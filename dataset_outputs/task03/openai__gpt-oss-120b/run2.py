"""Real‑time chat server using Flask‑SocketIO.

Features:
- User connection with simple token‑based identification.
- Broadcast messages to all connected users.
- Private messages between specific users.
- Clean disconnection handling.
- Basic security: input sanitisation, message length limits,
  CORS restrictions and secret key.

Run with:
    pip install flask flask-socketio eventlet
    python chat_server.py
"""

from __future__ import annotations

import html
from typing import Dict, Any

from flask import Flask, request, abort
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

# --------------------------------------------------------------------------- #
# Flask & SocketIO configuration
# --------------------------------------------------------------------------- #
app = Flask(__name__)
# NOTE: Replace with a strong random value in production
app.config["SECRET_KEY"] = "change_this_to_a_strong_random_secret"
# Restrict origins to known front‑ends; adjust as needed
socketio = SocketIO(app, cors_allowed_origins=["http://localhost:3000"])

# --------------------------------------------------------------------------- #
# In‑memory state
# --------------------------------------------------------------------------- #
# Mapping from Socket.IO session id (sid) to username
users: Dict[str, str] = {}
# Reverse lookup: username -> sid (for private messaging)
rooms: Dict[str, str] = {}

# Application constants
MAX_MESSAGE_LENGTH = 500  # Prevent excessively large payloads


def sanitize(text: str) -> str:
    """HTML‑escape a string and trim whitespace.

    Args:
        text: Raw message content.

    Returns:
        A safe, escaped version of *text*.
    """
    return html.escape(text.strip())


# --------------------------------------------------------------------------- #
# Event handlers
# --------------------------------------------------------------------------- #
@socketio.event
def connect(auth: Dict[str, Any] | None = None):
    """Authenticate a new client.

    The client must send an ``auth`` dict containing a ``token`` field.
    For demo purposes the token itself is treated as the username.
    """
    if not auth or "token" not in auth:
        # Reject the connection if no token is supplied
        return False

    token = auth["token"]
    username = str(token).strip()
    if not username:
        return False

    sid = request.sid

    # Ensure username uniqueness
    if username in rooms:
        emit("error", {"msg": "Username already in use."}, to=sid)
        disconnect()
        return

    users[sid] = username
    rooms[username] = sid
    join_room("global")

    # Notify the new client
    emit("connected", {"msg": f"Welcome {username}!"}, to=sid)

    # Broadcast presence to others
    emit(
        "user_joined",
        {"username": username},
        broadcast=True,
        include_self=False,
    )


@socketio.event
def disconnect():
    """Cleanup after a client disconnects."""
    sid = request.sid
    username = users.pop(sid, None)

    if username:
        rooms.pop(username, None)
        leave_room("global")
        emit("user_left", {"username": username}, broadcast=True)


@socketio.on("broadcast")
def handle_broadcast(data: Dict[str, Any]):
    """Receive a message from a client and broadcast it.

    Expected payload:
        {"msg": "<message text>"}
    """
    sid = request.sid
    username = users.get(sid)

    if not username:
        emit("error", {"msg": "Unauthenticated."}, to=sid)
        return

    raw_msg = data.get("msg", "")
    if not isinstance(raw_msg, str):
        emit("error", {"msg": "Invalid message format."}, to=sid)
        return

    if len(raw_msg) > MAX_MESSAGE_LENGTH:
        emit("error", {"msg": "Message too long."}, to=sid)
        return

    safe_msg = sanitize(raw_msg)
    payload = {"username": username, "msg": safe_msg}
    emit("broadcast", payload, broadcast=True)


@socketio.on("private_message")
def handle_private_message(data: Dict[str, Any]):
    """Send a private message to a specific user.

    Expected payload:
        {"to": "<recipient username>", "msg": "<message text>"}
    """
    sid = request.sid
    sender = users.get(sid)

    if not sender:
        emit("error", {"msg": "Unauthenticated."}, to=sid)
        return

    target = data.get("to")
    raw_msg = data.get("msg", "")

    if not isinstance(target, str) or not isinstance(raw_msg, str):
        emit("error", {"msg": "Invalid payload."}, to=sid)
        return

    if len(raw_msg) > MAX_MESSAGE_LENGTH:
        emit("error", {"msg": "Message too long."}, to=sid)
        return

    safe_msg = sanitize(raw_msg)
    target_sid = rooms.get(target)

    if not target_sid:
        emit("error", {"msg": f"User {target} not connected."}, to=sid)
        return

    payload = {"from": sender, "msg": safe_msg}
    emit("private_message", payload, to=target_sid)

    # Acknowledge the sender (optional)
    emit(
        "private_message_sent",
        {"to": target, "msg": safe_msg},
        to=sid,
    )


# --------------------------------------------------------------------------- #
# Application entry point
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    # Use eventlet for scalable WebSocket handling
    import eventlet

    eventlet.monkey_patch()
    socketio.run(app, host="0.0.0.0", port=5000)