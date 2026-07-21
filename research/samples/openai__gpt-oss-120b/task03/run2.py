"""
chat_server.py
--------------

A simple real‑time chat server built on top of the ``websockets`` library.
It supports:

* User registration (unique usernames)
* Broadcast messaging to all connected users
* Private messaging between two users
* Graceful handling of client disconnects

The server validates inbound messages, enforces a maximum payload size,
and isolates client interactions to prevent crashes from malformed data.

Only the Python standard library and the widely‑used ``websockets`` package
are required.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Set

import websockets
from websockets import WebSocketServerProtocol

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

MAX_MESSAGE_SIZE = 4096  # bytes
ALLOWED_ORIGINS: Set[str] = {"http://localhost", "https://mychat.example.com"}
LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

# --------------------------------------------------------------------------- #
# Helper data structures
# --------------------------------------------------------------------------- #


@dataclass
class ConnectedClient:
    """Container for a connected client."""

    username: str
    websocket: WebSocketServerProtocol
    # Additional fields (e.g., authentication token) could be added here.


# --------------------------------------------------------------------------- #
# Core server implementation
# --------------------------------------------------------------------------- #


class ChatServer:
    """
    Manages client connections and message routing.

    The server keeps a mapping of usernames to :class:`ConnectedClient` objects.
    All public methods raise :class:`ValueError` on invalid usage.
    """

    def __init__(self) -> None:
        self._clients: Dict[str, ConnectedClient] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------- #
    # Connection handling
    # ------------------------------------------------------------------- #

    async def register(self, client: ConnectedClient) -> None:
        """
        Register a new client.

        Args:
            client: The client to register.

        Raises:
            ValueError: If the username is already taken.
        """
        async with self._lock:
            if client.username in self._clients:
                raise ValueError(f"Username '{client.username}' already in use.")
            self._clients[client.username] = client
            logging.info("User registered: %s", client.username)

    async def unregister(self, username: str) -> None:
        """
        Unregister a client by username.

        Args:
            username: The username to remove.

        Raises:
            ValueError: If the username is not known.
        """
        async with self._lock:
            if username not in self._clients:
                raise ValueError(f"Username '{username}' not found.")
            del self._clients[username]
            logging.info("User disconnected: %s", username)

    # ------------------------------------------------------------------- #
    # Messaging
    # ------------------------------------------------------------------- #

    async def broadcast(self, sender: str, message: str) -> None:
        """
        Send a message to all connected clients except the sender.

        Args:
            sender: Username of the message origin.
            message: Text to broadcast.

        Raises:
            RuntimeError: If sending to a client fails.
        """
        payload = json.dumps(
            {"type": "broadcast", "from": sender, "message": message}
        )
        async with self._lock:
            coros = [
                client.websocket.send(payload)
                for uname, client in self._clients.items()
                if uname != sender
            ]
        await self._safe_gather(coros, context="broadcast")

    async def private_message(self, sender: str, recipient: str, message: str) -> None:
        """
        Send a private message from ``sender`` to ``recipient``.

        Args:
            sender: Username of the sender.
            recipient: Username of the receiver.
            message: Text to send.

        Raises:
            ValueError: If the recipient does not exist.
            RuntimeError: If sending fails.
        """
        async with self._lock:
            if recipient not in self._clients:
                raise ValueError(f"Recipient '{recipient}' not connected.")
            target_ws = self._clients[recipient].websocket

        payload = json.dumps(
            {"type": "private", "from": sender, "to": recipient, "message": message}
        )
        await self._safe_gather([target_ws.send(payload)], context="private_message")

    # ------------------------------------------------------------------- #
    # Internal utilities
    # ------------------------------------------------------------------- #

    async def _safe_gather(self, coroutines: list[asyncio.Future], *, context: str) -> None:
        """
        Await a list of coroutines, logging any failures without propagating
        them to the caller.

        Args:
            coroutines: Awaitable objects to run.
            context: Human‑readable description used for logging.
        """
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logging.error(
                    "Error during %s (task %s): %s", context, idx, result, exc_info=True
                )

    async def _handle_message(self, client: ConnectedClient, raw_msg: str) -> None:
        """
        Parse and route a raw JSON message from a client.

        Args:
            client: The sender client.
            raw_msg: Raw JSON string.

        Raises:
            ValueError: If the payload is malformed or violates protocol.
        """
        if len(raw_msg.encode("utf-8")) > MAX_MESSAGE_SIZE:
            raise ValueError("Message exceeds maximum allowed size.")

        try:
            data = json.loads(raw_msg)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON payload.") from exc

        msg_type = data.get("type")
        if msg_type == "broadcast":
            message = data.get("message", "")
            await self.broadcast(client.username, message)
        elif msg_type == "private":
            recipient = data.get("to")
            message = data.get("message", "")
            if not recipient:
                raise ValueError("Private messages require a 'to' field.")
            await self.private_message(client.username, recipient, message)
        else:
            raise ValueError(f"Unsupported message type: {msg_type}")

    # ------------------------------------------------------------------- #
    # WebSocket entry point
    # ------------------------------------------------------------------- #

    async def handler(self, websocket: WebSocketServerProtocol, path: str) -> None:
        """
        Main entry point for each WebSocket connection.

        Protocol:
            1. Client sends a JSON registration message:
               ``{"type": "register", "username": "<desired_name>"}``
            2. Server acknowledges or closes the connection on error.
            3. Subsequent messages follow the schema described in
               :meth:`_handle_message`.

        Args:
            websocket: The client connection.
            path: The request path (unused).

        The coroutine runs until the client disconnects.
        """
        try:
            # Enforce origin check for basic CSRF mitigation
            origin = websocket.request_headers.get("Origin", "")
            if origin not in ALLOWED_ORIGINS:
                await websocket.close(code=4001, reason="Invalid origin.")
                logging.warning("Connection rejected due to origin: %s", origin)
                return

            # Await registration
            raw = await asyncio.wait_for(websocket.recv(), timeout=10)
            reg_data = json.loads(raw)
            if reg_data.get("type") != "register" or "username" not in reg_data:
                raise ValueError("First message must be a registration with a username.")
            username = str(reg_data["username"]).strip()
            if not username:
                raise ValueError("Username cannot be empty.")

            client = ConnectedClient(username=username, websocket=websocket)
            await self.register(client)

            # Notify the new client of successful registration
            await websocket.send(json.dumps({"type": "welcome", "username": username}))

            # Main message loop
            async for raw_msg in websocket:
                try:
                    await self._handle_message(client, raw_msg)
                except ValueError as exc:
                    await websocket.send(json.dumps({"type": "error", "detail": str(exc)}))
        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosedError) as exc:
            logging.info("Connection closed abruptly: %s", exc)
        except Exception as exc:  # Catch‑all for unexpected errors
            logging.error("Unexpected error: %s", exc, exc_info=True)
            await websocket.close(code=1011, reason="Internal server error.")
        finally:
            # Cleanup irrespective of how the loop exited
            if "client" in locals():
                try:
                    await self.unregister(client.username)
                except Exception as exc:
                    logging.error(
                        "Error during unregister of %s: %s", client.username, exc, exc_info=True
                    )
                # Inform remaining users about the disconnect
                await self.broadcast("system", f"{client.username} has left the chat.")


# --------------------------------------------------------------------------- #
# Server bootstrap
# --------------------------------------------------------------------------- #


async def main(host: str = "localhost", port: int = 8765) -> None:
    """
    Start the WebSocket chat server.

    Args:
        host: Interface to bind to.
        port: TCP port to listen on.
    """
    server = ChatServer()
    async with websockets.serve(
        server.handler,
        host,
        port,
        max_size=MAX_MESSAGE_SIZE,
        origins=ALLOWED_ORIGINS,
    ):
        logging.info("Chat server listening on ws://%s:%s", host, port)
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Chat server stopped by user.")