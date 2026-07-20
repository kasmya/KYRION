"""
Real‑time chat server using Flask‑SocketIO.

Features
--------
- User connection with a chosen nickname.
- Broadcast messages to all connected users.
- Private messages between users.
- Graceful handling of disconnects.
- Basic security measures (input validation, escaping, CORS, secret key).

Run
---
$ pip install Flask Flask‑SocketIO eventlet
$ python chat_server.py
"""

from __future__ import annotations

import html
import logging
from typing import Dict, Set

from flask import Flask, request, jsonify
from flask_socketio import (
    SocketIO,
    emit,
    join_room,
    leave_room,
    disconnect,
    ConnectionRefusedError,
)

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

app = Flask(__name__)
# In production use a strong, random secret key and configure HTTPS.
app.config["SECRET_KEY"] = "change_this_secret_key_in_production"
# Restrict origins for security – adjust as needed.
app.config["CORS_ALLOWED_ORIGINS"] = ["http://localhost:5000"]

# Use eventlet for asynchronous networking (or gevent, etc.).
socketio = SocketIO(app, cors_allowed_origins=app.config["CORS_ALLOWED_ORIGINS"], async_mode="eventlet")

# --------------------------------------------------------------------------- #
# In‑memory user store (sid ↔ username)
# --------------------------------------------------------------------------- #

# Mapping of Socket.IO session id -> username
sid_to_user: Dict[str, str] = {}
# Reverse mapping of username -> sid (unique usernames enforced)
user_to_sid: Dict[str, str] = {}
# Active usernames (helps for validation)
active_usernames: Set[str] = set()

# --------------------------------------------------------------------------- #
# Helper utilities
# --------------------------------------------------------------------------- #


def _sanitize_message(message: str) -> str:
    """Escape HTML to prevent injection attacks."""
    return html.escape(message)


def _validate_username(username: str) -> None:
    """
    Validate a username. Raises ``ValueError`` if invalid.

    Rules:
        * 3‑30 printable characters
        * No whitespace at the ends
        * Must be unique among connected users
    """
    if not (3 <= len(username) <= 30):
        raise ValueError("Username must be between 3 and 30 characters.")
    if username.strip() != username:
        raise ValueError("Username cannot start or end with whitespace.")
    if any(c.isspace() for c in username):
        raise ValueError("Username cannot contain whitespace characters.")
    if username in active_usernames:
        raise ValueError("Username already taken.")


def _get_sid_by_username(username: str) -> str | None:
    """Return the sid for a given username, or ``None`` if not connected."""
    return user_to_sid.get(username)


# --------------------------------------------------------------------------- #
# SocketIO event handlers
# --------------------------------------------------------------------------- #


@socketio.on("connect")
def handle_connect() -> None:
    """
    New client has established a WebSocket connection.

    The client must immediately emit a ``join`` event with a nickname.
    If the client does not send a nickname within a short interval,
    the server will disconnect it (handled client‑side).
    """
    logging.info(f"Client connected: SID={request.sid}")


@socketio.on("join")
def handle_join(data: dict) -> None:
    """
    Register a new user.

    Expected ``data`` format:
        {"username": "<desired nickname>"}
    """
    try:
        username_raw = data.get("username", "")
        username = str(username_raw).strip()
        _validate_username(username)

        sid = request.sid
        sid_to_user[sid] = username
        user_to_sid[username] = sid
        active_usernames.add(username)

        # Put the user in a personal room (for private messaging)
        join_room(sid)

        emit("join_success", {"username": username}, room=sid)
        emit(
            "user_joined",
            {"username": username, "online_users": list(active_usernames)},
            broadcast=True,
            include_self=False,
        )
        logging.info(f"User '{username}' joined, SID={sid}")

    except (ValueError, KeyError) as exc:
        logging.warning(f"Join failed: {exc}")
        emit("join_error", {"error": str(exc)})
        # Disconnect the offending client to keep state consistent.
        disconnect()


@socketio.on("message")
def handle_message(data: dict) -> None:
    """
    Broadcast a message to all connected users.

    Expected ``data`` format:
        {"message": "<text>"}
    """
    try:
        sid = request.sid
        username = sid_to_user[sid]  # raises KeyError if not registered
        raw_message = data.get("message", "")
        message = _sanitize_message(str(raw_message))

        if not message:
            raise ValueError("Empty messages are not allowed.")

        emit(
            "new_message",
            {"username": username, "message": message},
            broadcast=True,
        )
        logging.debug(f"Broadcast from {username}: {message}")

    except (KeyError, ValueError) as exc:
        logging.error(f"Message handling error: {exc}")
        emit("error", {"error": str(exc)})


@socketio.on("private_message")
def handle_private_message(data: dict) -> None:
    """
    Send a private message to a specific user.

    Expected ``data`` format:
        {"to": "<target username>", "message": "<text>"}
    """
    try:
        sid = request.sid
        sender = sid_to_user[sid]  # raises KeyError if not registered

        target_username = str(data.get("to", "")).strip()
        raw_message = data.get("message", "")
        message = _sanitize_message(str(raw_message))

        if not target_username or not message:
            raise ValueError("Both recipient and message are required.")

        target_sid = _get_sid_by_username(target_username)
        if not target_sid:
            raise ValueError(f"User '{target_username}' not online.")

        payload = {"from": sender, "message": message}
        emit("private_message", payload, room=target_sid)
        emit("private_message_sent", {"to": target_username, "message": message}, room=sid)

        logging.info(f"Private message from {sender} to {target_username}")

    except (KeyError, ValueError) as exc:
        logging.error(f"Private message error: {exc}")
        emit("error", {"error": str(exc)})


@socketio.on("disconnect")
def handle_disconnect() -> None:
    """
    Clean up user state when a client disconnects.
    """
    sid = request.sid
    username = sid_to_user.pop(sid, None)
    if username:
        user_to_sid.pop(username, None)
        active_usernames.discard(username)
        leave_room(sid)
        emit(
            "user_left",
            {"username": username, "online_users": list(active_usernames)},
            broadcast=True,
        )
        logging.info(f"User '{username}' disconnected, SID={sid}")
    else:
        logging.info(f"Unregistered SID {sid} disconnected")


# --------------------------------------------------------------------------- #
# HTTP endpoints (optional health check)
# --------------------------------------------------------------------------- #


@app.route("/health", methods=["GET"])
def health_check() -> tuple[dict[str, str], int]:
    """Simple health‑check endpoint."""
    return jsonify(status="ok"), 200


# --------------------------------------------------------------------------- #
# Application entry point
# --------------------------------------------------------------------------- #


if __name__ == "__main__":
    # In production configure proper logging, TLS termination, and a robust WSGI server.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # ``debug=False`` disables the Flask debugger and the reloader.
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)