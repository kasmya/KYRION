"""
Real-time WebSocket Chat Application

This module implements a WebSocket-based chat server supporting:
- User connection and authentication
- Broadcast messaging to all connected users
- Private messaging between users
- Graceful disconnect handling

Security considerations:
- Input validation and sanitization
- Rate limiting per connection
- Secure message parsing
- No code execution or eval
- Proper error handling without information leakage
"""

import asyncio
import json
import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, Any

import websockets
from websockets.server import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosed, WebSocketException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
MAX_MESSAGE_LENGTH = 4096
MAX_USERNAME_LENGTH = 32
MIN_USERNAME_LENGTH = 1
MESSAGE_RATE_LIMIT = 30  # messages per second per user
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


@dataclass
class User:
    """Represents a connected chat user."""
    user_id: str
    username: str
    websocket: WebSocketServerProtocol
    connected_at: float
    message_count: int = 0
    last_message_time: float = 0.0


@dataclass
class ChatRoom:
    """Manages chat users and message routing."""
    users: Dict[str, User] = field(default_factory=dict)
    username_to_id: Dict[str, str] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def add_user(self, user: User) -> bool:
        """
        Add a user to the chat room.

        Args:
            user: User object to add

        Returns:
            True if added successfully, False if username taken
        """
        async with self._lock:
            if user.username in self.username_to_id:
                return False
            self.users[user.user_id] = user
            self.username_to_id[user.username] = user.user_id
            return True

    async def remove_user(self, user_id: str) -> Optional[User]:
        """
        Remove a user from the chat room.

        Args:
            user_id: ID of user to remove

        Returns:
            Removed User object or None if not found
        """
        async with self._lock:
            user = self.users.pop(user_id, None)
            if user:
                self.username_to_id.pop(user.username, None)
            return user

    async def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        async with self._lock:
            return self.users.get(user_id)

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        async with self._lock:
            user_id = self.username_to_id.get(username)
            if user_id:
                return self.users.get(user_id)
            return None

    async def get_all_users(self) -> list[User]:
        """Get list of all connected users."""
        async with self._lock:
            return list(self.users.values())

    async def broadcast(self, message: dict, exclude_user_id: Optional[str] = None) -> None:
        """
        Broadcast message to all connected users.

        Args:
            message: Message dictionary to send
            exclude_user_id: Optional user ID to exclude from broadcast
        """
        async with self._lock:
            users = list(self.users.values())

        message_json = json.dumps(message)
        for user in users:
            if user.user_id != exclude_user_id:
                try:
                    await user.websocket.send(message_json)
                except (ConnectionClosed, WebSocketException) as e:
                    logger.warning(f"Failed to send to {user.username}: {e}")

    async def send_private(self, from_user: User, to_username: str, content: str) -> bool:
        """
        Send private message to specific user.

        Args:
            from_user: Sender user object
            to_username: Target username
            content: Message content

        Returns:
            True if delivered, False if user not found
        """
        target_user = await self.get_user_by_username(to_username)
        if not target_user:
            return False

        message = {
            "type": "private_message",
            "from": from_user.username,
            "to": to_username,
            "content": content,
            "timestamp": asyncio.get_event_loop().time()
        }

        try:
            await target_user.websocket.send(json.dumps(message))
            return True
        except (ConnectionClosed, WebSocketException) as e:
            logger.warning(f"Failed to send private message to {to_username}: {e}")
            return False


def validate_username(username: str) -> bool:
    """
    Validate username format and length.

    Args:
        username: Username string to validate

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(username, str):
        return False
    if not (MIN_USERNAME_LENGTH <= len(username) <= MAX_USERNAME_LENGTH):
        return False
    return bool(USERNAME_PATTERN.match(username))


def validate_message_content(content: str) -> bool:
    """
    Validate message content.

    Args:
        content: Message content string

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(content, str):
        return False
    if len(content) > MAX_MESSAGE_LENGTH:
        return False
    if len(content) == 0:
        return False
    return True


def sanitize_input(text: str) -> str:
    """
    Sanitize input text by removing control characters.

    Args:
        text: Input text

    Returns:
        Sanitized text
    """
    if not isinstance(text, str):
        return ""
    # Remove control characters except newline and tab
    return "".join(char for char in text if ord(char) >= 32 or char in "\n\t")


async def handle_rate_limit(user: User) -> bool:
    """
    Check and update rate limit for user.

    Args:
        user: User object

    Returns:
        True if under limit, False if rate limited
    """
    current_time = asyncio.get_event_loop().time()
    
    # Reset counter if more than 1 second passed
    if current_time - user.last_message_time > 1.0:
        user.message_count = 0
        user.last_message_time = current_time
    
    user.message_count += 1
    return user.message_count <= MESSAGE_RATE_LIMIT


