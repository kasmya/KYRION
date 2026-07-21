"""
Real-time Chat Application over WebSockets.

This module implements a WebSocket-based chat server supporting:
- User connection with unique ID assignment
- Broadcast messaging to all connected users
- Private messaging between specific users
- Graceful disconnect handling and cleanup

Security considerations:
- Input validation and sanitization
- Message size limits to prevent DoS
- Exception handling for robust operation
- No sensitive data logging

Requires: websockets (pip install websockets)
"""

import asyncio
import json
import logging
import uuid
from typing import Dict, Set, Optional, Any
from websockets.server import WebSocketServerProtocol, serve
from websockets.exceptions import ConnectionClosed, WebSocketException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
MAX_MESSAGE_SIZE = 1024 * 16  # 16 KB
HEARTBEAT_INTERVAL = 30  # seconds


class ChatServer:
    """WebSocket chat server managing connections and message routing."""

    def __init__(self, host: str = "localhost", port: int = 8765) -> None:
        """
        Initialize chat server.

        Args:
            host: Host address to bind to
            port: Port number to listen on
        """
        self.host = host
        self.port = port
        self.connections: Dict[str, WebSocketServerProtocol] = {}
        self.usernames: Dict[str, str] = {}  # user_id -> username
        self.user_rooms: Dict[str, Set[str]] = {}  # user_id -> set of room names

    async def register_user(self, websocket: WebSocketServerProtocol) -> str:
        """
        Register a new user connection.

        Args:
            websocket: WebSocket connection instance

        Returns:
            Unique user ID assigned to this connection
        """
        user_id = str(uuid.uuid4())
        self.connections[user_id] = websocket
        self.user_rooms[user_id] = set()
        logger.info(f"User connected: {user_id} (total: {len(self.connections)})")
        return user_id

    async def unregister_user(self, user_id: str) -> None:
        """
        Unregister a user and clean up resources.

        Args:
            user_id: ID of user to remove
        """
        if user_id in self.connections:
            del self.connections[user_id]
        if user_id in self.usernames:
            username = self.usernames.pop(user_id)
            logger.info(f"User disconnected: {username} ({user_id})")
        if user_id in self.user_rooms:
            del self.user_rooms[user_id]
        logger.info(f"User removed: {user_id} (remaining: {len(self.connections)})")

    async def set_username(self, user_id: str, username: str) -> bool:
        """
        Set username for a user ID.

        Args:
            user_id: User identifier
            username: Desired username

        Returns:
            True if username was set, False if already taken
        """
        if username in self.usernames.values():
            return False
        self.usernames[user_id] = username
        logger.info(f"User {user_id} set username: {username}")
        return True

    async def broadcast_message(
        self,
        message: dict,
        exclude_user: Optional[str] = None
    ) -> None:
        """
        Broadcast message to all connected users.

        Args:
            message: Message dictionary to send
            exclude_user: Optional user ID to exclude from broadcast
        """
        if not self.connections:
            return

        message_json = json.dumps(message)
        disconnected = []

        for user_id, websocket in self.connections.items():
            if user_id == exclude_user:
                continue
            try:
                await websocket.send(message_json)
            except ConnectionClosed:
                disconnected.append(user_id)
            except WebSocketException as e:
                logger.error(f"Broadcast error to {user_id}: {e}")
                disconnected.append(user_id)

        # Clean up disconnected users
        for user_id in disconnected:
            await self.unregister_user(user_id)

    async def send_private_message(
        self,
        sender_id: str,
        recipient_username: str,
        content: str
    ) -> bool:
        """
        Send private message to specific user by username.

        Args:
            sender_id: ID of sending user
            recipient_username: Username of recipient
            content: Message content

        Returns:
            True if message was delivered, False if recipient not found
        """
        # Find recipient user ID
        recipient_id = None
        for uid, username in self.usernames.items():
            if username == recipient_username:
                recipient_id = uid
                break

        if not recipient_id or recipient_id not in self.connections:
            return False

        sender_username = self.usernames.get(sender_id, "Unknown")
        message = {
            "type": "private_message",
            "sender": sender_username,
            "content": content,
            "timestamp": asyncio.get_event_loop().time()
        }

        try:
            await self.connections[recipient_id].send(json.dumps(message))
            return True
        except (ConnectionClosed, WebSocketException) as e:
            logger.error(f"Private message delivery failed: {e}")
            await self.unregister_user(recipient_id)
            return False

    async def handle_message(self, user_id: str, data: str) -> None:
        """
        Process incoming message from user.

        Args:
            user_id: ID of sending user
            data: Raw message data as string
        """
        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            await self.send_error(user_id, "Invalid JSON format")
            return

        msg_type = message.get("type")
        username = self.usernames.get(user_id, "Anonymous")

        if msg_type == "set_username":
            await self.handle_set_username(user_id, message)
        elif msg_type == "broadcast":
            await self.handle_broadcast(user_id, username, message)
        elif msg_type == "private_message":
            await self.handle_private_message(user_id, message)
        elif msg_type == "join_room":
            await self.handle_join_room(user_id, message)
        elif msg_type == "leave_room":
            await self.handle_leave_room(user_id, message)
        elif msg_type == "room_message":
            await self.handle_room_message(user_id, username, message)
        else:
            await self.send_error(user_id, f"Unknown message type: {msg_type}")

    async def handle_set_username(self, user_id: str, message: dict) -> None:
        """
        Handle username registration request.

        Args:
            user_id: User ID
            message: Message containing desired username
        """
        username = message.get("username", "").strip()
        if not username:
            await self.send_error(user_id, "Username cannot be empty")
            return

        if len(username) > 32:
            await self.send_error(user_id, "Username too long (max 32 chars)")
            return

        # Sanitize username
        username = "".join(c for c in username if c.isalnum() or c in "_-")
        if not username:
            await self.send_error(user_id, "Username contains invalid characters")
            return

        success = await self.set_username(user_id, username)
        if success:
            response = {
                "type": "username_set",
                "username": username,
                "user_id": user_id
            }
            await self.send_to_user(user_id, response)
            # Notify others
            await self.broadcast_message({
                "type": "user_joined",
                "username": username,
                "user_count": len(self.connections)
            }, exclude_user=user_id)
        else:
            await self.send_error(user_id, "Username already taken")

    async def handle_broadcast(
        self,
        user_id: str,
        username: str,
        message: dict
    ) -> None:
        """
        Handle broadcast message to all users.

        Args:
            user_id: Sender's user ID
            username: Sender's username
            message: Message containing content
        """
        content = message.get("content", "").strip()
        if not content:
            await self.send_error(user_id, "Message content cannot be empty")
            return

        if len(content) > 1000:
            await self.send_error(user_id, "Message too long (max 1000 chars)")
            return

        broadcast_msg = {
            "type": "broadcast",
            "sender": username,
            "content": content,
            "timestamp": asyncio.get_event_loop().time()
        }
        await self.broadcast_message(broadcast_msg)

    async def handle_private_message(self, user_id: str, message: dict) -> None:
        """
        Handle private message to specific user.

        Args:
            user_id: Sender's user ID
            message: Message containing recipient and content
        """
        recipient = message.get("recipient", "").strip()
        content = message.get("content", "").strip()

        if not recipient or not content:
            await self.send_error(user_id, "Recipient and content required")
            return

        if len(content) > 1000:
            await self.send_error(user_id, "Message too long (max 1000 chars)")
            return

        delivered = await self.send_private_message(user_id, recipient, content)
        if not delivered:
            await self.send_error(user_id, f"User '{recipient}' not found or offline")
        else:
            # Confirm delivery to sender
            await self.send_to_user(user_id, {
                "type": "private_message_sent",
                "recipient": recipient,
                "content": content
            })

    async def handle_join_room(self, user_id: str, message: dict) -> None:
        """
        Handle user joining a chat room.

        Args:
            user_id: User ID
            message: Message containing room name
        """
        room = message.get("room", "").strip()
        if not room:
            await self.send_error(user_id, "Room name required")
            return

        if len(room) > 64:
            await self.send_error(user_id, "Room name too long (max 64 chars)")
            return

        # Sanitize room name
        room = "".join(c for c in room if c.isalnum() or c in "_-")
        if not room:
            await self.send_error(user_id, "Invalid room name")
            return

        self.user_rooms[user_id].add(room)
        username = self.usernames.get(user_id, "Anonymous")
        logger.info(f"User {username} joined room: {room}")

        await self.send_to_user(user_id, {
            "type": "room_joined",
            "room": room
        })

        # Notify room members
        await self.broadcast_to_room(room, {
            "type": "room_user_joined",
            "room": room,
            "username": username
        }, exclude_user=user_id)

    async def handle_leave_room(self, user_id: str, message: dict) -> None:
        """
        Handle user leaving a chat room.

        Args:
            user_id: User ID
            message: Message containing room name
        """
        room = message.get("room", "").strip()
        if room in self.user_rooms.get(user_id, set()):
            self.user_rooms[user_id].discard(room)
            username = self.usernames.get(user_id, "Anonymous")
            logger.info(f"User {username} left room: {room}")

            await self.send_to_user(user_id, {
                "type": "room_left",
                "room": room
            })

            # Notify room members
            await self.broadcast_to_room(room, {
                "type": "room_user_left",
                "room": room,
                "username": username
            }, exclude_user=user_id)

    async def handle_room_message(
        self,
        user_id: str,
        username: str,
        message: dict
    ) -> None:
        """
        Handle message sent to a chat room.

        Args:
            user_id: Sender's user ID
            username: Sender's username
            message: Message containing room and content
        """
        room = message.get("room", "").strip()
        content = message.get("content", "").strip()

        if not room or not content:
            await self.send_error(user_id, "Room and content required")
            return

        if room not in self.user_rooms.get(user_id, set()):
            await self.send_error(user_id, "You are not a member of this room")
            return

        if len(content) > 1000:
            await self.send_error(user_id, "Message too long (max 1000 chars)")
            return

        room_msg = {
            "type": "room_message",
            "room": room,
            "sender": username,
            "content": content,
            "timestamp": asyncio.get_event_loop().time()
        }
        await self.broadcast_to_room(room, room_msg)

    async def broadcast_to_room(
        self,
        room: str,
        message: dict,
        exclude_user: Optional[str] = None
    ) -> None:
        """
        Broadcast message to all users in a room.

        Args:
            room: Room name
            message: Message to broadcast
            exclude_user: Optional user ID to exclude
        """
        message_json = json.dumps(message)
        disconnected = []

        for user_id, websocket in self.connections.items():
            if user_id == exclude_user:
                continue
            if room in self.user_rooms.get(user_id, set()):
                try:
                    await websocket.send(message_json)
                except ConnectionClosed:
                    disconnected.append(user_id)
                except WebSocketException as e:
                    logger.error(f"Room broadcast error to {user_id}: {e}")
                    disconnected.append(user_id)

        for user_id in disconnected:
            await self.unregister_user(user_id)

    async def send_to_user(self, user_id: str, message: dict) -> bool:
        """
        Send message to specific user.

        Args:
            user_id: Target user ID
            message: Message dictionary

        Returns:
            True if sent successfully, False otherwise
        """
        if user_id not in self.connections:
            return False

        try:
            await self.connections[user_id].send(json.dumps(message))
            return True
        except (ConnectionClosed, WebSocketException) as e:
            logger.error(f"Send to user {user_id} failed: {e}")
            await self.unregister_user(user_id)
            return False

    async def send_error(self, user_id: str, error_message: str) -> None:
        """
        Send error message to user.

        Args:
            user_id: Target user ID
            error_message: Error description
        """
        await self.send_to_user(user_id, {
            "type": "error",
            "message": error_message
        })

    async def handle_connection(
        self,
        websocket: WebSocketServerProtocol,
        path: str
    ) -> None:
        """
        Main connection handler for each WebSocket client.

        Args:
            websocket: WebSocket connection instance
            path: Request path (unused)
        """
        user_id = await self.register_user(websocket)
        logger.info(f"New connection from {websocket.remote_address}")

        try:
            async for message in websocket:
                # Enforce message size limit
                if len(message) > MAX_MESSAGE_SIZE:
                    await self.send_error(user_id, "Message too large")
                    continue

                await self.handle_message(user_id, message)

        except ConnectionClosed:
            logger.info(f"Connection closed normally: {user_id}")
        except WebSocketException as e:
            logger.error(f"WebSocket error for {user_id}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error for {user_id}: {e}")
        finally:
            await self.unregister_user(user_id)
            # Notify others of departure
            username = self.usernames.get(user_id)
            if username:
                await self.broadcast_message({
                    "type": "user_left",
                    "username": username,
                    "user_count": len(self.connections)
                })

    async def start(self) -> None:
        """Start the WebSocket server."""
        logger.info(f"Starting chat server on {self.host}:{self.port}")
        async with serve(
            self.handle_connection,
            self.host,
            self.port,
            ping_interval=HEARTBEAT_INTERVAL,
            ping_timeout=10,
            max_size=MAX_MESSAGE_SIZE
        ):
            await asyncio.Future()  # Run forever


async def main() -> None:
    """Entry point for the chat server."""
    server = ChatServer()
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Server shutting down...")
    except Exception as e:
        logger.exception(f"Server error: {e}")


if __name__ == "__main__":
    asyncio.run(main())