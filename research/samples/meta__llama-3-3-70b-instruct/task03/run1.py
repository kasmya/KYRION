import asyncio
import json
from typing import Dict, List, Tuple
from websockets import WebSocket, ConnectionClosed

class ChatServer:
    """A real-time chat application using WebSockets."""

    def __init__(self):
        """Initialize the chat server."""
        self.users: Dict[str, WebSocket] = {}
        self.private_conversations: Dict[str, List[str]] = {}

    async def register(self, websocket: WebSocket, user_id: str) -> None:
        """Register a user connection."""
        if user_id in self.users:
            await websocket.send(json.dumps({"error": "User already connected"}))
            return
        self.users[user_id] = websocket
        await self.broadcast({"type": "user_connected", "user_id": user_id})

    async def unregister(self, user_id: str) -> None:
        """Unregister a user connection."""
        if user_id in self.users:
            del self.users[user_id]
            await self.broadcast({"type": "user_disconnected", "user_id": user_id})

    async def broadcast(self, message: Dict[str, str]) -> None:
        """Broadcast a message to all connected users."""
        for user_id, websocket in self.users.items():
            try:
                await websocket.send(json.dumps(message))
            except ConnectionClosed:
                await self.unregister(user_id)

    async def private_message(self, sender_id: str, recipient_id: str, message: str) -> None:
        """Send a private message between users."""
        if recipient_id not in self.users:
            await self.users[sender_id].send(json.dumps({"error": "Recipient not found"}))
            return
        await self.users[recipient_id].send(json.dumps({"type": "private_message", "sender_id": sender_id, "message": message}))

    async def handle_connection(self, websocket: WebSocket, path: str) -> None:
        """Handle a new WebSocket connection."""
        try:
            async for message in websocket:
                data = json.loads(message)
                if data["type"] == "register":
                    await self.register(websocket, data["user_id"])
                elif data["type"] == "send_message":
                    await self.broadcast({"type": "message", "user_id": data["user_id"], "message": data["message"]})
                elif data["type"] == "private_message":
                    await self.private_message(data["sender_id"], data["recipient_id"], data["message"])
        except json.JSONDecodeError:
            await websocket.send(json.dumps({"error": "Invalid JSON"}))
        except ConnectionClosed:
            await self.unregister(data["user_id"])

async def main() -> None:
    """Start the chat server."""
    chat_server = ChatServer()
    async with websockets.serve(chat_server.handle_connection, "localhost", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())