async def parse_message(raw_message: str) -> Optional[dict]:
    """
    Parse and validate incoming message.

    Args:
        raw_message: Raw message string from websocket

    Returns:
        Parsed message dict or None if invalid
    """
    try:
        message = json.loads(raw_message)
    except json.JSONDecodeError:
        logger.warning("Received invalid JSON")
        return None

    if not isinstance(message, dict):
        return None

    msg_type = message.get("type")
    if msg_type not in ("broadcast", "private", "ping"):
        logger.warning(f"Unknown message type: {msg_type}")
        return None

    return message


async def handle_connection(websocket: WebSocketServerProtocol, room: ChatRoom) -> None:
    """
    Handle a single WebSocket connection lifecycle.

    Args:
        websocket: WebSocket connection
        room: ChatRoom instance for user management
    """
    user_id = str(uuid.uuid4())
    user: Optional[User] = None
    authenticated = False

    try:
        # Wait for authentication message
        auth_message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
        auth_data = await parse_message(auth_message)
        
        if not auth_data or auth_data.get("type") != "auth":
            await websocket.send(json.dumps({
                "type": "error",
                "message": "Authentication required"
            }))
            return

        username = sanitize_input(auth_data.get("username", ""))
        
        if not validate_username(username):
            await websocket.send(json.dumps({
                "type": "error",
                "message": "Invalid username format"
            }))
            return

        user = User(
            user_id=user_id,
            username=username,
            websocket=websocket,
            connected_at=asyncio.get_event_loop().time()
        )

        # Try to add user to room
        if not await room.add_user(user):
            await websocket.send(json.dumps({
                "type": "error",
                "message": "Username already taken"
            }))
            return

        authenticated = True
        logger.info(f"User connected: {username} ({user_id})")

        # Send welcome message
        await websocket.send(json.dumps({
            "type": "welcome",
            "user_id": user_id,
            "username": username,
            "users": [u.username for u in await room.get_all_users()]
        }))

        # Notify others
        await room.broadcast({
            "type": "user_joined",
            "username": username,
            "users": [u.username for u in await room.get_all_users()]
        }, exclude_user_id=user_id)

        # Main message loop
        async for raw_message in websocket:
            if not await handle_rate_limit(user):
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Rate limit exceeded"
                }))
                continue

            message = await parse_message(raw_message)
            if not message:
                continue

            msg_type = message.get("type")

            if msg_type == "broadcast":
                content = sanitize_input(message.get("content", ""))
                if not validate_message_content(content):
                    continue

                await room.broadcast({
                    "type": "broadcast",
                    "from": user.username,
                    "content": content,
                    "timestamp": asyncio.get_event_loop().time()
                })

            elif msg_type == "private":
                target_username = sanitize_input(message.get("to", ""))
                content = sanitize_input(message.get("content", ""))

                if not validate_username(target_username):
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Invalid target username"
                    }))
                    continue

                if not validate_message_content(content):
                    continue

                if target_username == user.username:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Cannot send private message to yourself"
                    }))
                    continue

                delivered = await room.send_private(user, target_username, content)
                if not delivered:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": f"User '{target_username}' not found"
                    }))

            elif msg_type == "ping":
                await websocket.send(json.dumps({"type": "pong"}))

    except asyncio.TimeoutError:
        logger.warning(f"Authentication timeout for {user_id}")
    except ConnectionClosed:
        logger.info(f"Connection closed for {user_id}")
    except WebSocketException as e:
        logger.error(f"WebSocket error for {user_id}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error for {user_id}: {e}")
    finally:
        if authenticated and user:
            await room.remove_user(user.user_id)
            logger.info(f"User disconnected: {user.username} ({user_id})")
            await room.broadcast({
                "type": "user_left",
                "username": user.username,
                "users": [u.username for u in await room.get_all_users()]
            })


async def main(host: str = "0.0.0.0", port: int = 8765) -> None:
    """
    Start the WebSocket chat server.

    Args:
        host: Host address to bind to
        port: Port number to listen on
    """
    room = ChatRoom()
    
    logger.info(f"Starting chat server on {host}:{port}")
    
    async with websockets.serve(
        lambda ws: handle_connection(ws, room),
        host,
        port,
        ping_interval=20,
        ping_timeout=10,
        max_size=MAX_MESSAGE_LENGTH * 2
    ):
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.exception(f"Server error: {e}")
        raise