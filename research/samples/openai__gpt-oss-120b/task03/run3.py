"""
chat_server.py
==============

A minimal real‑time chat server built on top of the :pypi:`websockets` library.
Features:

* User registration (unique usernames)
* Broadcast messaging to all connected users
* Private messaging to a specific user
* Graceful handling of disconnects and malformed messages
* Basic security measures (message size limits, optional TLS)

Only the Python standard library and the widely‑used ``websockets`` package are
required.  Run the server with ``python -m chat_server``.  Clients must speak the
JSON protocol documented in the ``handle_message`` method.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import sys
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

import websockets
from websockets import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

# --------------------------------------------------------------------------- #
# Configuration & Logging
# --------------------------------------------------------------------------- #

MAX_MESSAGE_SIZE: int = 1024  # bytes
DEFAULT_HOST: str = "localhost"
DEFAULT_PORT: int = 8765

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("chat_server")


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #

@dataclass
class Client:
    """Representation of a connected client."""
    username: str
    websocket: WebSocketServerProtocol
    # A set of usernames this client is allowed to send private messages to.
    # By default everyone can message everyone; extend this in the future.
    allowed: Set[str] = field(default_factory=set)


# --------------------------------------------------------------------------- #
# Chat server implementation
# --------------------------------------------------------------------------- #

class ChatServer:
    """
    Core chat server handling WebSocket connections.

    The server maintains a mapping of usernames to :class:`Client` objects.
    All communication follows a simple JSON protocol described in
    :meth:`handle_message`.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        ssl_context: Optional[ssl.SSLContext] = None,
    ) -> None:
        """
        Initialise the server.

        :param host: Hostname or IP address to bind.
        :param port: TCP port to listen on.
        :param ssl_context: Optional :class:`ssl.SSLContext` for TLS.
        """
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.clients: Dict[str, Client] = {}
        self.lock = asyncio.Lock()  # protect ``self.clients``

    async def start(self) -> None:
        """
        Start the WebSocket server and run forever.

        This method should be awaited from an asyncio event loop.
        """
        async with websockets.serve(
            self.handler,
            self.host,
            self.port,
            max_size=MAX_MESSAGE_SIZE,
            ssl=self.ssl_context,
        ):
            log.info("Chat server listening on %s:%s", self.host, self.port)
            await asyncio.Future()  # run forever

    async def handler(self, websocket: WebSocketServerProtocol, path: str) -> None:
        """
        Entry point for each WebSocket connection.

        Handles login, message processing and cleanup on disconnect.

        :param websocket: The client WebSocket connection.
        :param path: The request path (unused).
        """
        username: Optional[str] = None
        try:
            # Expect the first message to be a login request.
            raw = await asyncio.wait_for(websocket.recv(), timeout=10)
            login_data = self.parse_json(raw)
            if login_data.get("type") != "login" or "username" not in login_data:
                await self.send_error(websocket, "First message must be a login request.")
                return

            username = self.sanitize_username(login_data["username"])
            async with self.lock:
                if username in self.clients:
                    await self.send_error(websocket, f"Username '{username}' is already taken.")
                    return
                self.clients[username] = Client(username=username, websocket=websocket)
                log.info("User '%s' connected.", username)

            await self.send_info(websocket, f"Welcome, {username}!")
            await self.broadcast_info(f"User '{username}' has joined the chat.", exclude={username})

            # Main receive loop
            async for raw_message in websocket:
                data = self.parse_json(raw_message)
                await self.handle_message(username, data)

        except (asyncio.TimeoutError, json.JSONDecodeError) as exc:
            await self.send_error(websocket, f"Invalid login sequence: {exc}")
        except ConnectionClosedOK:
            log.info("User '%s' closed the connection cleanly.", username or "<unknown>")
        except ConnectionClosedError as exc:
            log.warning("Connection error with user '%s': %s", username or "<unknown>", exc)
        finally:
            if username:
                await self.unregister(username)

    async def unregister(self, username: str) -> None:
        """
        Remove a client from the internal registry and notify others.

        :param username: The username to remove.
        """
        async with self.lock:
            client = self.clients.pop(username, None)
        if client:
            log.info("User '%s' disconnected.", username)
            await self.broadcast_info(f"User '{username}' has left the chat.", exclude={username})

    async def handle_message(self, sender: str, data: dict) -> None:
        """
        Dispatch incoming messages based on their ``type`` field.

        Supported types:
        * ``broadcast`` – send to all users.
        * ``private`` – send to a single recipient.

        :param sender: Username of the message sender.
        :param data: Parsed JSON payload.
        """
        msg_type = data.get("type")
        if msg_type == "broadcast":
            message = data.get("message")
            if not isinstance(message, str):
                await self.send_error_to(sender, "Broadcast message must be a string.")
                return
            await self.broadcast_message(message, sender)
        elif msg_type == "private":
            recipient = data.get("to")
            message = data.get("message")
            if not (isinstance(recipient, str) and isinstance(message, str)):
                await self.send_error_to(sender, "Private messages require 'to' and 'message' strings.")
                return
            await self.send_private_message(message, sender, recipient)
        else:
            await self.send_error_to(sender, f"Unsupported message type: {msg_type!r}")

    async def broadcast_message(self, message: str, sender: str) -> None:
        """
        Send a message to all connected users.

        :param message: Text to broadcast.
        :param sender: Username of the sender.
        """
        payload = {
            "type": "broadcast",
            "from": sender,
            "message": message,
        }
        await self._send_to_all(payload, exclude=set())

    async def send_private_message(self, message: str, sender: str, recipient: str) -> None:
        """
        Send a private message to a specific user.

        :param message: Text to send.
        :param sender: Username of the sender.
        :param recipient: Username of the intended recipient.
        """
        async with self.lock:
            target = self.clients.get(recipient)
            sender_client = self.clients.get(sender)

        if not target:
            await self.send_error_to(sender, f"Recipient '{recipient}' not found.")
            return

        payload = {
            "type": "private",
            "from": sender,
            "message": message,
        }
        try:
            await target.websocket.send(json.dumps(payload))
            log.debug("Private message from '%s' to '%s' delivered.", sender, recipient)
        except Exception as exc:
            await self.send_error_to(sender, f"Failed to deliver private message: {exc}")

    async def broadcast_info(self, info: str, exclude: Set[str] = set()) -> None:
        """
        Broadcast an informational message (e.g., join/leave notifications).

        :param info: Information text.
        :param exclude: Set of usernames to exclude from the broadcast.
        """
        payload = {"type": "info", "message": info}
        await self._send_to_all(payload, exclude=exclude)

    async def send_info(self, websocket: WebSocketServerProtocol, info: str) -> None:
        """
        Send an informational message to a single websocket.

        :param websocket: Target connection.
        :param info: Message text.
        """
        payload = {"type": "info", "message": info}
        await websocket.send(json.dumps(payload))

    async def send_error(self, websocket: WebSocketServerProtocol, error_msg: str) -> None:
        """
        Send an error message to a single websocket.

        :param websocket: Target connection.
        :param error_msg: Description of the error.
        """
        payload = {"type": "error", "message": error_msg}
        await websocket.send(json.dumps(payload))

    async def send_error_to(self, username: str, error_msg: str) -> None:
        """
        Send an error message to a specific user by username.

        :param username: Recipient username.
        :param error_msg: Error description.
        """
        async with self.lock:
            client = self.clients.get(username)
        if client:
            await self.send_error(client.websocket, error_msg)

    async def _send_to_all(self, payload: dict, exclude: Set[str]) -> None:
        """
        Internal helper to broadcast a JSON payload to all clients except those in ``exclude``.

        :param payload: JSON‑serialisable dictionary.
        :param exclude: Set of usernames to omit.
        """
        message = json.dumps(payload)
        async with self.lock:
            targets = [
                client.websocket
                for uname, client in self.clients.items()
                if uname not in exclude
            ]

        # Send concurrently, ignore individual failures but log them.
        await asyncio.gather(
            *(self._safe_send(ws, message) for ws in targets),
            return_exceptions=True,
        )

    async def _safe_send(self, ws: WebSocketServerProtocol, message: str) -> None:
        """
        Send a message while catching and logging any transport errors.

        :param ws: Destination websocket.
        :param message: JSON string to send.
        """
        try:
            await ws.send(message)
        except (ConnectionClosedOK, ConnectionClosedError):
            # Connection will be cleaned up elsewhere.
            pass
        except Exception as exc:
            log.error("Failed to send message to a client: %s", exc)

    @staticmethod
    def parse_json(raw: str) -> dict:
        """
        Parse a JSON string into a dictionary, raising ``json.JSONDecodeError`` on failure.

        :param raw: Raw JSON string.
        :return: Parsed dictionary.
        """
        return json.loads(raw)

    @staticmethod
    def sanitize_username(name: str) -> str:
        """
        Basic sanitisation for usernames: strip whitespace and limit length.

        :param name: Raw username.
        :return: Sanitised username.
        :raises ValueError: If the username is empty or too long.
        """
        sanitized = name.strip()
        if not sanitized:
            raise ValueError("Username cannot be empty.")
        if len(sanitized) > 32:
            raise ValueError("Username exceeds maximum length of 32 characters.")
        return sanitized


