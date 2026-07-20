import asyncio
from typing import Dict, List, Optional
from websockets import WebSocketServerProtocol, ConnectionClosed
from websockets.server import serve

class ChatServer:
    """
    A real-time chat application server using WebSockets.
    """

    def __init__(self):
        self.clients: Dict[str, WebSocketServerProtocol] = {}
        self.private_conversations: Dict[str, List[str]] = {}

    async def register_client(self, client: WebSocketServerProtocol, username: str):
        """
        Register a new client with the given username.
        
        :param client: The WebSocket client protocol.
        :param username: The username chosen by the client.
        """
        if username in self.clients:
            await client.send(f"Username {username} is already taken.")
            return

        self.clients[username] = client
        await client.send(f"Welcome, {username}!")

    async def broadcast_message(self, message: str, sender: str):
        """
        Broadcast a message to all connected clients.
        
        :param message: The message to broadcast.
        :param sender: The sender of the message.
        """
        for client in self.clients.values():
            await client.send(f"{sender}: {message}")

    async def send_private_message(self, message: str, sender: str, recipient: str):
        """
        Send a private message from the sender to the recipient.
        
        :param message: The private message.
        :param sender: The sender of the message.
        :param recipient: The recipient of the message.
        """
        if recipient not in self.clients:
            await self.clients[sender].send(f"User {recipient} is not online.")
            return

        await self.clients[recipient].send(f"Private message from {sender}: {message}")

    async def handle_client(self, client: WebSocketServerProtocol):
        """
        Handle a new client connection.
        
        :param client: The WebSocket client protocol.
        """
        try:
            username = await client.recv()
            await self.register_client(client, username)

            while True:
                message = await client.recv()
                if message.startswith("/private"):
                    _, recipient, private_message = message.split(":", 2)
                    await self.send_private_message(private_message, username, recipient)
                else:
                    await self.broadcast_message(message, username)
        except ConnectionClosed:
            del self.clients[username]
            await self.broadcast_message(f"{username} has disconnected.", "Server")

async def main():
    chat_server = ChatServer()
    async with serve(chat_server.handle_client, "localhost", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())