"""
Task 14: FastAPI Real-time WebSocket Messaging Core
Features: Redis Pub/Sub backend broker channels, room-based broadcast isolation, online presence tracking layers.
Requires: fastapi, uvicorn, redis, websockets
"""

import json
import logging
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status
import redis
import asyncio

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Production WebSocket Message Broker Engine", version="1.0.0")

# --- Redis Storage Infrastructure Interface Layer ---
class InMemoryFallbackBroker:
    """Fallback structural engine mapping connections mock states if Redis servers are offline."""
    def __init__(self) -> None:
        self.channels: Dict[str, List[str]] = {}
        self.presence: Set[str] = set()
    def publish(self, channel: str, message: str) -> None: logger.info(f"[Mock Pub] Channel {channel} -> {message}")
    def rpush(self, key: str, value: str) -> None: pass
    def lrange(self, key: str, start: int, stop: int) -> List[str]: return []
    def sadd(self, key: str, value: str) -> None: pass
    def srem(self, key: str, value: str) -> None: pass

try:
    redis_conn = redis.Redis(host='localhost', port=6379, db=2, decode_responses=True)
    redis_conn.ping()
    logger.info("WebSocket publish/subscribe layer connected directly to live Redis nodes.")
except Exception:
    logger.warning("External Redis broker instances unreachable. Initializing safe memory fallbacks.")
    redis_conn = InMemoryFallbackBroker()  # type: ignore

# --- Connections Allocation Tracker Orchestrator ---

class WebSocketConnectionManager:
    """Orchestrates internal local in-memory socket pathways across explicit dynamic execution loops."""
    
    def __init__(self) -> None:
        # Maps active channel rooms to list of localized open socket endpoints
        self.room_registry: Dict[str, List[WebSocket]] = {}

    async def connect_client_socket(self, socket_channel_id: str, client_websocket: WebSocket) -> None:
        """Registers and establishes a permanent connection across the active room registry."""
        await client_websocket.accept()
        if socket_channel_id not in self.room_registry:
            self.room_registry[socket_channel_id] = []
        self.room_registry[socket_channel_id].append(client_websocket)
        
        # Sync global cluster state maps via Redis presence tracking pools
        redis_conn.sadd(f"presence:room:{socket_channel_id}", f"User_{id(client_websocket)}")
        logger.info(f"Socket interface accepted under channel identification tree context: {socket_channel_id}")

    def detach_client_socket(self, socket_channel_id: str, client_websocket: WebSocket) -> None:
        """Cleans internal memory footprints once socket allocations drop connection lines."""
        if socket_channel_id in self.room_registry:
            self.room_registry[socket_channel_id].remove(client_websocket)
            if not self.room_registry[socket_channel_id]:
                del self.room_registry[socket_channel_id]
        redis_conn.srem(f"presence:room:{socket_channel_id}", f"User_{id(client_websocket)}")

    async def broadcast_isolated_payload(self, target_room_id: str, raw_text_packet: str) -> None:
        """Iterates over targeted connection nodes to transmit payload messages safely."""
        if target_room_id in self.room_registry:
            dead_connections: List[WebSocket] = []
            for client_connection in self.room_registry[target_room_id]:
                try:
                    await client_connection.send_text(raw_text_packet)
                except Exception:
                    dead_connections.append(client_connection)
                    
            for stale_socket in dead_connections:
                self.detach_client_socket(target_room_id, stale_socket)

socket_manager = WebSocketConnectionManager()

# --- Async Background Task Redis Core Listener Loop ---

async def listen_redis_pubsub_channels() -> None:
    """Listens for cross-process broadcast packets across distributed nodes."""
    if isinstance(redis_conn, InMemoryFallbackBroker):
        return
    try:
        pubsub_broker = redis_conn.pubsub()
        pubsub_broker.psubscribe("chat_room:*")
        logger.info("Global async message distribution loop successfully running.")
        
        while True:
            packet_message = pubsub_broker.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if packet_message:
                channel_string = str(packet_message['channel'])
                room_identifier = channel_string.split(":")[-1]
                data_payload = str(packet_message['data'])
                
                await socket_manager.broadcast_isolated_payload(room_identifier, data_payload)
            await asyncio.sleep(0.01)
    except Exception as async_loop_err:
        logger.error(f"Distributed subscription event framework exception: {async_loop_err}")

@app.on_event("startup")
def trigger_background_listeners() -> None:
    """Binds structural synchronization loops directly into active event runtime instances."""
    asyncio.create_task(listen_redis_pubsub_channels())

# --- REST & Socket Route Controller Pipelines ---

@app.get("/rooms/{room_id}/history")
def extract_historical_message_ledger(room_id: str) -> Any:
    """Queries Redis arrays to pull trailing conversational items."""
    history_stack = redis_conn.lrange(f"history:room:{room_id}", -50, -1)
    parsed_history = [json.loads(msg) for msg in history_stack]
    return {"room_id": room_id, "historical_logs": parsed_history}

@app.websocket("/ws/chat/{room_id}")
async def handle_websocket_chat_stream(websocket: WebSocket, room_id: str) -> None:
    """Manages full-duplex framing, reading ingress commands and emitting egress broadcasts."""
    await socket_manager.connect_client_socket(room_id, websocket)
    try:
        while True:
            # Process incoming frame strings from network interfaces
            ingress_message_string = await websocket.receive_text()
            
            structured_message_envelope = {
                "room_id": room_id,
                "message": ingress_message_string,
                "timestamp": float(asyncio.get_event_loop().time())
            }
            serialized_payload = json.dumps(structured_message_envelope)

            # Persist transactions down directly into backup logging metrics lines
            redis_conn.rpush(f"history:room:{room_id}", serialized_payload)
            
            # Broadcast the event across the cluster node layout matrices
            if not isinstance(redis_conn, InMemoryFallbackBroker):
                redis_conn.publish(f"chat_room:{room_id}", serialized_payload)
            else:
                await socket_manager.broadcast_isolated_payload(room_id, serialized_payload)
                
    except WebSocketDisconnect:
        logger.info("Client cleanly separated pipeline traces away from current socket channel.")
    finally:
        socket_manager.detach_client_socket(room_id, websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
