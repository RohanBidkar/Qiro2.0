from typing import TypedDict, Annotated, Optional
from langgraph.graph import add_messages, StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessageChunk, ToolMessage, SystemMessage
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
import asyncio
from contextlib import asynccontextmanager

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
mongo_client = MongoClient(MONGODB_URI)
db = mongo_client["perplexity_db"]
chats_collection = db["chats"]

memory = MemorySaver()

class State(TypedDict):
    messages: Annotated[list, add_messages]

search_tool = TavilySearchResults(
    max_results=4,
)

tools = [search_tool]

llm = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0,
    max_tokens=None,
    reasoning_format="parsed",
    timeout=None,
    max_retries=2,
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
    tool_calls = state["messages"][-1].tool_calls
    
    tool_messages = []
    
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]
        
        if tool_name == "tavily_search_results_json":
            search_results = await search_tool.ainvoke(tool_args)
            
            tool_message = ToolMessage(
                content=str(search_results),
                tool_call_id=tool_id,
                name=tool_name
            )
            
            tool_messages.append(tool_message)
    
    return {"messages": tool_messages}

async def system_node(state):
    """Add system context with current datetime to messages"""
    current_datetime = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    system_message = f"""You are Qiro, a helpful AI assistant built by Rohan Bidkar. 
Current date and time: {current_datetime}

Answer user questions concisely and helpfully. When users ask about current events, 
today's date, or time-sensitive information, use the current datetime above as context.
Always provide accurate and up-to-date information."""
    
    return {
        "messages": [
            SystemMessage(content=system_message)
        ]
    }

graph_builder = StateGraph(State)

graph_builder.add_node("system_node", system_node)
graph_builder.add_node("model", model)
graph_builder.add_node("tool_node", tool_node)
graph_builder.set_entry_point("system_node")

graph_builder.add_edge("system_node", "model")
graph_builder.add_conditional_edges("model", tools_router)
graph_builder.add_edge("tool_node", "model")
graph_builder.add_edge("model", END)

graph = graph_builder.compile(checkpointer=memory)

# Telegram Bot Setup
telegram_app = None

async def lifespan(app: FastAPI):
    """Manage the lifespan of the FastAPI application with Telegram bot."""
    global telegram_app
    
    # Startup
    try:
        from telegram_handler import setup_telegram_bot, start_telegram_bot_async
        telegram_app = setup_telegram_bot()
        await start_telegram_bot_async(telegram_app)
        print("[OK] Telegram bot started successfully!")
    except Exception as e:
        print(f"[WARNING] Could not start Telegram bot: {e}")
        telegram_app = None
    
    yield
    
    # Shutdown
    try:
        if telegram_app:
            from telegram_handler import stop_telegram_bot_async
            await stop_telegram_bot_async(telegram_app)
            print("[OK] Telegram bot stopped successfully!")
    except Exception as e:
        print(f"[WARNING] Error stopping Telegram bot: {e}")

app = FastAPI(lifespan=lifespan)

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
        new_checkpoint_id = str(uuid4())

        config = {
            "configurable": {
                "thread_id": new_checkpoint_id
            }
        }
        
        events = graph.astream_events(
            {"messages": [HumanMessage(content=message)]},
            version="v2",
            config=config
        )
        
        yield f"data: {{\"type\": \"checkpoint\", \"checkpoint_id\": \"{new_checkpoint_id}\"}}\n\n"
    else:
        config = {
            "configurable": {
                "thread_id": checkpoint_id
            }
        }
        events = graph.astream_events(
            {"messages": [HumanMessage(content=message)]},
            version="v2",
            config=config
        )

    async for event in events:
        event_type = event["event"]
        
        if event_type == "on_chat_model_stream":
            chunk_content = serialise_ai_message_chunk(event["data"]["chunk"])
            safe_content = chunk_content.replace("'", "\\'").replace("\n", "\\n")
            
            yield f"data: {{\"type\": \"content\", \"content\": \"{safe_content}\"}}\n\n"
            
        elif event_type == "on_chat_model_end":
            tool_calls = event["data"]["output"].tool_calls if hasattr(event["data"]["output"], "tool_calls") else []
            search_calls = [call for call in tool_calls if call["name"] == "tavily_search_results_json"]
            
            if search_calls:
                search_query = search_calls[0]["args"].get("query", "")
                safe_query = search_query.replace('"', '\\"').replace("'", "\\'").replace("\n", "\\n")
                yield f"data: {{\"type\": \"search_start\", \"query\": \"{safe_query}\"}}\n\n"
                
        elif event_type == "on_tool_end" and event["name"] == "tavily_search_results_json":
            output = event["data"]["output"]
            
            if isinstance(output, list):
                urls = []
                for item in output:
                    if isinstance(item, dict) and "url" in item:
                        urls.append(item["url"])
                
                urls_json = json.dumps(urls)
                yield f"data: {{\"type\": \"search_results\", \"urls\": {urls_json}}}\n\n"
    
    yield f"data: {{\"type\": \"end\"}}\n\n"

@app.get("/chat_stream/{message}")
async def chat_stream(message: str, checkpoint_id: Optional[str] = Query(None)):
    return StreamingResponse(
        generate_chat_responses(message, checkpoint_id), 
        media_type="text/event-stream"
    )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "telegram_bot_active": telegram_app is not None
    }


@app.get("/chats")
async def get_chats(user_id: Optional[str] = Query(None)):
    """Get all chats for the current user"""
    try:
        query = {"user_id": user_id} if user_id else {}
        chats = list(chats_collection.find(query, {"_id": 0}).sort("created_at", -1).limit(50))
        return {"chats": chats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chats/{chat_id}")
async def get_chat(chat_id: str, user_id: Optional[str] = Query(None)):
    """Get a specific chat by ID"""
    try:
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

        query = {"id": chat_id}
        if user_id:
            query["user_id"] = user_id
        
        result = chats_collection.delete_one(query)
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Chat not found")
        return {"message": "Chat deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


frontend_dist = os.path.join(os.path.dirname(__file__), "..", "client", "dist")

if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
