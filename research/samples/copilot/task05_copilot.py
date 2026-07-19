"""
Chatbot API using FastAPI and Redis.
Features:
- Context memory (conversation history per user)
- Stubbed LLM integration
- Rate limiting (per user and IP)
- Multi-turn dialogue
- Fallback responses
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional

import aioredis
from fastapi import FastAPI, Depends, HTTPException, Request, status
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)

# Redis connection
redis = None


async def get_redis() -> aioredis.Redis:
    """Get Redis connection."""
    global redis
    if redis is None:
        redis = await aioredis.from_url("redis://localhost")
    return redis


# FastAPI app
app = FastAPI(title="Chatbot API")


# Pydantic models
class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    response: str
    history: List[str]


# Utility functions
async def rate_limit(user_id: str, ip: str, redis: aioredis.Redis, limit: int = 5, window: int = 60) -> None:
    """Rate limit per user and IP.

    Args:
        user_id (str): User identifier.
        ip (str): Client IP.
        redis (aioredis.Redis): Redis connection.
        limit (int): Max requests allowed.
        window (int): Time window in seconds.
    """
    key = f"rate:{user_id}:{ip}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window)
    if count > limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")


async def get_history(user_id: str, redis: aioredis.Redis) -> List[str]:
    """Retrieve conversation history."""
    return await redis.lrange(f"history:{user_id}", 0, -1)


async def add_to_history(user_id: str, message: str, redis: aioredis.Redis) -> None:
    """Add message to conversation history."""
    await redis.rpush(f"history:{user_id}", message)
    await redis.ltrim(f"history:{user_id}", -20, -1)  # Keep last 20 messages


async def llm_stub(message: str, history: List[str]) -> str:
    """Stubbed LLM response generator.

    Args:
        message (str): User message.
        history (List[str]): Conversation history.

    Returns:
        str: Chatbot response.
    """
    # Simple echo logic with fallback
    if "hello" in message.lower():
        return "Hi there! How can I help you today?"
    elif "bye" in message.lower():
        return "Goodbye! Have a great day."
    elif history:
        return f"You said: {message}. Previously you mentioned: {history[-1]}"
    else:
        return "I'm not sure how to respond, but I'm here to help."


# Routes
@app.post("/chat", response_model=ChatResponse)
async def chat(request: Request, chat_req: ChatRequest, redis: aioredis.Redis = Depends(get_redis)):
    """Handle chat requests with context memory and rate limiting."""
    ip = request.client.host
    await rate_limit(chat_req.user_id, ip, redis)

    # Add user message to history
    await add_to_history(chat_req.user_id, f"User: {chat_req.message}", redis)

    # Get history
    history = await get_history(chat_req.user_id, redis)

    # Generate response
    response = await llm_stub(chat_req.message, history)

    # Add bot response to history
    await add_to_history(chat_req.user_id, f"Bot: {response}", redis)

    return ChatResponse(response=response, history=[msg.decode() if isinstance(msg, bytes) else msg for msg in history])


@app.on_event("startup")
async def startup_event():
    """Initialize Redis connection on startup."""
    await get_redis()
    logging.info("Redis connection established.")


@app.on_event("shutdown")
async def shutdown_event():
    """Close Redis connection on shutdown."""
    global redis
    if redis:
        await redis.close()
        logging.info("Redis connection closed.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

