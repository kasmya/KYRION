import asyncio
from typing import Dict, List, Tuple
from websockets import ConnectionClosed, WebSocketServerProtocol, connect, websockets
from asyncio import Semaphore

# Configuration
MAX_CLIENTS = 100
BROADCAST_PREFIX = "broadcast:"
PRIVATE_PREFIX = "private:"
DISCONNECT_EVENT = "disconnect"

# Security: Simple authentication (in real apps, use a secure method)
class User:
    def __init__(self, name: str, websocket: WebSocketServerProtocol):
        self.name = name
        self.websocket = websocket

    def __repr__(self):
        return f"User('{self.name}')"

class ChatServer:
    """
    Real-time Chat Server using WebSockets.

    Features:
    - User Connection
    - Message Broadcasting
    - Private Messaging
    - User Disconnection Handling
    """

    def __init__(self):
        self.users: Dict[str, User] = {}
        self.semaphore = Semaphore(MAX_CLIENTS)  # Throttling connections

    async def register(self, websocket: WebSocketServerProtocol, name: str):
        """
        Register a new user.

        :param websocket: Client's WebSocket object
        :param name: Chosen username
        :raises ValueError: If username is taken or exceeds MAX_CLIENTS
        """
        async with self.semaphore:
            if name in self.users:
                raise ValueError("Username taken")
            if len(self.users) >= MAX_CLIENTS:
                raise ValueError("Server full")
            self.users[name] = User(name, websocket)
            print(f"User '{name}' connected")

    async def unregister(self, name: str):
        """
        Remove a user upon disconnection.

        :param name: Username to remove
        """
        if name in self.users:
            del self.users[name]
            print(f"User '{name}' disconnected")

    async def broadcast(self, message: str):
        """
        Send a message to all connected users.

        :param message: Message to broadcast
        """
        for user in self.users.values():
            try:
                await user.websocket.send(message)
            except ConnectionClosed:
                await self.unregister(user.name)

    async def private_message(self, sender: str, recipient: str, message: str):
        """
        Send a private message from one user to another.

        :param sender: Sender's username
        :param recipient: Recipient's username
        :param message: Message to send
        :raises KeyError: If recipient not found
        """
        if recipient not in self.users:
            raise KeyError("Recipient not found")
        try:
            await self.users[recipient].websocket.send(f"[{sender}] {message}")
        except ConnectionClosed:
            await self.unregister(recipient)

    async def handle_connection(self, websocket: WebSocketServerProtocol, path: str):
        """
        Handle a new WebSocket connection.

        :param websocket: Client's WebSocket object
        :param path: Connection path (not used)
        """
        try:
            # Authentication step (simplified, use secure methods in production)
            auth_msg = await websocket.recv()
            if not auth_msg.startswith("auth:"):
                raise ValueError("Invalid initial message")
            _, name = auth_msg.split(":", 1)
            name = name.strip()
            if not name:  # Basic validation
                raise ValueError("Username cannot be empty")
            await self.register(websocket, name)

            # Listen for messages
            while True:
                message = await websocket.recv()
                if message.startswith(BROADCAST_PREFIX):
                    _, msg = message.split(":", 1)
                    await self.broadcast(f"[{name}] {msg}")
                elif message.startswith(PRIVATE_PREFIX):
                    _, recipient, msg = message.split(":", 2)
                    await self.private_message(name, recipient, msg)
                elif message == DISCONNECT_EVENT:
                    break
                else:
                    print(f"Unknown message type from {name}: {message}")
        except ConnectionClosed:
            await self.unregister(name)
        except Exception as e:
            print(f"Error handling {name}: {e}")
            await self.unregister(name)
        finally:
            # Ensure cleanup
            if name in self.users:
                del self.users[name]

async def main():
    """
    Start the chat server.
    """
    chat_server = ChatServer()
    async with websockets.serve(chat_server.handle_connection, "localhost", 8765):
        print("Chat server started on port 8765")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())