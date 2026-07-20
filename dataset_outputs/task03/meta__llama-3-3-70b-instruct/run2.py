import asyncio
import logging
from typing import Dict, List
import websockets
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# User dictionary to store connected users
users: Dict[str, websockets.WebSocketServerProtocol] = {}

# User message history dictionary
user_messages: Dict[str, List[str]] = {}

async def register(websocket: websockets.WebSocketServerProtocol):
    """Register a new user connection."""
    try:
        # Receive username from client
        username = await websocket.recv()
        logger.info(f"New connection from user: {username}")

        # Check if username already exists
        if username in users:
            await websocket.send("Username already taken. Please try again.")
            return

        # Add user to dictionary
        users[username] = websocket
        user_messages[username] = []

        # Send acknowledgement to client
        await websocket.send("Connected successfully!")

        # Broadcast new user to all connected users
        await broadcast(f"New user {username} connected.")

    except websockets.ConnectionClosed:
        logger.info("Connection closed.")
    except Exception as e:
        logger.error(f"Error registering user: {e}")

async def broadcast(message: str):
    """Broadcast a message to all connected users."""
    try:
        for user, websocket in users.items():
            await websocket.send(message)
    except Exception as e:
        logger.error(f"Error broadcasting message: {e}")

async def private_message(websocket: websockets.WebSocketServerProtocol, message: str):
    """Send a private message to a user."""
    try:
        # Extract recipient username and message
        data = json.loads(message)
        recipient = data["recipient"]
        msg = data["message"]

        # Check if recipient is online
        if recipient in users:
            await users[recipient].send(f"Private message from {data['sender']}: {msg}")
        else:
            await websocket.send(f"User {recipient} is offline.")

    except Exception as e:
        logger.error(f"Error sending private message: {e}")

async def handle_connection(websocket: websockets.WebSocketServerProtocol):
    """Handle a new user connection."""
    try:
        # Register new user connection
        await register(websocket)

        # Handle incoming messages
        while True:
            message = await websocket.recv()
            logger.info(f"Received message: {message}")

            # Check if message is a private message
            if message.startswith("private:"):
                await private_message(websocket, message[8:])
            else:
                # Broadcast message to all connected users
                await broadcast(f"Message from {list(users.keys())[list(users.values()).index(websocket)]}: {message}")

    except websockets.ConnectionClosed:
        logger.info("Connection closed.")
    except Exception as e:
        logger.error(f"Error handling connection: {e}")

async def main():
    """Main entry point."""
    async with websockets.serve(handle_connection, "localhost", 8765):
        logger.info("Server started. Waiting for connections...")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())