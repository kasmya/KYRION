import asyncio
from typing import Dict, List, Optional
from websockets import WebSocket, WebSocketServer, WebSocketException
from websockets.typing import URI
import logging
import json

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatServer:
    """
    Real-time Chat Application Server using WebSockets.

    Features:
    - User Connection
    - Message Broadcasting to all connected users
    - Private Messaging between users
    - User Disconnection Handling
    """

    def __init__(self):
        self.clients: Dict[str, WebSocket] = {}  # username: websocket
        self.username_map: Dict[WebSocket, str] = {}  # websocket: username

    async def register(self, websocket: WebSocket, username: str):
        """
        Register a new client with a username.

        :param websocket: Client's WebSocket object
        :param username: Chosen username
        """
        if username in self.clients:
            await websocket.send(json.dumps({"error": "Username already taken"}))
            return

        self.clients[username] = websocket
        self.username_map[websocket] = username
        logger.info(f"Client {username} registered")

        # Broadcast new connection to all clients
        await self.broadcast({"message": f"{username} joined the chat", "sender": "SYSTEM"})

    async def unregister(self, websocket: WebSocket):
        """
        Unregister a client upon disconnection.

        :param websocket: Client's WebSocket object
        """
        username = self.username_map.pop(websocket, None)
        if username:
            del self.clients[username]
            logger.info(f"Client {username} disconnected")
            await self.broadcast({"message": f"{username} left the chat", "sender": "SYSTEM"})

    async def broadcast(self, message: Dict[str, str]):
        """
        Broadcast a message to all connected clients.

        :param message: Message dictionary with 'message' and 'sender'
        """
        for client in self.clients.values():
            try:
                await client.send(json.dumps(message))
            except WebSocketException as e:
                logger warning(f"Error broadcasting to client: {e}")
                await self.unregister(client)

    async def send_private(self, message: Dict[str, str], recipient_username: str):
        """
        Send a private message to a specific user.

        :param message: Message dictionary with 'message' and 'sender'
        :param recipient_username: Username of the recipient
        """
        recipient_ws = self.clients.get(recipient_username)
        if recipient_ws:
            try:
                await recipient_ws.send(json.dumps({"private": True, **message}))
            except WebSocketException as e:
                logger.warning(f"Error sending private message: {e}")
                await self.unregister(recipient_ws)
        else:
            logger.info(f"Recipient {recipient_username} not found")

    async def handle_client(self, websocket: WebSocket, path: str):
        """
        Handle a new client connection.

        :param websocket: Client's WebSocket object
        :param path: Path of the connection (not used)
        """
        try:
            # Wait for initial message containing the username
            msg = await websocket.recv()
            username = json.loads(msg).get("username")
            if not username:
                await websocket.send(json.dumps({"error": "Username required"}))
                return

            await self.register(websocket, username)

            # Handle incoming messages
            async for message in websocket:
                data = json.loads(message)
                if data.get("private"):
                    recipient_username = data["to"]
                    await self.send_private({"message": data["message"], "sender": username}, recipient_username)
                else:
                    await self.broadcast({"message": data["message"], "sender": username})
        except WebSocketException as e:
            logger.warning(f"Client connection error: {e}")
        finally:
            await self.unregister(websocket)

async def main():
    """
    Main entry point for the chat server.
    """
    server = ChatServer()
    async with WebSocketServer(URI("ws://localhost:8765"), ChatServer().handle_client) as server:
        logger.info("Chat server started on localhost:8765")
        await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())