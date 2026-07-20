import asyncio
import json
from typing import Dict, List, Optional
import websockets

class ChatServer:
    """
    Real-time chat application using WebSockets.

    Features:
    - User connection
    - Message broadcasting to all connected users
    - Private messaging between users
    - User disconnection handling
    """

    def __init__(self):
        self.users: Dict[str, websockets.WebSocketClientProtocol] = {}

    async def register(self, websocket: websockets.WebSocketClientProtocol, username: str) -> None:
        """
        Register a new user connection.

        Args:
        - websocket (websockets.WebSocketClientProtocol): The WebSocket object for the new connection.
        - username (str): The username of the new user.
        """
        if username in self.users:
            await websocket.send(json.dumps({"error": "Username already taken"}))
            await websocket.close()
        else:
            self.users[username] = websocket
            await websocket.send(json.dumps({"message": "Welcome to the chat!"}))

    async def unregister(self, username: str) -> None:
        """
        Unregister a user connection.

        Args:
        - username (str): The username of the user to unregister.
        """
        if username in self.users:
            del self.users[username]

    async def broadcast(self, message: str, exclude: Optional[str] = None) -> None:
        """
        Broadcast a message to all connected users.

        Args:
        - message (str): The message to broadcast.
        - exclude (Optional[str]): The username of the user to exclude from the broadcast.
        """
        if exclude is None:
            await asyncio.wait([user.send(message) for user in self.users.values()])
        else:
            await asyncio.wait([user.send(message) for username, user in self.users.items() if username != exclude])

    async def private_message(self, sender: str, recipient: str, message: str) -> None:
        """
        Send a private message from one user to another.

        Args:
        - sender (str): The username of the sender.
        - recipient (str): The username of the recipient.
        - message (str): The private message.
        """
        if recipient in self.users:
            await self.users[recipient].send(json.dumps({"private": message, "from": sender}))
        else:
            await self.users[sender].send(json.dumps({"error": "Recipient not found"}))

    async def handle_connection(self, websocket: websockets.WebSocketClientProtocol, path: str) -> None:
        """
        Handle a new WebSocket connection.

        Args:
        - websocket (websockets.WebSocketClientProtocol): The WebSocket object for the new connection.
        - path (str): The path of the new connection.
        """
        try:
            async for message in websocket:
                data = json.loads(message)
                if data["type"] == "register":
                    await self.register(websocket, data["username"])
                elif data["type"] == "message":
                    await self.broadcast(data["message"])
                elif data["type"] == "private":
                    await self.private_message(data["from"], data["to"], data["message"])
        except json.JSONDecodeError:
            await websocket.send(json.dumps({"error": "Invalid JSON"}))
        except websockets.ConnectionClosed:
            for username, user in list(self.users.items()):
                if user == websocket:
                    await self.unregister(username)
        except Exception as e:
            await websocket.send(json.dumps({"error": str(e)}))

async def main():
    chat_server = ChatServer()
    async with websockets.serve(chat_server.handle_connection, "localhost", 8765):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())