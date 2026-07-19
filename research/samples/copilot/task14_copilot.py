"""
Real-time Chat using FastAPI, WebSockets, and Redis.
Features:
- WebSocket server for real-time messaging
- Rooms/channels
- User presence (online/offline)
- Message history in Redis
"""

import asyncio
import logging
import redis.asyncio as aioredis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, List

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Real-time Chat")
redis = aioredis.from_url("redis://localhost")


class ConnectionManager:
    """Manage WebSocket connections per room."""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, room: str, websocket: WebSocket):
        await websocket.accept()
        if room not in self.active_connections:
            self.active_connections[room] = []
        self.active_connections[room].append(websocket)
        await redis.sadd(f"room:{room}:users", str(websocket.client))

    def disconnect(self, room: str, websocket: WebSocket):
        self.active_connections[room].remove(websocket)

    async def broadcast(self, room: str, message: str):
        await redis.rpush(f"room:{room}:history", message)
        for connection in self.active_connections.get(room, []):
            await connection.send_text(message)


manager = ConnectionManager()


@app.websocket("/ws/{room}")
async def websocket_endpoint(websocket: WebSocket, room: str):
    await manager.connect(room, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(room, f"{websocket.client.host}: {data}")
    except WebSocketDisconnect:
        manager.disconnect(room, websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

