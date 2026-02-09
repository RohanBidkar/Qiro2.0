from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction
from langchain_core.messages import HumanMessage
from uuid import uuid4
import os
from dotenv import load_dotenv

# Import from app.py
from app import graph

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7880316819:AAHvFwf0AGmZnQ6S4fvdn1VbM-9CBITaAes")

# Store user conversation threads
user_conversations = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user_id = update.effective_user.id
    
    # Initialize a new conversation for this user if not exists
    if user_id not in user_conversations:
        user_conversations[user_id] = {
            "checkpoint_id": str(uuid4()),
            "conversation_history": []
        }
    
    welcome_message = (
        " Welcome to Qiro AI Assistant!\n\n"
        "I'm an intelligent assistant created by Rohan and powered by advanced AI that can:\n"
        "• Answer your questions\n"
        "• Search the web for information\n"
        "• Have contextual conversations\n\n"
        "Just send me a message and I'll respond! Use /help for more commands."
    )
    
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "📚 Available Commands:\n\n"
        "/start - Start a new conversation\n"
        "/help - Show this help message\n"
        "/clear - Clear conversation history\n\n"
        "Simply send any message to chat with Qiro!"
    )
    await update.message.reply_text(help_text)

async def clear_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear the conversation history for the user."""
    user_id = update.effective_user.id
    
    if user_id in user_conversations:
        user_conversations[user_id] = {
            "checkpoint_id": str(uuid4()),
            "conversation_history": []
        }
    
    await update.message.reply_text("✅ Conversation history cleared! Starting fresh...")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages and generate responses from Qiro AI."""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Initialize conversation if needed
    if user_id not in user_conversations:
        user_conversations[user_id] = {
            "checkpoint_id": str(uuid4()),
            "conversation_history": []
        }
    
    # Show typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    try:
        # Get the conversation info
        conv_info = user_conversations[user_id]
        checkpoint_id = conv_info["checkpoint_id"]
        
        # Prepare the config for the graph
        config = {
            "configurable": {
                "thread_id": checkpoint_id
            }
        }
        
        # Invoke the graph with the user's message
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=user_message)]},
            config=config
        )
        
        # Extract the AI response - get the last AIMessage from the result
        ai_response = ""
        if result["messages"]:
            # Find the last message that's an AI response
            for msg in reversed(result["messages"]):
                if hasattr(msg, "__class__") and "AIMessage" in msg.__class__.__name__:
                    if hasattr(msg, "content"):
                        ai_response = msg.content
                        break
            
            # Fallback: if no AI message found, use last message
            if not ai_response:
                last_message = result["messages"][-1]
                if hasattr(last_message, "content"):
                    ai_response = last_message.content
                else:
                    ai_response = str(last_message)
        
        # Split response if too long (Telegram has a 4096 char limit)
        if len(ai_response) > 4096:
            # Send in chunks
            for i in range(0, len(ai_response), 4096):
                chunk = ai_response[i:i+4096]
                await update.message.reply_text(chunk, parse_mode=None)
        else:
            await update.message.reply_text(ai_response, parse_mode=None)
        
        # Update conversation history
        conv_info["conversation_history"].append({
            "role": "user",
            "content": user_message
        })
        conv_info["conversation_history"].append({
            "role": "assistant",
            "content": ai_response
        })
        
    except Exception as e:
        error_message = f"❌ Sorry, I encountered an error: {str(e)}\n\nPlease try again or use /clear to reset the conversation."
        await update.message.reply_text(error_message)
        print(f"Error handling message from user {user_id}: {str(e)}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    print(f"Exception while handling an update: {context.error}")

def setup_telegram_bot():
    """Initialize and setup the Telegram bot application."""
    # Create the Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_conversation))
    
    # Add message handler (must be after specific handlers)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    return application

def run_telegram_bot():
    """Run the Telegram bot (blocking call - for standalone execution)."""
    application = setup_telegram_bot()
    application.run_polling(allowed_updates=Update.ALL_TYPES)

async def start_telegram_bot_async(application):
    """Start the Telegram bot in non-blocking mode (for FastAPI integration)."""
    await application.initialize()
    await application.start()
    # Start polling for messages
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    return application

async def stop_telegram_bot_async(application):
    """Stop the Telegram bot gracefully."""
    await application.updater.stop()
    await application.stop()
    await application.shutdown()
