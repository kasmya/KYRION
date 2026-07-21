"""
chat_server.py

A simple real-time chat server using WebSockets.

Features:
- User registration with unique usernames.
- Broadcast messages to all connected users.
- Private messages between two users.
- Graceful handling of disconnects and errors.

Security considerations:
- Username validation (alphanumeric, length limits).
- Message size limit (max 2048 bytes).
- JSON schema validation.
- Exception handling for malformed data and connection issues.

Dependencies:
- websockets (https://pypi.org/project/websockets/)
- Python 3.9+

Run the server:
    python -m chat_server
"""

import asyncio
import json
import logging
import re
from typing import Dict, Set

import websockets
from websockets import WebSocketServerProtocol, ConnectionClosedError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# Global state (protected by asyncio locks)
_CONNECTED_USERS: Dict[str, WebSocketServerProtocol] = {}
_USERS_LOCK = asyncio.Lock()

# Constants
MAX_MESSAGE_SIZE = 2_048  # bytes
USERNAME_REGEX = re.compile(r"^[A-Za-z0-9_]{3,20}$")


async def register_user(username: str, ws: WebSocketServerProtocol) -> None:
    """
    Register a new user.

    Args:
        username: Desired username (must be validated before calling).
        ws: WebSocket connection associated with the user.

    Raises:
        ValueError: If the username is already taken.
    """
    async with _USERS_LOCK:
        if username in _CONNECTED_USERS:
            raise ValueError(f"Username '{username}' is already in use.")
        _CONNECTED_USERS[username] = ws
        logging.info("User registered: %s", username)


async def unregister_user(username: str) -> None:
    """
    Remove a user from the connected users list and broadcast the departure.

    Args:
        username: The username to remove.
    """
    async with _USERS_LOCK:
        ws = _CONNECTED_USERS.pop(username, None)
        if ws:
            logging.info("User unregistered: %s", username)
            await broadcast_system_message(f"{username} has left the chat.")


async def broadcast_system_message(message: str) -> None:
    """
    Send a system message to all connected users.

    Args:
        message: Text to broadcast.
    """
    await _broadcast({"type": "system", "message": message})


async def broadcast_user_message(sender: str, message: str) -> None:
    """
    Broadcast a user message to all connected users except the sender.

    Args:
        sender: Username of the message origin.
        message: Text to broadcast.
    """
    await _broadcast(
        {"type": "broadcast", "from": sender, "message": message},
        exclude={sender},
    )


async def send_private_message(sender: str, recipient: str, message: str) -> None:
    """
    Send a private message from one user to another.

    Args:
        sender: Username of the message origin.
        recipient: Target username.
        message: Text to send.

    Raises:
        KeyError: If the recipient is not connected.
    """
    async with _USERS_LOCK:
        target_ws = _CONNECTED_USERS.get(recipient)
        if not target_ws:
            raise KeyError(f"Recipient '{recipient}' not connected.")
        payload = {
            "type": "private",
            "from": sender,
            "to": recipient,
            "message": message,
        }
        await target_ws.send(json.dumps(payload))


async def _broadcast(payload: dict, exclude: Set[str] = None) -> None:
    """
    Internal helper to broadcast a JSON payload to all users.

    Args:
        payload: JSON-serializable dict to send.
        exclude: Optional set of usernames to skip.
    """
    if exclude is None:
        exclude = set()
    message = json.dumps(payload)
    async with _USERS_LOCK:
        coros = [
            ws.send(message)
            for user, ws in _CONNECTED_USERS.items()
            if user not in exclude
        ]
    if coros:
        await asyncio.gather(*coros, return_exceptions=True)


def _validate_username(username: str) -> None:
    """
    Validate a username against security constraints.

    Args:
        username: The username string to validate.

    Raises:
        ValueError: If the username is invalid.
    """
    if not USERNAME_REGEX.fullmatch(username):
        raise ValueError(
            "Username must be 3-20 characters long, alphanumeric or underscores."
        )


def _validate_message_content(content: str) -> None:
    """
    Validate message content size.

    Args:
        content: The message string.

    Raises:
        ValueError: If the message exceeds the allowed size.
    """
    if len(content.encode("utf-8")) > MAX_MESSAGE_SIZE:
        raise ValueError("Message exceeds maximum allowed size.")


async def handler(ws: WebSocketServerProtocol, path: str) -> None:
    """
    Main connection handler for each client.

    Protocol:
        1. Client sends a registration message:
           {"type": "register", "username": "desired_name"}
        2. Server validates and registers the user.
        3. Afterwards, client may send:
           - Broadcast: {"type": "broadcast", "message": "..."}
           - Private:   {"type": "private", "to": "username", "message": "..."}
        4. Server responds with success or error messages.

    Args:
        ws: The client WebSocket connection.
        path: URL path (unused).
    """
    username = None
    try:
        # Expect registration as first message
        raw = await asyncio.wait_for(ws.recv(), timeout=30)
        data = json.loads(raw)
        if data.get("type") != "register" or "username" not in data:
            await ws.send(
                json.dumps(
                    {"type": "error", "message": "First message must be registration."}
                )
            )
            return

        proposed_name = str(data["username"]).strip()
        _validate_username(proposed_name)
        await register_user(proposed_name, ws)
        username = proposed_name
        await ws.send(json.dumps({"type": "info", "message": f"Welcome, {username}!"}))
        await broadcast_system_message(f"{username} has joined the chat.")

        # Main message loop
        async for raw_msg in ws:
            try:
                if len(raw_msg.encode("utf-8")) > MAX_MESSAGE_SIZE:
                    raise ValueError("Incoming message too large.")
                msg = json.loads(raw_msg)
                msg_type = msg.get("type")
                if msg_type == "broadcast":
                    content = str(msg.get("message", "")).strip()
                    _validate_message_content(content)
                    await broadcast_user_message(username, content)
                elif msg_type == "private":
                    recipient = str(msg.get("to", "")).strip()
                    content = str(msg.get("message", "")).strip()
                    _validate_message_content(content)
                    await send_private_message(username, recipient, content)
                else:
                    raise ValueError("Unsupported message type.")
            except (json.JSONDecodeError, ValueError, KeyError) as exc:
                error_payload = {"type": "error", "message": str(exc)}
                await ws.send(json.dumps(error_payload))
    except (ConnectionClosedError, asyncio.TimeoutError) as exc:
        logging.info("Connection closed for %s: %s", username or "unknown", exc)
    finally:
        if username:
            await unregister_user(username)


async def main(host: str = "localhost", port: int = 8765) -> None:
    """
    Start the WebSocket chat server.

    Args:
        host: Host interface to bind.
        port: TCP port to listen on.
    """
    async with websockets.serve(handler, host, port, max_size=MAX_MESSAGE_SIZE):
        logging.info("Chat server started on ws://%s:%d", host, port)
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Chat server stopped by user.")