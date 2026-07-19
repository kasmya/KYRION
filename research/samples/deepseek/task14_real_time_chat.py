"""
Real-time Chat Application with WebSockets and Redis pub/sub.

Features:
- WebSocket server for real-time messaging
- Chat rooms/channels
- User presence (online/offline)
- Message history in Redis
- Typing indicators
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any, Set
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import redis.asyncio as redis

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('chat_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Real-time Chat API",
    description="WebSocket-based real-time chat with rooms and presence",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

class ConnectionManager:
    """Manages WebSocket connections and Redis pub/sub."""
    
    def __init__(self):
        """Initialize connection manager."""
        self.redis: Optional[redis.Redis] = None
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}  # room -> {user_id: ws}
        self.user_info: Dict[str, Dict[str, Any]] = {}  # user_id -> user info
        self.pubsub_task: Optional[asyncio.Task] = None
    
    async def initialize(self):
        """Initialize Redis connection."""
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        await self.redis.ping()
        logger.info("Connected to Redis")
    
    async def connect(self, websocket: WebSocket, room: str, user_id: str) -> None:
        """
        Connect a user to a room.
        
        Args:
            websocket: WebSocket connection
            room: Room name
            user_id: User identifier
        """
        await websocket.accept()
        
        # Initialize room if needed
        if room not in self.active_connections:
            self.active_connections[room] = {}
        
        # Add user to room
        self.active_connections[room][user_id] = websocket
        
        # Store user info
        self.user_info[user_id] = {
            'user_id': user_id,
            'room': room,
            'joined_at': datetime.now().isoformat(),
            'is_online': True
        }
        
        # Update presence in Redis
        await self.redis.hset(
            f"presence:{room}",
            user_id,
            json.dumps({'status': 'online', 'updated_at': datetime.now().isoformat()})
        )
        
        # Broadcast join notification
        await self.broadcast_to_room(
            room,
            {
                'type': 'user_joined',
                'user_id': user_id,
                'timestamp': datetime.now().isoformat(),
                'online_count': len(self.active_connections[room])
            },
            exclude_user=user_id
        )
        
        # Send recent message history
        await self.send_message_history(websocket, room)
        
        # Send current online users
        await websocket.send_json({
            'type': 'online_users',
            'users': list(self.active_connections[room].keys()),
            'timestamp': datetime.now().isoformat()
        })
        
        logger.info(f"User {user_id} connected to room {room}")
    
    async def disconnect(self, room: str, user_id: str) -> None:
        """
        Disconnect a user from a room.
        
        Args:
            room: Room name
            user_id: User identifier
        """
        # Remove from active connections
        if room in self.active_connections:
            self.active_connections[room].pop(user_id, None)
            
            # Clean up empty room
            if not self.active_connections[room]:
                del self.active_connections[room]
        
        # Update user info
        if user_id in self.user_info:
            self.user_info[user_id]['is_online'] = False
        
        # Update presence in Redis
        await self.redis.hset(
            f"presence:{room}",
            user_id,
            json.dumps({'status': 'offline', 'updated_at': datetime.now().isoformat()})
        )
        
        # Broadcast leave notification
        online_count = len(self.active_connections.get(room, {}))
        await self.broadcast_to_room(
            room,
            {
                'type': 'user_left',
                'user_id': user_id,
                'timestamp': datetime.now().isoformat(),
                'online_count': online_count
            }
        )
        
        logger.info(f"User {user_id} disconnected from room {room}")
    
    async def broadcast_to_room(
        self,
        room: str,
        message: Dict[str, Any],
        exclude_user: Optional[str] = None
    ) -> None:
        """
        Broadcast message to all users in a room.
        
        Args:
            room: Room name
            message: Message to broadcast
            exclude_user: User to exclude from broadcast
        """
        if room not in self.active_connections:
            return
        
        disconnected = []
        
        for user_id, websocket in self.active_connections[room].items():
            if user_id == exclude_user:
                continue
            
            try:
                await websocket.send_json(message)
            except WebSocketDisconnect:
                disconnected.append(user_id)
            except Exception as e:
                logger.error(f"Error sending to {user_id}: {str(e)}")
                disconnected.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected:
            await self.disconnect(room, user_id)
    
    async def send_message_history(
        self,
        websocket: WebSocket,
        room: str,
        limit: int = 50
    ) -> None:
        """
        Send recent message history to a user.
        
        Args:
            websocket: WebSocket connection
            room: Room name
            limit: Number of messages to send
        """
        try:
            messages = await self.redis.lrange(f"messages:{room}", -limit, -1)
            
            history = []
            for msg_json in messages:
                try:
                    msg = json.loads(msg_json)
                    history.append(msg)
                except json.JSONDecodeError:
                    continue
            
            if history:
                await websocket.send_json({
                    'type': 'message_history',
                    'messages': history,
                    'timestamp': datetime.now().isoformat()
                })
                
        except Exception as e:
            logger.error(f"Error sending message history: {str(e)}")
    
    async def store_message(
        self,
        room: str,
        message: Dict[str, Any],
        max_history: int = 1000
    ) -> None:
        """
        Store message in Redis.
        
        Args:
            room: Room name
            message: Message to store
            max_history: Maximum messages to keep
        """
        key = f"messages:{room}"
        
        # Add message to list
        await self.redis.rpush(key, json.dumps(message))
        
        # Trim to max history
        await self.redis.ltrim(key, -max_history, -1)
    
    async def broadcast_typing_indicator(
        self,
        room: str,
        user_id: str,
        is_typing: bool
    ) -> None:
        """
        Broadcast typing indicator.
        
        Args:
            room: Room name
            user_id: User who is typing
            is_typing: Typing status
        """
        await self.broadcast_to_room(
            room,
            {
                'type': 'typing_indicator',
                'user_id': user_id,
                'is_typing': is_typing,
                'timestamp': datetime.now().isoformat()
            },
            exclude_user=user_id
        )
    
    async def get_room_info(self, room: str) -> Dict[str, Any]:
        """
        Get information about a room.
        
        Args:
            room: Room name
            
        Returns:
            Room information
        """
        online_users = list(self.active_connections.get(room, {}).keys())
        message_count = await self.redis.llen(f"messages:{room}")
        
        return {
            'room': room,
            'online_users': online_users,
            'online_count': len(online_users),
            'message_count': message_count
        }
    
    async def get_user_presence(self, room: str, user_id: str) -> Dict[str, Any]:
        """
        Get user presence information.
        
        Args:
            room: Room name
            user_id: User identifier
            
        Returns:
            Presence information
        """
        presence_data = await self.redis.hget(f"presence:{room}", user_id)
        
        if presence_data:
            return json.loads(presence_data)
        
        return {'status': 'offline'}

# Initialize connection manager
manager = ConnectionManager()

@app.on_event("startup")
async def startup():
    """Initialize connection manager on startup."""
    await manager.initialize()
    logger.info("Chat server started")

@app.on_event("shutdown")
async def shutdown():
    """Clean up on shutdown."""
    if manager.redis:
        await manager.redis.close()
    logger.info("Chat server stopped")

@app.get("/")
async def get():
    """Get chat client HTML."""
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
    <title>Real-time Chat</title>
    <style>
        body { font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px; }
        #messages { border: 1px solid #ccc; height: 400px; overflow-y: scroll; padding: 10px; margin-bottom: 10px; }
        .message { margin: 5px 0; padding: 5px; }
        .system { color: #666; font-style: italic; }
        .input-area { display: flex; gap: 10px; }
        input { flex: 1; padding: 10px; }
        button { padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; }
        #typing { color: #666; font-style: italic; height: 20px; }
    </style>
</head>
<body>
    <h1>Chat Room: <span id="roomName">general</span></h1>
    <div id="messages"></div>
    <div id="typing"></div>
    <div class="input-area">
        <input type="text" id="messageInput" placeholder="Type your message..." onkeypress="handleKeyPress(event)">
        <button onclick="sendMessage()">Send</button>
    </div>
    <script>
        const room = 'general';
        const userId = 'user_' + Math.random().toString(36).substr(2, 9);
        const ws = new WebSocket(`ws://localhost:8004/ws/${room}?user_id=${userId}`);
        
        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            const messagesDiv = document.getElementById('messages');
            
            if (data.type === 'message') {
                messagesDiv.innerHTML += `<div class="message"><strong>${data.user_id}:</strong> ${data.content}</div>`;
            } else if (data.type === 'user_joined') {
                messagesDiv.innerHTML += `<div class="message system">${data.user_id} joined (${data.online_count} online)</div>`;
            } else if (data.type === 'user_left') {
                messagesDiv.innerHTML += `<div class="message system">${data.user_id} left (${data.online_count} online)</div>`;
            } else if (data.type === 'typing_indicator') {
                document.getElementById('typing').textContent = data.is_typing ? `${data.user_id} is typing...` : '';
            } else if (data.type === 'online_users') {
                messagesDiv.innerHTML += `<div class="message system">Online: ${data.users.join(', ')}</div>`;
            } else if (data.type === 'message_history') {
                data.messages.forEach(msg => {
                    messagesDiv.innerHTML += `<div class="message"><strong>${msg.user_id}:</strong> ${msg.content}</div>`;
                });
            }
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        };
        
        function sendMessage() {
            const input = document.getElementById('messageInput');
            if (input.value.trim()) {
                ws.send(JSON.stringify({type: 'message', content: input.value}));
                input.value = '';
            }
        }
        
        function handleKeyPress(event) {
            if (event.key === 'Enter') sendMessage();
        }
        
        let typingTimer;
        document.getElementById('messageInput').addEventListener('input', function() {
            clearTimeout(typingTimer);
            ws.send(JSON.stringify({type: 'typing', is_typing: true}));
            typingTimer = setTimeout(() => {
                ws.send(JSON.stringify({type: 'typing', is_typing: false}));
            }, 1000);
        });
    </script>
</body>
</html>
    """)

