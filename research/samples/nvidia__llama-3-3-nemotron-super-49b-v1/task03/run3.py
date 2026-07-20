# Import necessary libraries
from flask import Flask
from flask_socketio import SocketIO, emit
from typing import Dict, List
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app and SocketIO instance
app = Flask(__name__)
app.config["SECRET_KEY"] = "secret!"  # Replace with a secure secret key
socketio = SocketIO(app, logger=True, cors_allowed_origins="*")

# Store connected users and private conversations
connected_users: Dict[str, str] = {}  # username: sid
private_conversations: Dict[str, List[str]] = {}  # username: [connected_usernames]

### SocketIO Event Handlers ###

@socketio.on("connect")
def handle_connect() -> None:
    """Handle user connection."""
    logger.info("Client connected")

@socketio.on("disconnect")
def handle_disconnect() -> None:
    """Handle user disconnection."""
    sid = request.sid
    if sid in connected_users.values():
        username = list(connected_users.keys())[list(connected_users.values()).index(sid)]
        del connected_users[username]
        logger.info(f"User {username} disconnected")
        broadcast_users()
        # Clean up private conversations
        if username in private_conversations:
            del private_conversations[username]
            for user in list(private_conversations.keys()):
                if username in private_conversations[user]:
                    private_conversations[user].remove(username)

@socketio.on("join")
def handle_join(data: Dict[str, str]) -> None:
    """
    Handle user joining the chat.

    :param data: Dictionary containing "username"
    """
    username = data["username"]
    if username not in connected_users:
        connected_users[username] = request.sid
        logger.info(f"User {username} joined")
        broadcast_users()
        emit("welcome", {"message": f"Welcome, {username}!"}, room=request.sid)

@socketio.on("message")
def handle_message(data: Dict[str, str]) -> None:
    """
    Handle broadcasting a message to all connected users.

    :param data: Dictionary containing "message"
    """
    message = data["message"]
    username = get_username_from_sid(request.sid)
    if username:
        broadcast_message({"username": username, "message": message})

@socketio.on("private_message")
def handle_private_message(data: Dict[str, str]) -> None:
    """
    Handle sending a private message to another user.

    :param data: Dictionary containing "recipient" and "message"
    """
    recipient = data["recipient"]
    message = data["message"]
    sender_username = get_username_from_sid(request.sid)
    if sender_username and recipient in connected_users:
        # Establish or use existing private conversation
        if sender_username not in private_conversations:
            private_conversations[sender_username] = []
        if recipient not in private_conversations[sender_username]:
            private_conversations[sender_username].append(recipient)
            if recipient not in private_conversations:
                private_conversations[recipient] = []
            private_conversations[recipient].append(sender_username)
        
        emit("private_message", {"username": sender_username, "message": message}, room=connected_users[recipient])

### Utility Functions ###

def get_username_from_sid(sid: str) -> str | None:
    """Retrieve username from SocketIO session ID."""
    for username, session_sid in connected_users.items():
        if session_sid == sid:
            return username
    return None

def broadcast_users() -> None:
    """Broadcast list of connected users to all."""
    emit("users", list(connected_users.keys()), broadcast=True)

def broadcast_message(message: Dict[str, str]) -> None:
    """Broadcast a message to all connected users."""
    emit("message", message, broadcast=True)

### Run the Application ###

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)