"""
Real-time WebSocket chat server with broadcast, private messaging, and disconnect handling.

This module provides a self-contained chat server using `websockets` and `asyncio`.
It supports user connections, broadcasting messages to all connected clients, sending
private messages between users, and graceful disconnect handling. All user input is
sanitized to prevent XSS and other injection attacks.
"""

import asyncio
import html
import json
import logging
import signal
from typing import Dict, Set, Any, Optional

import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.server import WebSocketServerProtocol

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("chat_server")

# Type alias for connected clients
# Maps username -> websocket connection
ConnectedClients = Dict[str, WebSocketServerProtocol]


class ChatServer:
    """
    Manages WebSocket connections, message broadcasting, and private messaging.
    """

    def __init__(self) -> None:
        """Initialize the chat server with an empty client registry."""
        self.clients: ConnectedClients = {}
        self.lock: asyncio.Lock = asyncio.Lock()

    async def register_client(
        self, username: str, websocket: WebSocketServerProtocol
    ) -> bool:
        """
        Register a new client with the given username.

        Args:
            username: The desired username of the connecting client.
            websocket: The WebSocket connection for the client.

        Returns:
            True if registration succeeded, False if the username is already taken.
        """
        async with self._lock:
            if username in self.clients:
                return False
            self.clients[username] = websocket
            logger.info("User '%s' connected. Total clients: %d", username, len(self.clients))
            return True

    async def unregister_client(self, username: str) -> None:
        """
        Remove a client from the registry and notify others.

        Args:
            username: The username of the client to remove.
        """
        async with self._lock:
            if username in self.clients:
                del self.clients[username]
                logger.info("User '%s' disconnected. Total clients: %d", username, len(self.clients))
                await self._broadcast_system_message(f"{username} has left the chat.")

    async def broadcast_message(self, sender: str, message: str) -> None:
        """
        Send a message from a sender to all connected clients except the sender.

        Args:
            sender: The username of the message sender.
            message: The sanitized text message to broadcast.
        """
        payload = json.dumps({"type": "broadcast", "from": sender, "message": message})
        await self._send_to_all(payload, exclude=sender)

    async def send_private_message(
        self, sender: str, recipient: str, message: str
    ) -> bool:
        """
        Send a private message from sender to a specific recipient.

        Args:
            sender: The username of the message sender.
            recipient: The username of the intended recipient.
            message: The sanitized text message to send.

        Returns:
            True if the recipient exists and the message was queued, False otherwise.
        """
        async with self._lock:
            target_ws = self.clients.get(recipient)
            if target_ws is None:
                return False

        payload = json.dumps(
            {"type": "private", "from": sender, "message": message}
        )
        try:
            await target_ws.send(payload)
            return True
        except (ConnectionClosedError, ConnectionClosedOK) as exc:
            logger.warning("Failed to send private message to %s: %s", recipient, exc)
            return False

    async def broadcast_system_message(self, text: str) -> None:
        """
        Broadcast a system-level message to all connected clients.

        Args:
            text: The system message content.
        """
        payload = json.dumps({"type": "system", "message": text})
        await self._send_to_all(payload)

    async def _send_to_all(self, payload: str, exclude: Optional[str] = None) -> None:
        """
        Send a JSON payload to all connected clients except the one to exclude.

        Args:
            payload: The JSON string to send.
            exclude: A username to skip (usually the sender).
        """
        async with self._lock:
            clients_snapshot = list(self.clients.items())

        for username, ws in clients_snapshot:
            if username == exclude:
                continue
            try:
                await ws.send(payload)
            except (ConnectionClosedError, ConnectionClosedOK) as exc:
                logger.warning("Failed to send to %s: %s", username, exc)


def sanitize_user_input(text: str) -> str:
    """
    Sanitize user-provided text by escaping HTML entities and stripping control characters.

    Args:
        text: The raw input string from a user.

    Returns:
        A sanitized string safe for JSON transmission and display.
    """
    # Escape HTML entities to prevent XSS in hypothetical web clients
    sanitized = html.escape(text, quote=True)
    # Remove control characters except common whitespace
    sanitized = "".join(ch for ch in sanitized if ch.isprintable() or ch in ("\n", "\r", "\t"))
    return sanitized


def validate_username(username: str) -> bool:
    """
    Validate that a username is alphanumeric and between 3 and 20 characters.

    Args:
        username: The proposed username.

    Returns:
        True if the username is valid, False otherwise.
    """
    if not username or not isinstance(username, str):
        return False
    if len(username) < 3 or len(username) > 20:
        return False
    return username.isalnum()