@app.websocket("/ws/{room}")
async def websocket_endpoint(
    websocket: WebSocket,
    room: str,
    user_id: str = Query(...)
):
    """
    WebSocket endpoint for real-time chat.
    
    Args:
        websocket: WebSocket connection
        room: Chat room name
        user_id: User identifier
    """
    await manager.connect(websocket, room, user_id)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message_type = data.get('type', 'message')
            
            if message_type == 'message':
                # Handle chat message
                content = data.get('content', '').strip()
                
                if not content:
                    continue
                
                message = {
                    'type': 'message',
                    'user_id': user_id,
                    'content': content,
                    'message_id': str(uuid.uuid4()),
                    'timestamp': datetime.now().isoformat()
                }
                
                # Store message
                await manager.store_message(room, message)
                
                # Broadcast to room
                await manager.broadcast_to_room(room, message)
                
                logger.info(f"Message from {user_id} in {room}: {content[:50]}")
                
            elif message_type == 'typing':
                # Handle typing indicator
                is_typing = data.get('is_typing', False)
                await manager.broadcast_typing_indicator(room, user_id, is_typing)
                
            elif message_type == 'ping':
                # Heartbeat
                await websocket.send_json({'type': 'pong', 'timestamp': datetime.now().isoformat()})
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {user_id}: {str(e)}", exc_info=True)
    finally:
        await manager.disconnect(room, user_id)

@app.get("/api/rooms/{room}/info")
async def get_room_info(room: str):
    """Get room information."""
    try:
        info = await manager.get_room_info(room)
        return info
    except Exception as e:
        logger.error(f"Error getting room info: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/rooms")
async def list_rooms():
    """List all active rooms."""
    rooms = list(manager.active_connections.keys())
    return {'rooms': rooms, 'count': len(rooms)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004, reload=True)
