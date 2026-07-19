"""Real-time Chat with FastAPI WebSockets and Redis pub/sub."""
import json, logging, asyncio
from typing import Dict, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import redis.asyncio as redis

logging.basicConfig(level=logging.INFO)
app = FastAPI()
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.online_users: Dict[str, Set[str]] = {} # room -> users

    async def connect(self, websocket: WebSocket, room: str, user: str):
        await websocket.accept()
        if room not in self.active_connections:
            self.active_connections[room] = set()
            self.online_users[room] = set()
        self.active_connections[room].add(websocket)
        self.online_users[room].add(user)
        await self.broadcast(room, {"type": "presence", "user": user, "status": "online"})

    def disconnect(self, websocket: WebSocket, room: str, user: str):
        if room in self.active_connections:
            self.active_connections[room].discard(websocket)
            self.online_users[room].discard(user)
            if not self.active_connections[room]:
                del self.active_connections[room]
                del self.online_users[room]

    async def broadcast(self, room: str, message: dict):
        if room in self.active_connections:
            for conn in self.active_connections[room]:
                await conn.send_json(message)

manager = ConnectionManager()

async def save_message(room: str, user: str, text: str):
    await redis_client.rpush(f"history:{room}", json.dumps({"user": user, "text": text}))
    await redis_client.ltrim(f"history:{room}", -50, -1)

@app.websocket("/ws/{room}/{user}")
async def websocket_endpoint(websocket: WebSocket, room: str, user: str):
    await manager.connect(websocket, room, user)
    
    # Send history
    history = await redis_client.lrange(f"history:{room}", 0, -1)
    for msg in history:
        await websocket.send_json({"type": "history", "data": json.loads(msg)})
        
    try:
        while True:
            data = await websocket.receive_text()
            await save_message(room, user, data)
            await manager.broadcast(room, {"type": "message", "user": user, "text": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket, room, user)
        await manager.broadcast(room, {"type": "presence", "user": user, "status": "offline"})

@app.get("/rooms/{room}/users")
async def get_online_users(room: str):
    return list(manager.online_users.get(room, set()))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)