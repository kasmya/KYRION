"""
Real-time WebSocket chat application with broadcast and private messaging.

Provides a fully asynchronous chat server using the websockets library,
supporting user connection, disconnection, broadcast messaging, and
private messaging. All public functions include type hints and docstrings.
Error handling and security best practices are applied throughout.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.server import WebSocketServerProtocol

# Configure module-level logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Maximum message size to prevent memory exhaustion (64 KiB)
MAX_MESSAGE_SIZE = 64 * 1024

# Maximum allowed username length
MAX_USERNAME_LENGTH = 32


class ChatServer:
    """
    Manages WebSocket connections, user registry, and message routing.

    Attributes:
        users: A dictionary mapping WebSocket connections to their usernames.
        lock: An asyncio lock to protect concurrent access to the users dict.
    """

    def __init__(self) -> None:
        """Initialize the chat server with an empty user registry."""
        self.users: Dict[WebSocketServerProtocol, str] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def register(self, websocket: WebSocketServerProtocol, username: str) -> None:
        """
        Register a new user after validating the username.

        Args:
            websocket: The WebSocket connection to register.
            username: The requested username.

        Raises:
            ValueError: If the username is invalid or already taken.
        """
        username = username.strip()
        if not username:
            raise ValueError("Username cannot be empty.")
        if len(username) > MAX_USERNAME_LENGTH:
            raise ValueError(
                f"Username must be at most {MAX_USERNAME_LENGTH} characters."
            )
        # Reject names that could be confused with system commands
        if username.startswith("/"):
            raise ValueError("Username cannot start with '/'.")

        async with self._lock:
            if username in self.users.values():
                raise ValueError(f"Username '{username}' is already taken.")
            self.users[websocket] = username

    async def unregister(self, websocket: WebSocketServerProtocol) -> Optional[str]:
        """
        Remove a user and return their username if present.

        Args:
            websocket: The WebSocket connection to unregister.

        Returns:
            The username that was removed, or None if the connection was not registered.
        """
        async with self._lock:
            return self.users.pop(websocket, None)

    async def get_username(
        self, websocket: WebSocketServerProtocol
    ) -> Optional[str]:
        """
        Retrieve the username associated with a WebSocket connection.

        Args:
            websocket: The WebSocket connection.

        Returns:
            The username, or None if the connection is not registered.
        """
        async with self._lock:
            return self.users.get(websocket)

    async def get_connection_by_username(
        self, username: str
    ) -> Optional[WebSocketServerProtocol]:
        """
        Find a WebSocket connection by username.

        Args:
            username: The username to look up.

        Returns:
            The WebSocket connection if found, else None.
        """
        async with self._lock:
            for ws, name in self.users.items():
                if name == username:
                    return ws
        return None

    async def broadcast(self, message: str, sender: WebSocketServerProtocol) -> None:
        """
        Send a message to all connected users except the sender.

        Args:
            message: The message to broadcast.
            sender: The WebSocket connection of the sender.
        """
        sender_username = await self.get_username(sender)
        if sender_username is None:
            logger.warning("Broadcast attempted by unregistered connection.")
            return

        payload = json.dumps(
            {"type": "broadcast", "from": sender_username, "message": message}
        )

        async with self._lock:
            recipients = [
                conn for conn in self.users if conn is not sender
            ]

        if recipients:
            await asyncio.gather(
                *[self._safe_send(conn, payload) for conn in recipients],
                return_exceptions=True,
            )

    async def send_private(
        self,
        sender: WebSocketServerProtocol,
        recipient_username: str,
        message: str,
    ) -> None:
        """
        Send a private message to a specific user.

        Args:
            sender: The WebSocket connection of the sender.
            recipient_username: The intended recipient's username.
            message: The private message text.

        Raises:
            ValueError: If the recipient is not found.
        """
        sender_username = await self.get_username(sender)
        if sender_username is None:
            raise ValueError("Sender is not registered.")

        recipient_conn = await self.get_connection_by_username(recipient_username)
        if recipient_conn is None:
            raise ValueError(f"User '{recipient_username}' not found.")

        payload = {
            "type": "private",
            "from": sender_username,
            "to": recipient_username,
            "message": message,
        }
        await self._safe_send(recipient_conn, json.dumps(payload))

    async def _safe_send(
        self, websocket: WebSocketServerProtocol, message: str
    ) -> None:
        """
        Send a message over a WebSocket connection with error handling.

        Args:
            websocket: The target WebSocket connection.
            message: The JSON-encoded message to send.
        """
        try:
            await websocket.send(message)
        except ConnectionClosed:
            logger.info(
                "Failed to send to %s: connection closed.",
                await self.get_username(websocket) or "unknown",
            )
            await self.unregister(websocket)
        except WebSocketException as exc:
            logger.error("WebSocket error while sending: %s", exc)
            await self.unregister(websocket)


async def _safe_send(websocket: WebSocketServerProtocol, message: str) -> None:
    """Standalone safe-send helper used internally before registration."""
    try:
        await websocket.send(message)
    except ConnectionClosed:
        logger.info("Connection closed before registration completed.")
    except WebSocketException as exc:
        logger.error("WebSocket error during pre-registration send: %s", exc)


async def handle_connection(
    websocket: WebSocketServerProtocol, chat: ChatServer
) -> None:
    """
    Handle a single client connection lifecycle.

    Args:
        websocket: The incoming WebSocket connection.
        chat: The shared ChatServer instance.
    """
    # --- Registration phase ---
    try:
        raw_message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
    except asyncio.TimeoutError:
        await _safe_send(websocket, json.dumps({"error": "Registration timed out."}))
        return
    except ConnectionClosed:
        return
    except WebSocketException:
        return

    try:
        data = json.loads(raw_message)
    except json.JSONDecodeError:
        await _safe_send(websocket, json.dumps({"error": "Invalid JSON."}))
        return

    if not isinstance(data, dict) or data.get("type") != "register":
        await _safe_send(websocket, json.dumps({"error": "Expected registration."}))
        return

    username = data.get("username")
    if not isinstance(username, str):
        await _safe_send(websocket, json.dumps({"error": "Username must be a string."}))
        return

    try:
        await chat.register(websocket, username)
    except ValueError as exc:
        await _safe_send(websocket, json.dumps({"error": str(exc)}))
        return

    # Confirm registration
    await _safe_send(websocket, json.dumps({"type": "registered", "username": username}))
    logger.info("User '%s' connected.", username)

    # Notify others
    join_msg = json.dumps({"type": "system", "message": f"{username} joined."})
    async with chat._lock:
        others = [conn for conn in chat.users if conn is not websocket]
    await asyncio.gather(
        *[_safe_send(conn, join_msg) for conn in others], return_exceptions=True
    )

    # --- Message loop ---
    try:
        async for raw in websocket:
            # Enforce message size limit
            if len(raw) > MAX_MESSAGE_SIZE:
                await _safe_send(
                    websocket,
                    json.dumps({"error": "Message too large."}),
                )
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await _safe_send(
                    websocket, json.dumps({"error": "Invalid JSON."})
                )
                continue

            if not isinstance(data, dict):
                await _safe_send(
                    websocket, json.dumps({"error": "Message must be a JSON object."})
                )
                continue

            msg_type = data.get("type")
            if msg_type == "broadcast":
                text = data.get("message")
                if not isinstance(text, str) or not text.strip():
                    await _safe_send(
                        websocket, json.dumps({"error": "Message cannot be empty."})
                    )
                    continue
                await chat.broadcast(text.strip(), websocket)

            elif msg_type == "private":
                recipient = data.get("to")
                text = data.get("message")
                if not isinstance(recipient, str) or not isinstance(text, str):
                    await _safe_send(
                        websocket,
                        json.dumps({"error": "Invalid private message format."}),
                    )
                    continue
                if not text.strip():
                    await _safe_send(
                        websocket, json.dumps({"error": "Message cannot be empty."})
                    )
                    continue
                try:
                    await chat.send_private(websocket, recipient, text.strip())
                except ValueError as exc:
                    await _safe_send(
                        websocket, json.dumps({"error": str(exc)})
                    )

            else:
                await _safe_send(
                    websocket,
                    json.dumps({"error": f"Unknown message type: {msg_type}"}),
                )
    except ConnectionClosed:
        pass
    finally:
        # --- Disconnect handling ---
        unregistered_name = await chat.unregister(websocket)
        if unregistered_name:
            logger.info("User '%s' disconnected.", unregistered_name)
            leave_msg = json.dumps(
                {"type": "leave", "message": f"{unregistered_name} left."}
            )
            async with chat_lock:
                remaining = list(chat.users.keys())
            await asyncio.gather(
                *[_safe_send(conn, leave_msg) for conn in remaining],
                return_exceptions=True,
            )


async def main(host: str = "localhost", port: int = 8765) -> None:
    """
    Start the WebSocket chat server.

    Args:
        host: The network interface to bind to.
        port: The port to listen on.
    """
    chat = ChatServer()
    logger.info("Starting chat server on %s:%d", host, port)
    async with websockets.serve(
        lambda ws: handle_connection(ws, chat),
        host,
        port,
        max_size=MAX_MESSAGE_SIZE,
    ):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server shut down.")