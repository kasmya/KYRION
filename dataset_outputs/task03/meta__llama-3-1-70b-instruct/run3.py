import asyncio
import logging
import typing as t
from datetime import datetime
from websockets import ConnectionClosed, WebSocketServerProtocol, serve

# Set up logging
logging.basicConfig(level=logging.INFO)

# Type aliases
UserSocket = t.Tuple[str, WebSocketServerProtocol]
UserMap = t.Dict[str, UserSocket]
Message = t.Dict[str, t.Union[str, datetime]]

class ChatServer:
    def __init__(self):
        self.users: UserMap = {}
        self.broadcast_queue: asyncio.Queue[Message] = asyncio.Queue()

    async def handle_connection(self, websocket: WebSocketServerProtocol, path: str):
        """
        Handle a new WebSocket connection.

        :param websocket: WebSocket protocol instance
        :param path: Path of the WebSocket endpoint
        """
        # Handle connection
        username = await self._register_user(websocket)
        logging.info(f"User connected: {username}")

        # Listen for messages from the user
        await self._listen_for_messages(websocket, username)

        # Unregister the user when they disconnect
        await self._unregister_user(username)

    async def _register_user(self, websocket: WebSocketServerProtocol) -> str:
        """
        Register a new user and store their WebSocket connection.

        :param websocket: WebSocket protocol instance
        :return: Username of the registered user
        """
        # Wait for the user to send their username
        message = await websocket.recv()
        username = message

        # Store the user's WebSocket connection
        self.users[username] = (username, websocket)
        return username

    async def _listen_for_messages(self, websocket: WebSocketServerProtocol, username: str):
        """
        Listen for messages from the user and broadcast them to other users.

        :param websocket: WebSocket protocol instance
        :param username: Username of the user sending messages
        """
        while True:
            try:
                message = await websocket.recv()
            except ConnectionClosed:
                break

            # Parse the message
            try:
                message = message.split(":", 1)
                if len(message) != 2:
                    raise ValueError
                recipient, content = message
            except ValueError:
                await websocket.send("Invalid message format. Use 'username:message'.")
                continue

            # Broadcast the message to the recipient
            if recipient in self.users:
                await self.users[recipient][1].send(f"{username}:{content}")
            else:
                await websocket.send("Recipient not found.")

    async def _unregister_user(self, username: str):
        """
        Unregister a user and remove their WebSocket connection.

        :param username: Username of the user to unregister
        """
        if username in self.users:
            del self.users[username]
            logging.info(f"User disconnected: {username}")

    async def broadcast_messages(self):
        """
        Broadcast messages from the broadcast queue to all users.
        """
        while True:
            message = await self.broadcast_queue.get()
            for user in self.users.values():
                await user[1].send(message)

async def main():
    chat_server = ChatServer()
    asyncio.create_task(chat_server.broadcast_messages())
    async with serve(chat_server.handle_connection, "localhost", 8765):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())