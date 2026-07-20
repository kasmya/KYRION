import asyncio
import logging
from typing import Dict, List

import websockets
import json

# Define a type for a message
class Message:
    def __init__(self, sender: str, content: str, private: bool = False, recipient: str = None):
        self.sender = sender
        self.content = content
        self.private = private
        self.recipient = recipient

    def to_dict(self) -> Dict:
        return {
            'sender': self.sender,
            'content': self.content,
            'private': self.private,
            'recipient': self.recipient
        }

# Create a logger
logger = logging.getLogger('chat')
logger.setLevel(logging.INFO)

# Create a handler and set the logging level
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)

# Create a formatter and add it to the handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# Add the handler to the logger
logger.addHandler(handler)

# Create a set to store the connected users
connected_users: Dict[str, websockets.WebSocketServerProtocol] = {}

async def broadcast(message: Message):
    """Broadcast a message to all connected users."""
    if message.private:
        if message.recipient in connected_users:
            await connected_users[message.recipient].send(json.dumps(message.to_dict()))
    else:
        for user in connected_users.values():
            await user.send(json.dumps(message.to_dict()))

async def handle_connection(websocket: websockets.WebSocketServerProtocol):
    """Handle a new connection from a user."""
    # Get the user's name
    try:
        name = await websocket.recv()
    except websockets.ConnectionClosed:
        return

    # Add the user to the set of connected users
    connected_users[name] = websocket
    logger.info(f'User {name} connected.')

    # Send a welcome message to the user
    await websocket.send(json.dumps({
        'content': f'Welcome, {name}!',
        'sender': 'Server'
    }))

    # Listen for messages from the user
    try:
        while True:
            try:
                message = await websocket.recv()
                message = json.loads(message)
                message = Message(message['sender'], message['content'], message.get('private', False), message.get('recipient'))
                await broadcast(message)
            except json.JSONDecodeError:
                logger.warning('Invalid message format.')
            except KeyError:
                logger.warning('Missing key in message.')
    except websockets.ConnectionClosed:
        # Remove the user from the set of connected users
        del connected_users[name]
        logger.info(f'User {name} disconnected.')

async def main():
    async with websockets.serve(handle_connection, 'localhost', 8765):
        logger.info('Server started. Listening for connections...')
        await asyncio.Future()

asyncio.run(main())