# --------------------------------------------------------------------------- #
# Helper for TLS (optional)
# --------------------------------------------------------------------------- #

def create_ssl_context(certfile: str, keyfile: str) -> ssl.SSLContext:
    """
    Build an :class:`ssl.SSLContext` for encrypted connections.

    :param certfile: Path to the PEM‑encoded certificate.
    :param keyfile: Path to the PEM‑encoded private key.
    :return: Configured SSL context.
    """
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certfile=certfile, keyfile=keyfile)
    # Enforce strong ciphers only.
    context.set_ciphers("ECDHE+AESGCM")
    return context


# --------------------------------------------------------------------------- #
# Entry‑point
# --------------------------------------------------------------------------- #

def main() -> None:
    """
    Parse command‑line arguments and launch the chat server.

    Usage:
        python -m chat_server [--host HOST] [--port PORT] [--cert CERT] [--key KEY]
    """
    import argparse

    parser = argparse.ArgumentParser(description="Run the WebSocket chat server.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Interface to bind to.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port.")
    parser.add_argument("--cert", help="Path to TLS certificate (enables TLS).")
    parser.add_argument("--key", help="Path to TLS private key (required with --cert).")
    args = parser.parse_args()

    ssl_ctx: Optional[ssl.SSLContext] = None
    if args.cert:
        if not args.key:
            parser.error("--key is required when --cert is provided.")
        ssl_ctx = create_ssl_context(args.cert, args.key)
        log.info("TLS enabled with certificate %s.", args.cert)

    server = ChatServer(host=args.host, port=args.port, ssl_context=ssl_ctx)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        log.info("Chat server stopped by user.")
    except Exception as exc:
        log.exception("Fatal error in chat server: %s", exc)


if __name__ == "__main__":
    main()