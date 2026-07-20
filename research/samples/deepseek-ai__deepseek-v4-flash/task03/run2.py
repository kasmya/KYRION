"""
Real-time chat application using Flask-SocketIO.

Features:
- User connection with nickname
- Broadcasting messages to all connected users
- Private messaging between users
- User disconnection handling
- Security: input sanitization, type validation, error handling
"""

from typing import Dict, Optional
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect
import html
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Change in production
socketio = SocketIO(app, cors_allowed_origins="*")  # Configure CORS properly in production

# In-memory store: sid -> username
connected_users: Dict[str, str] = {}

# HTML template for the chat client (for testing)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Chat App</title>
    <script src="https://cdn.socket.io/4.6.0/socket.io.min.js"></script>
    <style>
        body { font-family: Arial; margin: 20px; }
        #messages { border: 1px solid #ccc; height: 300px; overflow-y: scroll; padding: 10px; margin-bottom: 10px; }
        #message-input { width: 60%; }
    </style>
</head>
<body>
    <h2>WebSocket Chat</h2>
    <div>
        <label>Nickname: <input id="nickname" placeholder="Enter nickname"></label>
        <button id="connect-btn">Connect</button>
        <button id="disconnect-btn" disabled>Disconnect</button>
    </div>
    <div id="messages"></div>
    <div>
        <input id="recipient" placeholder="Recipient (empty for broadcast)" size="20">
        <input id="message-input" placeholder="Type a message...">
        <button id="send-btn">Send</button>
    </div>
    <script>
        let socket = null;
        const messages = document.getElementById('messages');
        const nicknameInput = document.getElementById('nickname');
        const connectBtn = document.getElementById('connect-btn');
        const disconnectBtn = document.getElementById('disconnect-btn');
        const messageInput = document.getElementById('message-input');
        const recipientInput = document.getElementById('recipient');
        const sendBtn = document.getElementById('send-btn');

        function addMessage(msg) {
            const div = document.createElement('div');
            div.textContent = msg;
            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
        }

        connectBtn.addEventListener('click', () => {
            const nickname = nicknameInput.value.trim();
            if (!nickname) { alert('Please enter a nickname'); return; }
            socket = io();
            socket.on('connect', () => {
                socket.emit('join', { nickname: nickname });
                connectBtn.disabled = true;
                disconnectBtn.disabled = false;
                addMessage('Connected as ' + nickname);
            });
            socket.on('message', (data) => {
                addMessage(data.sender + ': ' + data.message);
            });
            socket.on('private_message', (data) => {
                addMessage('[Private] ' + data.sender + ': ' + data.message);
            });
            socket.on('user_connected', (data) => {
                addMessage(data.nickname + ' joined the chat');
            });
            socket.on('user_disconnected', (data) => {
                addMessage(data.nickname + ' left the chat');
            });
            socket.on('error', (data) => {
                addMessage('Error: ' + data.message);
            });
            socket.on('disconnect', () => {
                addMessage('Disconnected from server');
                connectBtn.disabled = false;
                disconnectBtn.disabled = true;
                socket = null;
            });
        });

        disconnectBtn.addEventListener('click', () => {
            if (socket) socket.disconnect();
        });

        sendBtn.addEventListener('click', () => {
            if (!socket) { alert('Not connected'); return; }
            const message = messageInput.value.trim();
            if (!message) return;
            const recipient = recipientInput.value.trim();
            if (recipient) {
                socket.emit('private_message', { recipient: recipient, message: message });
            } else {
                socket.emit('broadcast_message', { message: message });
            }
            messageInput.value = '';
        });
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Serve the chat client HTML page."""
    return render_template_string(HTML_TEMPLATE)


def sanitize_input(text: str) -> str:
    """
    Sanitize user input by escaping HTML characters and trimming whitespace.

    Args:
        text: Raw user input.

    Returns:
        Sanitized string.
    """
    return html.escape(text.strip(), quote=True)


def validate_nickname(nickname: str) -> Optional[str]:
    """
    Validate a nickname: non-empty, alphanumeric and underscores, length 3-20.

    Args:
        nickname: The nickname to validate.

    Returns:
        Error message if invalid, None if valid.
    """
    if not nickname:
        return "Nickname cannot be empty."
    if len(nickname) < 3 or len(nickname) > 20:
        return "Nickname must be between 3 and 20 characters."
    if not re.match(r'^[a-zA-Z0-9_]+$', nickname):
        return "Nickname can only contain letters, numbers, and underscores."
    return None


@socketio.on('join')
def handle_join(data: dict) -> None:
    """
    Handle a user joining the chat.

    Expects data with 'nickname'. Validates, stores user, broadcasts join message.

    Args:
        data: Dictionary containing 'nickname'.
    """
    nickname = sanitize_input(data.get('nickname', ''))
    error = validate_nickname(nickname)
    if error:
        emit('error', {'message': error})
        disconnect()
        return

    # Check if nickname already in use
    if nickname in connected_users.values():
        emit('error', {'message': 'Nickname already taken.'})
        disconnect()
        return

    sid = request.sid
    connected_users[sid] = nickname
    join_room('global')

    # Broadcast to all users (including sender)
    socketio.emit('user_connected', {'nickname': nickname}, room='global')

    # Notify sender that they joined successfully
    emit('message', {'sender': 'System', 'message': f'Welcome {nickname}!'})

    print(f"[JOIN] {nickname} connected (sid: {sid})")


@socketio.on('broadcast_message')
def handle_broadcast(data: dict) -> None:
    """
    Broadcast a message to all connected users.

    Args:
        data: Dictionary containing 'message'.
    """
    sid = request.sid
    sender = connected_users.get(sid)
    if not sender:
        emit('error', {'message': 'You are not connected.'})
        return

    message = sanitize_input(data.get('message', ''))
    if not message:
        emit('error', {'message': 'Message cannot be empty.'})
        return

    # Broadcast to everyone in the global room (including sender)
    socketio.emit('message', {'sender': sender, 'message': message}, room='global')
    print(f"[BROADCAST] {sender}: {message}")


@socketio.on('private_message')
def handle_private_message(data: dict) -> None:
    """
    Send a private message to a specific user by nickname.

    Args:
        data: Dictionary with 'recipient' (nickname) and 'message'.
    """
    sender_sid = request.sid
    sender = connected_users.get(sender_sid)
    if not sender:
        emit('error', {'message': 'You are not connected.'})
        return

    recipient_nickname = sanitize_input(data.get('recipient', ''))
    message = sanitize_input(data.get('message', ''))
    if not recipient_nickname:
        emit('error', {'message': 'Recipient nickname is required.'})
        return
    if not message:
        emit('error', {'message': 'Message cannot be empty.'})
        return

    # Find recipient sid
    recipient_sid = None
    for sid, nickname in connected_users.items():
        if nickname == recipient_nickname:
            recipient_sid = sid
            break

    if recipient_sid is None:
        emit('error', {'message': f'User "{recipient_nickname}" not found.'})
        return

    # Send privately to recipient
    socketio.emit('private_message', {'sender': sender, 'message': message}, room=recipient_sid)
    # Also send a confirmation to the sender
    socketio.emit('private_message', {'sender': sender, 'message': message}, room=sender_sid)
    print(f"[PRIVATE] {sender} -> {recipient_nickname}: {message}")


@socketio.on('disconnect')
def handle_disconnect() -> None:
    """
    Handle user disconnection. Remove from store, broadcast departure.
    """
    sid = request.sid
    nickname = connected_users.pop(sid, None)
    if nickname:
        leave_room('global')
        socketio.emit('user_disconnected', {'nickname': nickname}, room='global')
        print(f"[DISCONNECT] {nickname} left")


@socketio.on_error_default
def default_error_handler(e: Exception) -> None:
    """
    Default error handler for SocketIO events.

    Args:
        e: The exception that occurred.
    """
    print(f"[ERROR] SocketIO error: {str(e)}")
    emit('error', {'message': 'An internal error occurred.'})


def main() -> None:
    """Run the chat application."""
    print("Starting WebSocket Chat Server...")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    main()