from typing import TypedDict, Annotated, Optional
from langgraph.graph import add_messages, StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessageChunk, ToolMessage
from dotenv import load_dotenv
from langchain_community.tools.tavily_search import TavilySearchResults
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles # Added for serving frontend
import json
from uuid import uuid4
from langgraph.checkpoint.memory import MemorySaver
from pymongo import MongoClient
from datetime import datetime
import os

load_dotenv()

# Initialize MongoDB
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
mongo_client = MongoClient(MONGODB_URI)
db = mongo_client["perplexity_db"]
chats_collection = db["chats"]

# Initialize memory saver for checkpointing
memory = MemorySaver()

class State(TypedDict):
    messages: Annotated[list, add_messages]

search_tool = TavilySearchResults(
    max_results=4,
)

tools = [search_tool]

llm = ChatGroq(
    model="qwen/qwen3-32b",
    temperature=0,
    max_tokens=None,
    reasoning_format="parsed",
    timeout=None,
    max_retries=2,
    # other params...
)

llm_with_tools = llm.bind_tools(tools=tools)

async def model(state: State):
    result = await llm_with_tools.ainvoke(state["messages"])
    return {
        "messages": [result], 
    }

async def tools_router(state: State):
    last_message = state["messages"][-1]

    if(hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0):
        return "tool_node"
    else: 
        return END
    
async def tool_node(state):
    """Custom tool node that handles tool calls from the LLM."""
    # Get the tool calls from the last message
    tool_calls = state["messages"][-1].tool_calls
    
    # Initialize list to store tool messages
    tool_messages = []
    
    # Process each tool call
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]
        
        # Handle the search tool
        if tool_name == "tavily_search_results_json":
            # Execute the search tool with the provided arguments
            search_results = await search_tool.ainvoke(tool_args)
            
            # Create a ToolMessage for this result
            tool_message = ToolMessage(
                content=str(search_results),
                tool_call_id=tool_id,
                name=tool_name
            )
            
            tool_messages.append(tool_message)
    
    # Add the tool messages to the state
    return {"messages": tool_messages}

async def system_node(state):
    return {
        "messages": [
            {"role": "system", "content": "You are Qiro a helpful assistant built by Rohan Bidkar."}
        ]
    }

graph_builder = StateGraph(State)

graph_builder.add_node("model", model)
graph_builder.add_node("system_node", system_node)
graph_builder.add_node("tool_node", tool_node)
graph_builder.set_entry_point("model")

graph_builder.add_conditional_edges("model", tools_router)
graph_builder.add_edge("tool_node", "model")
graph_builder.add_edge("model","system_node")

graph = graph_builder.compile(checkpointer=memory)

app = FastAPI()

# Add CORS middleware with settings that match frontend requirements
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"], 
    expose_headers=["Content-Type"], 
)

def serialise_ai_message_chunk(chunk): 
    if(isinstance(chunk, AIMessageChunk)):
        return chunk.content
    else:
        raise TypeError(
            f"Object of type {type(chunk).__name__} is not correctly formatted for serialisation"
        )

