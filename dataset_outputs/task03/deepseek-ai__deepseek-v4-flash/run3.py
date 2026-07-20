import eventlet
eventlet.monkey_patch()  # Required for Flask-SocketIO with async

from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit, join_room, leave_room, send
from markupsafe import escape
from typing import Dict, Optional, Set, Any

# Simple in-memory store for connected users
# Maps sid -> username
connected_users: Dict[str, str] = {}
# Maps username -> sid for fast private messaging
username_to_sid: Dict[str, str] = {}

# HTML template for a basic chat client (inline for self-containment)
CLIENT_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Chat</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            var socket = io();
            var username = prompt('Enter your username:');
            if (username) {
                socket.emit('set_username', {'username': username});
            }
            socket.on('connect', function() {
                console.log('Connected');
            });
            socket.on('message', function(data) {
                var message = data['user'] + ': ' + data['message'];
                var li = document.createElement('li');
                li.textContent = message;
                document.getElementById('messages').appendChild(li);
            });
            socket.on('private_message', function(data) {
                var message = '[Private from ' + data['sender'] + ']: ' + data['message'];
                var li = document.createElement('li');
                li.textContent = message;
                document.getElementById('messages').appendChild(li);
            });
            socket.on('user_joined', function(data) {
                var li = document.createElement('li');
                li.textContent = data['username'] + ' joined the chat.';
                document.getElementById('messages').appendChild(li);
            });
            socket.on('user_left', function(data) {
                var li = document.createElement('li');
                li.textContent = data['username'] + ' left the chat.';
                document.getElementById('messages').appendChild(li);
            });
            socket.on('error', function(data) {
                alert(data['message']);
            });
            document.getElementById('send-btn').addEventListener('click', function() {
                var input = document.getElementById('msg-input');
                var msg = input.value;
                if (msg.startsWith('/msg ')) {
                    var parts = msg.split(' ');
                    if (parts.length >= 3) {
                        var recipient = parts[1];
                        var pm = parts.slice(2).join(' ');
                        socket.emit('private_message', {'recipient': recipient, 'message': pm});
                    }
                } else {
                    socket.emit('send_message', {'message': msg});
                }
                input.value = '';
            });
        });
    </script>
</head>
<body>
    <ul id="messages"></ul>
    <input id="msg-input" type="text" placeholder="Type a message...">
    <button id="send-btn">Send</button>
    <p><small>Use <code>/msg &lt;username&gt; &lt;message&gt;</code> for private messages.</small></p>
</body>
</html>
"""

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Should be replaced with a secure random key
socketio = SocketIO(app, cors_allowed_origins="*")  # For development; in production restrict origins


def sanitize(text: str) -> str:
    """Escape HTML to prevent XSS attacks."""
    return escape(text)


def get_username(sid: str) -> Optional[str]:
    """Retrieve the username associated with a session ID.

    Args:
        sid: The socket session ID.

    Returns:
        The username if found, otherwise None.
    """
    return connected_users.get(sid)


def broadcast_user_list() -> None:
    """Send the current list of usernames to all connected clients."""
    users = list(username_to_sid.keys())
    emit('user_list', {'users': users}, broadcast=True)


@app.route('/')
def index():
    """Serve the chat client page."""
    return render_template_string(CLIENT_HTML)


@socketio.on('connect')
def handle_connect() -> None:
    """On new connection, initialize and notify the client."""
    pass  # Client will send username via 'set_username'


@socketio.on('set_username')
def handle_set_username(data: dict) -> None:
    """Register a username for the newly connected client.

    Validates the username (non-empty, not taken) and stores mappings.
    Broadcasts join notification to all other users.

    Args:
        data: Dictionary with key 'username'.
    """
    sid = handle_set_username.sid  # Get sid from the event context
    username = data.get('username', '').strip()
    if not username:
        emit('error', {'message': 'Username cannot be empty.'})
        return
    if username in username_to_sid:
        emit('error', {'message': 'Username already taken. Please choose another.'})
        return

    # Store mappings
    connected_users[sid] = username
    username_to_sid[username] = sid

    # Notify others about the new user
    emit('user_joined', {'username': username}, broadcast=True, include_self=False)
    broadcast_user_list()

    # Confirm to the user
    emit('message', {'user': 'System', 'message': f'You joined as {username}'})


@socketio.on('send_message')
def handle_send_message(data: dict) -> None:
    """Broadcast a public message to all connected users.

    The sender's username is automatically prepended.

    Args:
        data: Dictionary with key 'message' containing the message text.
    """
    sid = handle_send_message.sid
    sender = get_username(sid)
    if sender is None:
        emit('error', {'message': 'You must set a username first.'})
        return
    message = sanitize(data.get('message', ''))
    if not message:
        return  # Ignore empty messages
    emit('message', {'user': sender, 'message': message}, broadcast=True)


@socketio.on('private_message')
def handle_private_message(data: dict) -> None:
    """Send a private message to a specific user.

    Both the sender and the recipient receive the message.
    The sender must have previously set a username.

    Args:
        data: Dictionary with keys 'recipient' (str) and 'message' (str).
    """
    sid = handle_private_message.sid
    sender = get_username(sid)
    if sender is None:
        emit('error', {'message': 'You must set a username first.'})
        return

    recipient = data.get('recipient', '').strip()
    message = sanitize(data.get('message', ''))
    if not recipient or not message:
        emit('error', {'message': 'Private message requires both recipient and message.'})
        return

    recipient_sid = username_to_sid.get(recipient)
    if recipient_sid is None:
        emit('error', {'message': f'User "{recipient}" not found.'})
        return

    # Send to recipient
    emit('private_message', {'sender': sender, 'message': message}, to=recipient_sid)
    # Send to sender (confirm)
    emit('private_message', {'sender': f'You to {recipient}', 'message': message}, to=sid)


@socketio.on('disconnect')
def handle_disconnect() -> None:
    """Handle user disconnection.

    Removes the user from mappings and notifies others about the departure.
    """
    sid = handle_disconnect.sid
    username = connected_users.pop(sid, None)
    if username:
        username_to_sid.pop(username, None)
        emit('user_left', {'username': username}, broadcast=True)
        broadcast_user_list()


if __name__ == '__main__':
    print("Starting chat server at http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)