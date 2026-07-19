"""
### Task 5: Chatbot (FastAPI + Redis)

A multi-turn chatbot service with per-user conversation history stored in
Redis, an abstracted (stubbed) LLM call, per-user and per-IP rate
limiting, and fallback responses on failure.

Requirements:
    pip install fastapi "uvicorn[standard]" redis pydantic

Run:
    export REDIS_URL=redis://localhost:6379/0
    uvicorn 05_chatbot:app --host 0.0.0.0 --port 8003
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import List, Optional

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("chatbot")

REDIS_URL = "redis://localhost:6379/0"
HISTORY_LIMIT = 20
USER_RATE_LIMIT = 20  # messages per window
IP_RATE_LIMIT = 60  # messages per window
RATE_LIMIT_WINDOW_SECONDS = 60

app = FastAPI(title="Chatbot Service")
redis_client: Optional[aioredis.Redis] = None


class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    user_id: str
    reply: str
    history_length: int


@app.on_event("startup")
async def on_startup() -> None:
    global redis_client
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Chatbot service connected to Redis at %s", REDIS_URL)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if redis_client is not None:
        await redis_client.close()


def _history_key(user_id: str) -> str:
    return f"chatbot:history:{user_id}"


async def get_conversation_history(user_id: str) -> List[dict]:
    """Fetches the recent conversation turns for a user from Redis."""
    assert redis_client is not None
    try:
        raw = await redis_client.lrange(_history_key(user_id), 0, -1)
        return [json.loads(item) for item in raw]
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load history for '%s': %s", user_id, exc)
        return []


async def append_to_history(user_id: str, role: str, content: str) -> None:
    """Appends a turn to a user's conversation history, trimming to the limit."""
    assert redis_client is not None
    entry = json.dumps({"role": role, "content": content, "timestamp": datetime.utcnow().isoformat()})
    try:
        await redis_client.rpush(_history_key(user_id), entry)
        await redis_client.ltrim(_history_key(user_id), -HISTORY_LIMIT, -1)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to persist history for '%s': %s", user_id, exc)


async def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """Sliding-window-ish rate limiter using a Redis counter with TTL.

    Returns:
        True if the request is allowed, False if the limit has been exceeded.
    """
    assert redis_client is not None
    try:
        current = await redis_client.incr(key)
        if current == 1:
            await redis_client.expire(key, window_seconds)
        return current <= limit
    except Exception as exc:  # noqa: BLE001
        logger.error("Rate limit check failed for '%s': %s", key, exc)
        # Fail open: if Redis is unavailable, don't block legitimate traffic.
        return True


async def call_llm(user_id: str, message: str, history: List[dict]) -> str:
    """Stub for an actual LLM API call.

    In production, replace this with a real call to your model provider,
    passing `history` as context alongside `message`.
    """
    try:
        # --- Placeholder for a real LLM integration ---
        # response = await some_llm_client.chat(messages=history + [{"role": "user", "content": message}])
        # return response.text
        logger.info("Generating stubbed reply for user '%s'", user_id)
        return f"(stubbed reply) You said: '{message}'. I have {len(history)} prior turn(s) of context."
    except Exception as exc:  # noqa: BLE001
        logger.error("LLM call failed for '%s': %s", user_id, exc)
        raise


FALLBACK_RESPONSE = "Sorry, I'm having trouble responding right now. Please try again shortly."


@app.post("/chat", response_model=ChatResponse)
async def chat(request: Request, chat_request: ChatRequest) -> ChatResponse:
    """Handles a single chat turn: rate limiting, history, LLM call, fallback."""
    client_ip = request.client.host if request.client else "unknown"

    user_allowed = await check_rate_limit(
        f"chatbot:ratelimit:user:{chat_request.user_id}", USER_RATE_LIMIT, RATE_LIMIT_WINDOW_SECONDS
    )
    ip_allowed = await check_rate_limit(
        f"chatbot:ratelimit:ip:{client_ip}", IP_RATE_LIMIT, RATE_LIMIT_WINDOW_SECONDS
    )

    if not user_allowed or not ip_allowed:
        logger.warning("Rate limit exceeded for user='%s' ip='%s'", chat_request.user_id, client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded, please slow down",
        )

    history = await get_conversation_history(chat_request.user_id)

    try:
        reply = await call_llm(chat_request.user_id, chat_request.message, history)
    except Exception:  # noqa: BLE001
        reply = FALLBACK_RESPONSE

    await append_to_history(chat_request.user_id, "user", chat_request.message)
    await append_to_history(chat_request.user_id, "assistant", reply)

    updated_history = await get_conversation_history(chat_request.user_id)
    return ChatResponse(user_id=chat_request.user_id, reply=reply, history_length=len(updated_history))


@app.get("/chat/{user_id}/history")
async def get_history_endpoint(user_id: str) -> dict:
    """Returns the stored conversation history for a user."""
    history = await get_conversation_history(user_id)
    return {"user_id": user_id, "history": history}


@app.delete("/chat/{user_id}/history")
async def clear_history_endpoint(user_id: str) -> dict:
    """Clears a user's conversation history."""
    assert redis_client is not None
    await redis_client.delete(_history_key(user_id))
    return {"message": f"history cleared for user '{user_id}'"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": time.time()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
