"""
### Task 14: Real-time Chat (WebSockets + Redis)

A FastAPI-based WebSocket chat server supporting rooms/channels, online
presence tracking, and message history persisted in Redis.

Requirements:
    pip install fastapi "uvicorn[standard]" redis

Run:
    export REDIS_URL=redis://localhost:6379/0
    uvicorn 14_realtime_chat:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set

import redis.asyncio as aioredis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("realtime_chat")

REDIS_URL = "redis://localhost:6379/0"
HISTORY_LIMIT = 100


@dataclass
class RoomState:
    """Tracks in-memory state for a single chat room."""

    connections: Dict[str, WebSocket] = field(default_factory=dict)

    @property
    def online_users(self) -> Set[str]:
        return set(self.connections.keys())


class ConnectionManager:
    """Manages WebSocket connections, rooms, presence, and Redis-backed history."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client
        self.rooms: Dict[str, RoomState] = {}

    def _history_key(self, room: str) -> str:
        return f"chat:history:{room}"

    async def connect(self, websocket: WebSocket, room: str, username: str) -> None:
        """Accepts a connection, registers presence, and sends recent history."""
        await websocket.accept()
        room_state = self.rooms.setdefault(room, RoomState())
        room_state.connections[username] = websocket

        logger.info("User '%s' joined room '%s'", username, room)

        history = await self.get_history(room)
        await websocket.send_json({"type": "history", "room": room, "messages": history})
        await self.broadcast_presence(room)

    def disconnect(self, room: str, username: str) -> None:
        """Removes a user's connection from a room."""
        room_state = self.rooms.get(room)
        if room_state and username in room_state.connections:
            del room_state.connections[username]
            logger.info("User '%s' left room '%s'", username, room)

    async def broadcast(self, room: str, payload: dict) -> None:
        """Sends a JSON payload to all connected users in a room."""
        room_state = self.rooms.get(room)
        if not room_state:
            return

        stale_users: List[str] = []
        for user, ws in room_state.connections.items():
            try:
                await ws.send_json(payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to send to '%s' in '%s': %s", user, room, exc)
                stale_users.append(user)

        for user in stale_users:
            self.disconnect(room, user)

    async def broadcast_presence(self, room: str) -> None:
        """Broadcasts the current list of online users in a room."""
        room_state = self.rooms.get(room)
        online = sorted(room_state.online_users) if room_state else []
        await self.broadcast(room, {"type": "presence", "room": room, "online_users": online})

    async def save_message(self, room: str, username: str, text: str) -> dict:
        """Persists a chat message to Redis and returns the stored message dict."""
        message = {
            "username": username,
            "text": text,
            "timestamp": datetime.utcnow().isoformat(),
        }
        try:
            await self.redis.rpush(self._history_key(room), json.dumps(message))
            await self.redis.ltrim(self._history_key(room), -HISTORY_LIMIT, -1)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to persist message to Redis: %s", exc)
        return message

    async def get_history(self, room: str) -> List[dict]:
        """Fetches recent message history for a room from Redis."""
        try:
            raw_messages = await self.redis.lrange(self._history_key(room), 0, -1)
            return [json.loads(m) for m in raw_messages]
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch history from Redis: %s", exc)
            return []


app = FastAPI(title="Realtime Chat Server")
redis_client: Optional[aioredis.Redis] = None
manager: Optional[ConnectionManager] = None


@app.on_event("startup")
async def on_startup() -> None:
    global redis_client, manager
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    manager = ConnectionManager(redis_client)
    logger.info("Chat server started, connected to Redis at %s", REDIS_URL)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if redis_client is not None:
        await redis_client.close()


@app.websocket("/ws/{room}/{username}")
async def chat_endpoint(websocket: WebSocket, room: str, username: str) -> None:
    """WebSocket endpoint: /ws/{room}/{username}

    Incoming messages are plain JSON: {"text": "hello everyone"}
    """
    assert manager is not None
    await manager.connect(websocket, room, username)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                text = str(data.get("text", "")).strip()
            except json.JSONDecodeError:
                text = raw.strip()

            if not text:
                continue

            message = await manager.save_message(room, username, text)
            await manager.broadcast(room, {"type": "message", "room": room, **message})

    except WebSocketDisconnect:
        manager.disconnect(room, username)
        await manager.broadcast_presence(room)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in chat endpoint: %s", exc)
        manager.disconnect(room, username)
        await manager.broadcast_presence(room)


@app.get("/rooms/{room}/online")
async def get_online_users(room: str) -> dict:
    """REST helper endpoint to check who is currently online in a room."""
    assert manager is not None
    room_state = manager.rooms.get(room)
    return {"room": room, "online_users": sorted(room_state.online_users) if room_state else []}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
