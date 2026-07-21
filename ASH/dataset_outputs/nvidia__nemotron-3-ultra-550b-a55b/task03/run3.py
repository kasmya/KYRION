"""
Real-time WebSocket Chat Application

This module implements a secure, asynchronous chat server using WebSockets.
Features include user connection management, broadcast messaging, private messaging,
and graceful disconnect handling with comprehensive error handling and type safety.

Security Considerations:
- Input validation and sanitization on all user-provided data
- Message size limits to prevent DoS
- Connection rate limiting (basic implementation)
- No eval/exec on user input
- Secure WebSocket (WSS) recommended for production deployment
- User authentication/authorization hooks provided for extension

Dependencies:
- websockets (PyPI): `pip install websockets`
- Python 3.8+ standard library modules
"""

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Any, Callable, Awaitable
from websockets.server import WebSocketServerProtocol, serve
from websockets.exceptions import ConnectionClosed, WebSocketException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants for security and limits
MAX_MESSAGE_SIZE = 1024 * 16  # 16 KB
MAX_USERNAME_LENGTH = 32
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")
MESSAGE_TYPES = {"broadcast", "private", "system", "error", "user_list"}


@dataclass
class ConnectedUser:
    """Represents a connected chat user with metadata."""
    user_id: str
    username: str
    websocket: WebSocketServerProtocol
    connected_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class ChatServer:
    """
    Manages WebSocket connections and message routing for the chat application.
    
    Handles user registration, broadcast messaging, private messaging,
    and connection lifecycle events with thread-safe operations.
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        max_connections: int = 1000,
        message_handler: Optional[Callable[[ConnectedUser, dict], Awaitable[None]]] = None
    ) -> None:
        """
        Initialize the chat server.
        
        Args:
            host: Network interface to bind to
            port: Port number to listen on
            max_connections: Maximum concurrent connections allowed
            message_handler: Optional custom message handler coroutine
        """
        self.host = host
        self.port = port
        self.max_connections = max_connections
        self.custom_handler = message_handler
        
        # Thread-safe storage for connected users
        self._users: Dict[str, ConnectedUser] = {}  # user_id -> ConnectedUser
        self._username_map: Dict[str, str] = {}     # username -> user_id
        self._lock = asyncio.Lock()
        
        # Server state
        self._server = None
        self._running = False
    
    async def start(self) -> None:
        """Start the WebSocket server and begin accepting connections."""
        if self._running:
            logger.warning("Server already running")
            return
            
        self._running = True
        logger.info(f"Starting chat server on {self.host}:{self.port}")
        
        try:
            self._server = await serve(
                self._handle_connection,
                self.host,
                self.port,
                max_size=MAX_MESSAGE_SIZE,
                ping_interval=20,
                ping_timeout=10
            )
            logger.info("Chat server started successfully")
        except OSError as e:
            logger.error(f"Failed to start server: {e}")
            self._running = False
            raise
    
    async def stop(self) -> None:
        """Gracefully stop the server and close all connections."""
        if not self._running:
            return
            
        logger.info("Stopping chat server...")
        self._running = False
        
        # Close all active connections
        async with self._lock:
            for user in list(self._users.values()):
                await self._safe_close(user.websocket, code=1001, reason="Server shutting down")
            self._users.clear()
            self._username_map.clear()
        
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        
        logger.info("Chat server stopped")
    
    async def _handle_connection(self, websocket: WebSocketServerProtocol) -> None:
        """
        Handle a new WebSocket connection lifecycle.
        
        Args:
            websocket: The WebSocket connection protocol instance
        """
        user_id = str(uuid.uuid4())
        user: Optional[ConnectedUser] = None
        
        try:
            # Check connection limit
            async with self._lock:
                if len(self._users) >= self.max_connections:
                    await self._send_error(websocket, "Server at capacity", 429)
                    await websocket.close(code=1013, reason="Server at capacity")
                    return
            
            # Wait for initial registration message
            try:
                raw_message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            except asyncio.TimeoutError:
                await websocket.close(code=1002, reason="Registration timeout")
                return
            
            # Parse and validate registration
            try:
                message = json.loads(raw_message)
                if not isinstance(message, dict):
                    raise ValueError("Message must be a JSON object")
            except json.JSONDecodeError:
                await self._send_error(websocket, "Invalid JSON format", 400)
                await websocket.close(code=1003, reason="Invalid JSON")
                return
            
            # Validate registration payload
            if message.get("type") != "register":
                await self._send_error(websocket, "First message must be registration", 400)
                await websocket.close(code=1008, reason="Protocol violation")
                return
            
            username = message.get("username", "").strip()
            if not self._validate_username(username):
                await self._send_error(websocket, "Invalid username format", 400)
                await websocket.close(code=1008, reason="Invalid username")
                return
            
            # Register user
            async with self._lock:
                if username in self._username_map:
                    await self._send_error(websocket, "Username already taken", 409)
                    await websocket.close(code=1008, reason="Username taken")
                    return
                
                user = ConnectedUser(
                    user_id=user_id,
                    username=username,
                    websocket=websocket,
                    connected_at=asyncio.get_event_loop().time()
                )
                self._users[user_id] = user
                self._username_map[username] = user_id
            
            logger.info(f"User registered: {username} ({user_id})")
            
            # Send welcome message with user list
            await self._send_welcome(user)
            await self._broadcast_user_join(user)
            
            # Main message loop
            async for raw_message in websocket:
                await self._process_message(user, raw_message)
                
        except ConnectionClosed:
            logger.debug(f"Connection closed for user {user_id}")
        except WebSocketException as e:
            logger.warning(f"WebSocket error for user {user_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error for user {user_id}: {e}", exc_info=True)
        finally:
            if user:
                await self._handle_disconnect(user)
    
    async def _process_message(self, user: ConnectedUser, raw_message: str) -> None:
        """
        Process an incoming message from a connected user.
        
        Args:
            user: The sending user
            raw_message: Raw message string from WebSocket
        """
        try:
            # Validate message size
            if len(raw_message) > MAX_MESSAGE_SIZE:
                await self._send_error(user.websocket, "Message too large", 413)
                return
            
            # Parse JSON
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                await self._send_error(user.websocket, "Invalid JSON format", 400)
                return
            
            if not isinstance(message, dict):
                await self._send_error(user.websocket, "Message must be a JSON object", 400)
                return
            
            # Validate message type
            msg_type = message.get("type")
            if msg_type not in MESSAGE_TYPES:
                await self._send_error(user.websocket, f"Unknown message type: {msg_type}", 400)
                return
            
            # Route to appropriate handler
            if msg_type == "broadcast":
                await self._handle_broadcast(user, message)
            elif msg_type == "private":
                await self._handle_private_message(user, message)
            elif msg_type == "user_list":
                await self._send_user_list(user)
            else:
                # Custom handler for extensibility
                if self.custom_handler:
                    await self.custom_handler(user, message)
                    
        except Exception as e:
            logger.error(f"Error processing message from {user.username}: {e}", exc_info=True)
            await self._send_error(user.websocket, "Internal server error", 500)
    
    async def _handle_broadcast(self, sender: ConnectedUser, message: dict) -> None:
        """
        Handle a broadcast message to all connected users.
        
        Args:
            sender: The user sending the message
            message: Parsed message dictionary
        """
        content = message.get("content", "").strip()
        if not content:
            await self._send_error(sender.websocket, "Empty broadcast message", 400)
            return
        
        # Sanitize content (basic example)
        sanitized_content = self._sanitize_content(content)
        
        broadcast_msg = {
            "type": "broadcast",
            "sender": sender.username,
            "sender_id": sender.user_id,
            "content": sanitized_content,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        await self._broadcast(broadcast_msg, exclude_user_id=sender.user_id)
    
    async def _handle_private_message(self, sender: ConnectedUser, message: dict) -> None:
        """
        Handle a private message to a specific user.
        
        Args:
            sender: The user sending the message
            message: Parsed message dictionary
        """
        target_username = message.get("target", "").strip()
        content = message.get("content", "").strip()
        
        if not target_username:
            await self._send_error(sender.websocket, "Missing target username", 400)
            return
        
        if not content:
            await self._send_error(sender.websocket, "Empty private message", 400)
            return
        
        # Find target user
        async with self._lock:
            target_user_id = self._username_map.get(target_username)
            if not target_user_id:
                await self._send_error(sender.websocket, "User not found", 404)
                return
            
            target_user = self._users.get(target_user_id)
            if not target_user:
                await self._send_error(sender.websocket, "User not found", 404)
                return
        
        # Sanitize content
        sanitized_content = self._sanitize_content(content)
        
        # Send to target
        private_msg = {
            "type": "private",
            "sender": sender.username,
            "sender_id": sender.user_id,
            "content": sanitized_content,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        try:
            await target_user.websocket.send(json.dumps(private_msg))
        except ConnectionClosed:
            logger.warning(f"Failed to deliver private message to {target_username}")
            await self._send_error(sender.websocket, "Recipient disconnected", 410)
        
        # Confirm delivery to sender
        confirm_msg = {
            "type": "private_sent",
            "target": target_username,
            "content": sanitized_content,
            "timestamp": asyncio.get_event_loop().time()
        }
        await sender.websocket.send(json.dumps(confirm_msg))
    
    async def _send_welcome(self, user: ConnectedUser) -> None:
        """Send welcome message with current user list to a newly connected user."""
        async with self._lock:
            user_list = [
                {"user_id": u.user_id, "username": u.username}
                for u in self._users.values()
            ]
        
        welcome_msg = {
            "type": "welcome",
            "your_user_id": user.user_id,
            "your_username": user.username,
            "users": user_list,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        await user.websocket.send(json.dumps(welcome_msg))
    
    async def _send_user_list(self, user: ConnectedUser) -> None:
        """Send current user list to requesting user."""
        async with self._lock:
            user_list = [
                {"user_id": u.user_id, "username": u.username}
                for u in self._users.values()
            ]
        
        list_msg = {
            "type": "user_list",
            "users": user_list,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        await user.websocket.send(json.dumps(list_msg))
    
    async def _broadcast_user_join(self, user: ConnectedUser) -> None:
        """Broadcast a user join notification to all other users."""
        join_msg = {
            "type": "user_joined",
            "user_id": user.user_id,
            "username": user.username,
            "timestamp": asyncio.get_event_loop().time()
        }
        await self._broadcast(join_msg, exclude_user_id=user.user_id)
    
    async def _broadcast_user_left(self, user: ConnectedUser) -> None:
        """Broadcast a user leave notification to all other users."""
        leave_msg = {
            "type": "user_left",
            "user_id": user.user_id,
            "username": user.username,
            "timestamp": asyncio.get_event_loop().time()
        }
        await self._broadcast(leave_msg, exclude_user_id=user.user_id)
    
    async def _broadcast(
        self,
        message: dict,
        exclude_user_id: Optional[str] = None
    ) -> None:
        """
        Broadcast a message to all connected users except optionally one.
        
        Args:
            message: Message dictionary to broadcast
            exclude_user_id: Optional user ID to exclude from broadcast
        """
        message_str = json.dumps(message)
        disconnected = []
        
        async with self._lock:
            users_to_send = [
                u for u in self._users.values()
                if u.user_id != exclude_user_id
            ]
        
        for user in users_to_send:
            try:
                await user.websocket.send(message_str)
            except ConnectionClosed:
                disconnected.append(user.user_id)
            except Exception as e:
                logger.error(f"Error broadcasting to {user.username}: {e}")
                disconnected.append(user.user_id)
        
        # Clean up disconnected users
        if disconnected:
            async with self._lock:
                for user_id in disconnected:
                    if user_id in self._users:
                        user = self._users.pop(user_id)
                        self._username_map.pop(user.username, None)
                        logger.info(f"Cleaned up disconnected user: {user.username}")
    
    async def _handle_disconnect(self, user: ConnectedUser) -> None:
        """
        Handle user disconnection cleanup.
        
        Args:
            user: The disconnected user
        """
        async with self._lock:
            if user.user_id in self._users:
                self._users.pop(user.user_id, None)
                self._username_map.pop(user.username, None)
                logger.info(f"User disconnected: {user.username} ({user.user_id})")
                
                # Broadcast leave notification
                await self._broadcast_user_left(user)
    
    async def _send_error(
        self,
        websocket: WebSocketServerProtocol,
        message: str,
        code: int = 400
    ) -> None:
        """
        Send an error message to a WebSocket connection.
        
        Args:
            websocket: Target WebSocket connection
            message: Error message
            code: HTTP-style error code
        """
        error_msg = {
            "type": "error",
            "code": code,
            "message": message,
            "timestamp": asyncio.get_event_loop().time()
        }
        try:
            await websocket.send(json.dumps(error_msg))
        except Exception:
            pass  # Ignore errors when sending errors
    
    async def _safe_close(
        self,
        websocket: WebSocketServerProtocol,
        code: int = 1000,
        reason: str = ""
    ) -> None:
        """
        Safely close a WebSocket connection.
        
        Args:
            websocket: WebSocket to close
            code: Close code
            reason: Close reason
        """
        try:
            await websocket.close(code=code, reason=reason)
        except Exception:
            pass
    
    def _validate_username(self, username: str)