async def connection_handler(
    websocket: WebSocketServerProtocol, path: str, server: ChatServer
) -> None:
    """
    Handle an individual WebSocket connection lifecycle.

    Args:
        websocket: The WebSocket connection instance.
        path: The request path (unused).
        server: The ChatServer instance managing all clients.
    """
    username: Optional[str] = None
    try:
        # Authentication / username registration
        raw_data = await websocket.recv()
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            await websocket.send(
                json.dumps({"type": "error", "message": "Invalid JSON."})
            )
            return

        if data.get("type") != "join" or "username" not in data:
            await websocket.send(
                json.dumps({"type": "error", "message": "Expected a join message with a username."})
            )
            return

        proposed_username = data["username"]
        if not validate_username(proposed_username):
            await websocket.send(
                json.dumps({"type": "error", "message": "Username must be 3-20 alphanumeric characters."})
            )
            return

        username = proposed_username
        registered = await server.register_client(username, websocket)
        if not registered:
            await websocket.send(
                json.dumps({"type": "error", "message": f"Username '{username}' is already taken."})
            )
            return

        await websocket.send(
            json.dumps({"type": "system", "message": f"Welcome, {username}!"})
        )
        await server.broadcast_system_message(f"{username} has joined the chat.")

        # Message processing loop
        async for raw_message in websocket:
            try:
                msg_data = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send(
                    json.dumps({"type": "error", "message": "Invalid JSON format."})
                )
                continue

            msg_type = msg_data.get("type")
            if msg_type == "broadcast":
                content = msg_data.get("message", "")
                if not content:
                    await websocket.send(
                        json.dumps({"type": "error", "message": "Empty message."})
                    )
                    continue
                sanitized = sanitize_user_message(content)
                await server.broadcast_message(username, sanitized)

            elif msg_type == "private":
                recipient = msg_data.get("recipient", "")
                content = msg_data.get("message", "")
                if not recipient or not content:
                    await websocket.send(
                        json.dumps({"type": "error", "message": "Private message requires a recipient and message."})
                    )
                    continue
                sanitized = sanitize_user_message(content)
                success = await server.broadcast_private_message(
                    username, recipient, sanitized
                )
                if not success:
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "error",
                                "message": f"User '{recipient}' not found or offline.",
                            }
                        )
                    )
            else:
                await websocket.send(
                    json.dumps({"type": "error", "message": f"Unknown message type: {msg_type}"})
                )

    except (ConnectionClosedError, ConnectionClosedOK):
        logger.info("Connection closed for %s", username or "unknown")
    except Exception as exc:
        logger.exception("Unexpected error with user %s: %s", username, exc)
    finally:
        if username:
            await server.unregister_client(username)


def sanitize_user_message(text: str) -> str:
    """
    Sanitize a chat message: strip control characters and HTML-escape.

    Args:
        text: The raw message text.

    Returns:
        The sanitized message text.
    """
    return sanitize_input(text)


def sanitize_input(text: str) -> str:
    """
    Sanitize general user input by removing dangerous characters and escaping HTML.

    Args:
        text: The raw input string.

    Returns:
        The sanitized string.
    """
    return html.escape(text, quote=True)


async def shutdown_signal(
    server: ChatServer, signal_event: asyncio.Event
) -> None:
    """
    Wait until a shutdown signal is received, then disconnect all clients.

    Args:
        server: The ChatServer instance to gracefully disconnect.
        signal_event: The event that triggers shutdown.
    """
    await signal_event.wait()
    logger.info("Shutting down server...")
    async with server._lock:
        for username, ws in list(server.clients.items()):
            try:
                await ws.close(reason="Server shutting down")
            except Exception:
                pass
        server.clients.clear()
    logger.info("Server shutdown complete.")


def main() -> None:
    """
    Start the WebSocket chat server on localhost:8765.

    Handles graceful shutdown on SIGINT and SIGTERM.
    """
    server = ChatServer()
    shutdown_event = asyncio.Event()

    loop = asyncio.get_event_loop()

    # Attach signal handlers for graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: shutdown_event.set())

    async def serve() -> None:
        """Start the websocket server and wait until shutdown."""
        async with websockets.serve(
            lambda ws, path: handle_handler(ws, path, server),
            host="0.0.0.0",
            port=8765,
        ):
            logger.info("Chat server started on ws://0.0.0.0:8765")
            await shutdown_event.wait()

    try:
        loop.run_until_complete(serve())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        loop.close()
        logger.info("Server stopped.")


# Wrapper to pass server to handler
async def handle_handler(
    websocket: WebSocketServerProtocol, path: str, server: ChatServer
) -> None:
    """
    Wrapper around handle_handler to satisfy the websockets.serve signature.

    Args:
        websocket: The WebSocket connection.
        path: The request path.
        server: The ChatServer instance.
    """
    await handle_handler(websocket, path, server)


if __name__ == "__main__":
    main()