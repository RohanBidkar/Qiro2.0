# MongoDB Chat Storage Setup

## Overview
This application now uses MongoDB to store chat history persistently. The sidebar displays all saved chats and allows you to:
- View recent chats
- Switch between different conversations
- Delete old chats
- Create new chats

## Configuration

### MongoDB Connection
The MongoDB connection URI is configured in `server/.env`:
```
MONGODB_URI=mongodb+srv://rohan:rohan@2005@cluster0.v3kmv6n.mongodb.net/?appName=Cluster0
```

### Database Structure
- **Database**: `perplexity_db`
- **Collection**: `chats`

### Chat Document Schema
```json
{
  "id": "unique-uuid",
  "title": "First 50 characters of first message",
  "messages": [...],
  "checkpoint_id": "conversation-checkpoint-id",
  "created_at": "ISO timestamp",
  "updated_at": "ISO timestamp"
}
```

## API Endpoints

### GET /chats
Fetches all chats (limited to 50 most recent)

### GET /chats/{chat_id}
Fetches a specific chat by ID

### POST /chats
Creates a new chat

### PUT /chats/{chat_id}
Updates an existing chat

### DELETE /chats/{chat_id}
Deletes a chat

## Features

### Automatic Saving
- Chats are automatically saved to MongoDB after each message exchange
- The first user message is used to generate the chat title (first 50 characters)
- Updates are made automatically as the conversation progresses

### Sidebar
- Click the menu button (☰) to open the sidebar
- View all your recent chats
- Click on a chat to load it
- Hover over a chat to see the delete button
- Click "New chat" to start a fresh conversation

## Installation

Make sure to install the required dependencies:
```bash
cd server
pip install pymongo langchain-groq
```

## Usage

1. Start MongoDB (if running locally) or ensure your MongoDB Atlas cluster is accessible
2. Start the backend server:
   ```bash
   cd server
   uvicorn app:app --reload
   ```
3. Start the frontend:
   ```bash
   cd client
   npm run dev
   ```
4. Open the app and start chatting - your conversations will be automatically saved!