async def generate_chat_responses(message: str, checkpoint_id: Optional[str] = None):
    is_new_conversation = checkpoint_id is None
    
    if is_new_conversation:
        # Generate new checkpoint ID for first message in conversation
        new_checkpoint_id = str(uuid4())

        config = {
            "configurable": {
                "thread_id": new_checkpoint_id
            }
        }
        
        # Initialize with first message
        events = graph.astream_events(
            {"messages": [HumanMessage(content=message)]},
            version="v2",
            config=config
        )
        
        # First send the checkpoint ID
        yield f"data: {{\"type\": \"checkpoint\", \"checkpoint_id\": \"{new_checkpoint_id}\"}}\n\n"
    else:
        config = {
            "configurable": {
                "thread_id": checkpoint_id
            }
        }
        # Continue existing conversation
        events = graph.astream_events(
            {"messages": [HumanMessage(content=message)]},
            version="v2",
            config=config
        )

    async for event in events:
        event_type = event["event"]
        
        if event_type == "on_chat_model_stream":
            chunk_content = serialise_ai_message_chunk(event["data"]["chunk"])
            # Escape single quotes and newlines for safe JSON parsing
            safe_content = chunk_content.replace("'", "\\'").replace("\n", "\\n")
            
            yield f"data: {{\"type\": \"content\", \"content\": \"{safe_content}\"}}\n\n"
            
        elif event_type == "on_chat_model_end":
            # Check if there are tool calls for search
            tool_calls = event["data"]["output"].tool_calls if hasattr(event["data"]["output"], "tool_calls") else []
            search_calls = [call for call in tool_calls if call["name"] == "tavily_search_results_json"]
            
            if search_calls:
                # Signal that a search is starting
                search_query = search_calls[0]["args"].get("query", "")
                # Escape quotes and special characters
                safe_query = search_query.replace('"', '\\"').replace("'", "\\'").replace("\n", "\\n")
                yield f"data: {{\"type\": \"search_start\", \"query\": \"{safe_query}\"}}\n\n"
                
        elif event_type == "on_tool_end" and event["name"] == "tavily_search_results_json":
            # Search completed - send results or error
            output = event["data"]["output"]
            
            # Check if output is a list 
            if isinstance(output, list):
                # Extract URLs from list of search results
                urls = []
                for item in output:
                    if isinstance(item, dict) and "url" in item:
                        urls.append(item["url"])
                
                # Convert URLs to JSON and yield them
                urls_json = json.dumps(urls)
                yield f"data: {{\"type\": \"search_results\", \"urls\": {urls_json}}}\n\n"
    
    # Send an end event
    yield f"data: {{\"type\": \"end\"}}\n\n"

@app.get("/chat_stream/{message}")
async def chat_stream(message: str, checkpoint_id: Optional[str] = Query(None)):
    return StreamingResponse(
        generate_chat_responses(message, checkpoint_id), 
        media_type="text/event-stream"
    )

# MongoDB Chat Management Endpoints
@app.get("/chats")
async def get_chats(user_id: Optional[str] = Query(None)):
    """Get all chats for the current user"""
    try:
        # Filter by user_id if provided
        query = {"user_id": user_id} if user_id else {}
        chats = list(chats_collection.find(query, {"_id": 0}).sort("created_at", -1).limit(50))
        return {"chats": chats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chats/{chat_id}")
async def get_chat(chat_id: str, user_id: Optional[str] = Query(None)):
    """Get a specific chat by ID"""
    try:
        # Build query with user_id if provided
        query = {"id": chat_id}
        if user_id:
            query["user_id"] = user_id
        
        chat = chats_collection.find_one(query, {"_id": 0})
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        return chat
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chats")
async def create_chat(chat_data: dict):
    """Create a new chat"""
    try:
        chat_id = str(uuid4())
        chat = {
            "id": chat_id,
            "user_id": chat_data.get("user_id"),  # Add user_id from request
            "title": chat_data.get("title", "New Chat"),
            "messages": chat_data.get("messages", []),
            "checkpoint_id": chat_data.get("checkpoint_id"),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        chats_collection.insert_one(chat)
        return {"id": chat_id, "message": "Chat created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/chats/{chat_id}")
async def update_chat(chat_id: str, chat_data: dict, user_id: Optional[str] = Query(None)):
    """Update an existing chat"""
    try:
        update_data = {
            "messages": chat_data.get("messages"),
            "checkpoint_id": chat_data.get("checkpoint_id"),
            "updated_at": datetime.utcnow().isoformat()
        }
        if "title" in chat_data:
            update_data["title"] = chat_data["title"]
        
        # Build query with user_id if provided for security
        query = {"id": chat_id}
        if user_id:
            query["user_id"] = user_id
        
        result = chats_collection.update_one(
            query,
            {"$set": update_data}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Chat not found")
        return {"message": "Chat updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, user_id: Optional[str] = Query(None)):
    """Delete a chat"""
    try:
        # Build query with user_id if provided for security
        query = {"id": chat_id}
        if user_id:
            query["user_id"] = user_id
        
        result = chats_collection.delete_one(query)
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Chat not found")
        return {"message": "Chat deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve frontend in production
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "client", "dist")

if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")


# SSE - server-sent events 