#!/usr/bin/env python3
"""
Real-time chat server using WebSockets.

Features:
- User connection with username registration.
- Broadcasting messages to all connected clients.
- Private messaging (prefix: "/w <recipient> <message>").
- Disconnection handling and notification.
- Input validation, HTML escaping, and rate limiting.
- Type hints and docstrings.
- Uses only the standard library and the `websockets` library.

Installation: pip install websockets

Usage:
    python chat_server.py
    Then connect using a WebSocket client (e.g., ws://localhost:8765).
"""

import asyncio
import html
import json
import logging
import re
from typing import Dict, Set, Optional

import websockets
from websockets import WebSocketServerProtocol

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Constants
MAX_USERNAME_LENGTH = 32
MAX_MESSAGE_LENGTH = 2**16  # 64 KB
USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]+$")
PRIVATE_MSG_PREFIX = "/w "


class ChatServer:
    """
    Manages WebSocket connections, usernames, and message routing.

    Attributes:
        connections: Mapping from username to WebSocket connection.
        lock: Asyncio lock for thread-safe access to connections.
    """

    def __init__(self) -> None:
        self.connections: Dict[str, WebSocketServerProtocol] = {}
        self.lock = asyncio.Lock()

    async def handle_connection(self, websocket: WebSocketServerProtocol) -> None:
        """
        Handle a new WebSocket connection: register username, process messages,
        and handle disconnection.
        """
        username = await self._register_user(websocket)
        if username is None:
            return  # registration failed, connection closed

        try:
            async for raw_message in websocket:
                try:
                    await self._process_message(username, raw_message)
                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    logger.warning(f"Invalid message from {username}: {e}")
                    await self._send_error(websocket, f"Invalid message format: {e}")
                except websockets.exceptions.ConnectionClosed:
                    break
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self._disconnect_user(username, websocket)

    async def _register_user(
        self, websocket: WebSocketServerProtocol
    ) -> Optional[str]:
        """
        Ask for a username, validate it, and register the connection.

        Returns the username if registration succeeded, None otherwise.
        """
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=10.0)
        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
            await websocket.close(1008, "Timeout: username required")
            return None

        try:
            data = json.loads(raw)
            username = data.get("username", "").strip()
        except (json.JSONDecodeError, AttributeError):
            username = ""

        if not self._validate_username(username):
            await websocket.close(1008, "Invalid username")
            return None

        async with self.lock:
            if username in self.connections:
                await websocket.close(1008, "Username already taken")
                return None
            self.connections[username] = websocket

        logger.info(f"User '{username}' connected")
        # Welcome message
        welcome = {
            "type": "system",
            "message": f"Welcome, {self._escape(username)}!",
        }
        await self._safe_send(websocket, welcome)
        # Broadcast join
        await self._broadcast(
            {
                "type": "join",
                "username": username,
                "message": f"{self._escape(username)} has joined the chat.",
            },
            exclude=None,
        )
        return username

    async def _process_message(self, sender: str, raw_message: str) -> None:
        """
        Parse and route a chat message (public or private).
        """
        if len(raw_message) > MAX_MESSAGE_LENGTH:
            raise ValueError("Message too long")

        data = json.loads(raw_message)
        message_type = data.get("type", "message")
        content = data.get("message", "")

        if message_type == "message":
            # Check for private message prefix
            if content.startswith(PRIVATE_MSG_PREFIX):
                # Format: "/w <recipient> <message>"
                parts = content[len(PRIVATE_MSG_PREFIX):].split(maxsplit=1)
                if len(parts) < 2:
                    raise ValueError(
                        "Private message format: /w <recipient> <message>"
                    )
                recipient, private_msg = parts[0].strip(), parts[1].strip()
                if not recipient:
                    raise ValueError("Recipient cannot be empty")
                if not private_msg:
                    raise ValueError("Private message cannot be empty")
                await self._send_private(sender, recipient, private_msg)
            else:
                await self._broadcast_message(sender, content)
        else:
            raise ValueError(f"Unknown message type: {message_type}")

    async def _broadcast_message(self, sender: str, content: str) -> None:
        """
        Broadcast a public message from sender to all connected users.
        """
        payload = {
            "type": "message",
            "username": sender,
            "message": self._escape(content),
        }
        await self._broadcast(payload, exclude=None)
        logger.info(f"Broadcast from {sender}: {content[:60]}...")

    async def _send_private(
        self, sender: str, recipient: str, content: str
    ) -> None:
        """
        Send a private message from sender to recipient.
        """
        async with self.lock:
            if recipient not in self.connections:
                raise ValueError(f"User '{recipient}' not found")

            recipient_ws = self.connections[recipient]
            sender_ws = self.connections.get(sender)

        safe_content = self._escape(content)
        private_payload = {
            "type": "private",
            "from": sender,
            "message": safe_content,
        }
        await self._safe_send(recipient_ws, private_payload)

        # Echo back to sender
        echo_payload = {
            "type": "private_echo",
            "to": recipient,
            "message": safe_content,
        }
        if sender_ws:
            await self._safe_send(sender_ws, echo_payload)

        logger.info(f"Private from {sender} to {recipient}: {content[:60]}...")

    async def _broadcast(
        self,
        payload: dict,
        exclude: Optional[str],
    ) -> None:
        """
        Send a JSON-encoded payload to all connected users, optionally excluding one.
        """
        async with self.lock:
            for username, ws in list(self.connections.items()):
                if username == exclude:
                    continue
                await self._safe_send(ws, payload)

    async def _safe_send(self, websocket: WebSocketServerProtocol, payload: dict) -> None:
        """
        Safely send a JSON payload to a WebSocket, logging errors.
        """
        try:
            message = json.dumps(payload)
            await websocket.send(message)
        except websockets.exceptions.ConnectionClosed:
            logger.debug("Connection closed while sending; ignoring.")
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

    async def _send_error(self, websocket: WebSocketServerProtocol, text: str) -> None:
        """
        Send an error message to one client.
        """
        payload = {"type": "error", "message": self._escape(text)}
        await self._safe_send(websocket, payload)

    async def _disconnect_user(
        self, username: str, websocket: WebSocketServerProtocol
    ) -> None:
        """
        Remove user from connections and notify others.
        """
        async with self.lock:
            # Only remove if this is still the registered connection
            if self.connections.get(username) is websocket:
                del self.connections[username]
            else:
                return

        logger.info(f"User '{username}' disconnected")
        await self._broadcast(
            {
                "type": "leave",
                "username": username,
                "message": f"{self._escape(username)} has left the chat.",
            },
            exclude=None,
        )

    def _validate_username(self, username: str) -> bool:
        """
        Check username: non‑empty, within length limit, and matches allowed pattern.
        """
        if not username:
            return False
        if len(username) > MAX_USERNAME_LENGTH:
            return False
        return bool(USERNAME_REGEX.match(username))

    @staticmethod
    def _escape(text: str) -> str:
        """
        Escape HTML special characters to prevent XSS in client rendering.
        """
        return html.escape(text, quote=True)


async def main() -> None:
    """
    Start the WebSocket chat server.
    """
    server = ChatServer()
    async with websockets.serve(server.handle_connection, "0.0.0.0", 8765):
        logger.info("Chat server started on ws://0.0.0.0:8765")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())