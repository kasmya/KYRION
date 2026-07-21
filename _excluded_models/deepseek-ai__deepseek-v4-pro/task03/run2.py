"""
Real-time chat application over WebSockets.

This module provides a WebSocket-based chat server with support for
user connections, broadcast messaging, private messaging, and
disconnect handling. It uses asyncio and the websockets library.
"""

import asyncio
import json
import logging
import ssl
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.server import WebSocketServerProtocol

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("chat-server")

# Maximum allowed message size (1 MB)
MAX_MESSAGE_SIZE = 1_048_576
# Allowed message types
VALID_MESSAGE_TYPES: Set[str] = {"broadcast", "private", "system"}


@dataclass
class User:
    """Represents a connected chat user."""

    username: str
    websocket: WebSocketServerProtocol
    ip_address: str


class ChatServer:
    """
    Manages WebSocket connections and message routing for the chat application.

    Handles user connections, disconnections, broadcast messaging,
    and private messaging with security considerations.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8765) -> None:
        """
        Initialize the chat server.

        Args:
            host: The host address to bind the server to.
            port: The port number to listen on.
        """
        self.host: str = host
        self.port: int = port
        self.users: Dict[str, User] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def _validate_username(self, username: str) -> str:
        """
        Validate and sanitize a username.

        Args:
            username: The proposed username.

        Returns:
            The sanitized username.

        Raises:
            ValueError: If the username is invalid.
        """
        if not username or not isinstance(username, str):
            raise ValueError("Username must be a non-empty string")

        # Strip whitespace and limit length
        sanitized = username.strip()[:30]
        if not sanitized:
            raise ValueError("Username cannot be empty after sanitization")

        # Check for disallowed characters
        if any(char in sanitized for char in ['"', "'", "<", ">", "&", "/", "\\"]):
            raise ValueError("Username contains disallowed characters")

        return sanitized

    async def _validate_message_content(self, content: str) -> str:
        """
        Validate and sanitize message content.

        Args:
            content: The message content.

        Returns:
            Sanitized message content.

        Raises:
            ValueError: If the content is invalid.
        """
        if not isinstance(content, str):
            raise ValueError("Message content must be a string")

        # Limit message length
        sanitized = content.strip()[:5000]
        if not sanitized:
            raise ValueError("Message content cannot be empty")

        return sanitized

    async def broadcast(self, message: str, sender: User) -> None:
        """
        Send a message to all connected users except the sender.

        Args:
            message: The formatted message to broadcast.
            sender: The user sending the broadcast.
        """
        payload = json.dumps({"type": "broadcast", "from": sender.username, "message": message})

        async with self._lock:
            disconnected: Set[str] = set()
            for username, user in self.users.items():
                if username == sender.username:
                    continue
                try:
                    await asyncio.wait_for(
                        user.websocket.send(payload),
                        timeout=5.0,
                    )
                except (asyncio.TimeoutError, ConnectionClosed, WebSocketException) as exc:
                    logger.warning("Failed to send to %s: %s", username, exc)
                    disconnected.add(username)

            # Clean up disconnected users
            for username in disconnected:
                await self._disconnect_user(username)

    async def send_private(
        self, sender: User, recipient_username: str, message: str
    ) -> None:
        """
        Send a private message to a specific user.

        Args:
            sender: The user sending the private message.
            recipient_username: The intended recipient's username.
            message: The private message content.

        Raises:
            ValueError: If the recipient is not found.
        """
        async with self._lock:
            recipient = self.users.get(recipient_username)
            if recipient is None:
                raise ValueError(f"User '{recipient_username}' not found")

        payload = json.dumps(
            {
                "type": "private",
                "from": sender.username,
                "to": recipient_username,
                "message": message,
            }
        )

        try:
            await asyncio.wait_for(
                recipient.websocket.send(payload),
                timeout=5.0,
            )
        except (asyncio.TimeoutError, ConnectionClosed, WebSocketException) as exc:
            logger.warning("Failed to send private message to %s: %s", recipient_username, exc)
            await self._disconnect_user(recipient_username)
            raise ValueError(f"Failed to deliver message to {recipient_username}") from exc

    async def _disconnect_user(self, username: str) -> None:
        """
        Remove a user and notify others of their departure.

        Args:
            username: The username of the departing user.
        """
        async with self._lock:
            user = self.users.pop(username, None)
            if user is None:
                return

        logger.info("User disconnected: %s", username)
        notify = json.dumps({"type": "system", "message": f"{username} has left the chat"})
        async with self._lock:
            for u in self.users.values():
                try:
                    await asyncio.wait_for(u.websocket.send(notify), timeout=2.0)
                except (asyncio.TimeoutError, ConnectionClosed, WebSocketException):
                    pass

    async def _handle_message(self, user: User, raw_message: str) -> None:
        """
        Process an incoming message from a connected user.

        Args:
            user: The user who sent the message.
            raw_message: The raw JSON message string.

        Raises:
            ValueError: If the message format or content is invalid.
        """
        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON format") from exc

        if not isinstance(data, dict):
            raise ValueError("Message must be a JSON object")

        msg_type = data.get("type")
        if msg_type not in ALLOWED_MESSAGE_TYPES:
            raise ValueError(f"Invalid message type: {msg_type}")

        content = data.get("message", "")
        content = await self._validate_message_content(content)

        if msg_type == "broadcast":
            await self.broadcast(content, user)
        elif msg_type == "private":
            recipient = data.get("to", "")
            if not recipient:
                raise ValueError("Private message missing 'to' field")
            recipient = await self.register_username(recipient)
            await self.send_private(user, recipient, content)

    async def handle_connection(self, websocket: WebSocketServerProtocol) -> None:
        """
        Manage a single client WebSocket connection.

        Handles the initial handshake (username registration), processes
        incoming messages, and manages disconnection.

        Args:
            websocket: The WebSocket connection instance.
        """
        user: Optional[User] = None
        try:
            # Receive initial handshake with username
            try:
                init_msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            except asyncio.TimeoutError:
                await websocket.close(1008, "Timeout waiting for username")
                return

            try:
                init_data = json.loads(init_msg)
            except json.JSONDecodeError:
                await websocket.close(1007, "Invalid handshake format")
                return

            username = init_data.get("username", "")
            try:
                username = await self.register_username(username)
            except ValueError as exc:
                await websocket.send(json.dumps({"type": "system", "error": str(exc)}))
                await websocket.close(1008, str(exc))
                return

            # Check for duplicate username
            async with self._lock:
                if username in self.users:
                    await websocket.send(
                        json.dumps({"type": "system", "error": "Username already taken"})
                    )
                    await websocket.close(1008, "Username taken")
                    return

                # Create user and add to active users
                ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
                user = User(username=username, websocket=websocket, ip_address=ip)
                self.users[username] = user

            logger.info("User connected: %s from %s", username, ip)

            # Notify all about new user
            join_notification = json.dumps(
                {"type": "system", "message": f"{username} has joined the chat"}
            )
            async with self._lock:
                for u in self.users.values():
                    if u.username != username:
                        try:
                            await asyncio.wait_for(u.websocket.send(join_notification), timeout=2.0)
                        except (asyncio.TimeoutError, ConnectionClosed, WebSocketException):
                            pass

            # Send welcome message to the new user
            await websocket.send(
                json.dumps({"type": "system", "message": f"Welcome, {username}!"})
            )

            # Main message loop
            async for raw_message in websocket:
                if len(raw_message) > MAX_MESSAGE_SIZE:
                    await websocket.send(
                        json.dumps({"type": "system", "error": "Message too large"})
                    )
                    continue

                try:
                    await self._handle_message(user, raw_message)
                except ValueError as exc:
                    error_msg = json.dumps({"type": "system", "error": str(exc)})
                    try:
                        await websocket.send(error_msg)
                    except (ConnectionClosed, WebSocketException):
                        break

        except ConnectionClosed:
            logger.info("Connection closed for %s", user.username if user else "unknown")
        except WebSocketException as exc:
            logger.error("WebSocket error: %s", exc)
        except Exception as exc:
            logger.exception("Unexpected error handling connection: %s", exc)
        finally:
            if user is not None:
                await self._disconnect_user(user.username)

    async def start(self) -> None:
        """
        Start the WebSocket chat server.

        Binds to the configured host and port and serves indefinitely.
        """
        logger.info("Starting chat server on %s:%d", self.host, self.port)
        try:
            async with websockets.serve(
                self.handle_connection,
                self.host,
                self.port,
                max_size=MAX_MESSAGE_SIZE,
                compression=None,  # Disable compression to prevent CRIME/BREACH
                origins=None,  # Allow all origins (adjust in production)
                ping_interval=20,
                ping_timeout=20,
            ):
                logger.info("Chat server is running")
                await asyncio.Future()  # run forever
        except OSError as exc:
            logger.critical("Failed to bind to %s:%d: %s", self.host, self.port, exc)
            raise
        except Exception as exc:
            logger.critical("Server error: %s", exc)
            raise


def main() -> None:
    """Entry point for the chat server."""
    server = ChatServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Server shut down by user")
    except Exception as exc:
        logger.critical("Fatal error: %s", exc)


if __name__ == "__main__":
    main()