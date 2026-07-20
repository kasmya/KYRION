"""
Real-time chat application using Flask-SocketIO.

Features:
- User connection with a unique username.
- Broadcast messages to all connected users.
- Private messaging between users.
- Graceful handling of user disconnections.
- Basic security checks (username validation, message size limits, simple token auth).

Run:
    $ pip install flask flask-socketio eventlet
    $ python chat_app.py
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Optional

from flask import Flask, request, abort
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

MAX_MESSAGE_LENGTH: int = 1000  # Prevent excessively large payloads
USERNAME_REGEX = re.compile(r"^[A-Za-z0-9_]{3,20}$")  # Simple username validation
AUTH_TOKEN: str = "CHANGE_ME_TO_A_SECURE_RANDOM_STRING"

app = Flask(__name__)
app.config["SECRET_KEY"] = "CHANGE_ME_TO_A_RANDOM_SECRET_KEY"
socketio = SocketIO(app, cors_allowed_origins="*")  # In production restrict origins

# --------------------------------------------------------------------------- #
# In‑memory user registry
# --------------------------------------------------------------------------- #

class UserRegistry:
    """Thread‑safe (via SocketIO's context) registry of connected users."""

    def __init__(self) -> None:
        self.sid_to_user: Dict[str, str] = {}
        self.user_to_sid: Dict[str, str] = {}

    def add(self, sid: str, username: str) -> None:
        self.sid_to_user[sid] = username
        self.user_to_sid[username] = sid

    def remove_by_sid(self, sid: str) -> Optional[str]:
        username = self.sid_to_user.pop(sid, None)
        if username:
            self.user_to_sid.pop(username, None)
        return username

    def get_sid(self, username: str) -> Optional[str]:
        return self.user_to_sid.get(username)

    def list_users(self) -> Dict[str, str]:
        """Return a copy of username → sid mapping."""
        return dict(self.user_to_sid)


users = UserRegistry()
log = logging.getLogger("chat")
logging.basicConfig(level=logging.INFO)


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #

def _validate_token(token: Optional[str]) -> bool:
    """Simple token check – replace with proper authentication in prod."""
    return token == AUTH_TOKEN


def _validate_username(username: str) -> bool:
    """Return True if username meets the defined pattern."""
    return bool(USERNAME_REGEX.fullmatch(username))


def _sanitize_message(message: str) -> str:
    """Trim and truncate message to a safe length."""
    return message.strip()[:MAX_MESSAGE_LENGTH]


# --------------------------------------------------------------------------- #
# SocketIO event handlers
# --------------------------------------------------------------------------- #

@socketio.event
def connect() -> None:
    """
    Handle a new client connection.

    Expected query parameters:
        token   – simple auth token.
        username – desired display name.
    """
    token = request.args.get("token")
    username = request.args.get("username")

    if not _validate_token(token):
        log.warning("Connection rejected: invalid token from %s", request.remote_addr)
        return abort(401)

    if not username or not _validate_username(username):
        log.warning("Connection rejected: invalid username %r", username)
        return abort(400, description="Invalid username")

    if users.get_sid(username):
        log.warning("Connection rejected: username already in use %r", username)
        return abort(409, description="Username already taken")

    sid = request.sid
    users.add(sid, username)
    join_room("broadcast")  # All users join a common room for broadcasting

    log.info("User %s connected (sid=%s)", username, sid)
    emit("system_message", {"msg": f"{username} has joined the chat."}, room="broadcast")
    emit("user_list", {"users": list(users.list_users().keys())})


@socketio.event
def disconnect() -> None:
    """Remove user from registry and inform remaining participants."""
    sid = request.sid
    username = users.remove_by_sid(sid)
    if username:
        leave_room("broadcast")
        log.info("User %s disconnected (sid=%s)", username, sid)
        emit("system_message", {"msg": f"{username} has left the chat."}, room="broadcast")
        emit("user_list", {"users": list(users.list_users().keys())}, broadcast=True)


@socketio.on("chat_message")
def handle_chat_message(data: dict) -> None:
    """
    Broadcast a message to all connected users.

    Expected payload:
        {"msg": "<text>"}
    """
    try:
        raw_msg = data.get("msg", "")
        if not isinstance(raw_msg, str):
            raise ValueError("Message must be a string")
        msg = _sanitize_message(raw_msg)
        if not msg:
            raise ValueError("Empty message")
    except Exception as exc:
        log.error("Invalid chat_message payload: %s", exc)
        emit("error", {"error": str(exc)})
        return

    username = users.sid_to_user.get(request.sid, "Unknown")
    log.debug("Broadcast from %s: %s", username, msg)
    emit(
        "chat_message",
        {"user": username, "msg": msg},
        room="broadcast"
    )


@socketio.on("private_message")
def handle_private_message(data: dict) -> None:
    """
    Send a private message to a specific user.

    Expected payload:
        {"to": "<username>", "msg": "<text>"}
    """
    try:
        target_user = data.get("to")
        raw_msg = data.get("msg", "")
        if not isinstance(target_user, str) or not isinstance(raw_msg, str):
            raise ValueError("Both 'to' and 'msg' must be strings")
        if not _validate_username(target_user):
            raise ValueError("Invalid target username")
        msg = _sanitize_message(raw_msg)
        if not msg:
            raise ValueError("Empty message")
    except Exception as exc:
        log.error("Invalid private_message payload: %s", exc)
        emit("error", {"error": str(exc)})
        return

    from_user = users.sid_to_user.get(request.sid, "Unknown")
    target_sid = users.get_sid(target_user)
    if not target_sid:
        emit("error", {"error": f"User {target_user} not found"})
        return

    log.debug("Private from %s to %s: %s", from_user, target_user, msg)
    # Send to recipient
    emit(
        "private_message",
        {"from": from_user, "msg": msg},
        room=target_sid
    )
    # Echo back to sender for UI confirmation
    emit(
        "private_message_sent",
        {"to": target_user, "msg": msg},
        room=request.sid
    )


# --------------------------------------------------------------------------- #
# HTTP endpoints (optional, for health checks or basic UI)
# --------------------------------------------------------------------------- #

@app.route("/health")
def health_check() -> str:
    """Simple health check."""
    return "OK", 200


# --------------------------------------------------------------------------- #
# Application entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # In production use eventlet or gevent workers; here we default to eventlet.
    import eventlet
    import eventlet.wsgi

    log.info("Starting chat server...")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)