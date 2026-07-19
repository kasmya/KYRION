"""
Chatbot API with conversation memory, rate limiting, and multi-turn dialogue.

Features:
- Context memory with conversation history per user
- LLM API integration (stubbed)
- Rate limiting per user and IP
- Multi-turn dialogue support
- Fallback responses
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import json
import hashlib
import asyncio
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
import redis.asyncio as redis
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('chatbot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="Chatbot API",
    description="Context-aware chatbot with conversation memory",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = None

# Rate limiting configuration
RATE_LIMIT_REQUESTS = 30  # requests per minute
RATE_LIMIT_WINDOW = 60  # seconds
CONVERSATION_TTL = 3600  # 1 hour conversation memory

class ChatMessage(BaseModel):
    """Chat message model."""
    user_id: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    
    @validator('message')
    def validate_message(cls, v: str) -> str:
        """Validate and clean message."""
        v = v.strip()
        if not v:
            raise ValueError('Message cannot be empty')
        return v

class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    confidence: float = Field(ge=0.0, le=1.0)
    conversation_id: str
    timestamp: str

class RateLimiter:
    """Redis-based rate limiter."""
    
    def __init__(self, redis_client: redis.Redis):
        """Initialize rate limiter."""
        self.redis = redis_client
    
    async def is_rate_limited(
        self,
        user_id: str,
        ip_address: str,
        limit: int = RATE_LIMIT_REQUESTS,
        window: int = RATE_LIMIT_WINDOW
    ) -> bool:
        """
        Check if request should be rate limited.
        
        Args:
            user_id: User identifier
            ip_address: IP address
            limit: Maximum requests per window
            window: Time window in seconds
            
        Returns:
            True if rate limited, False otherwise
        """
        # Check per-user rate
        user_key = f"rate_limit:user:{user_id}"
        user_count = await self.redis.get(user_key)
        
        if user_count is None:
            await self.redis.setex(user_key, window, 1)
        elif int(user_count) >= limit:
            logger.warning(f"Rate limit exceeded for user: {user_id}")
            return True
        else:
            await self.redis.incr(user_key)
        
        # Check per-IP rate
        ip_key = f"rate_limit:ip:{ip_address}"
        ip_count = await self.redis.get(ip_key)
        
        if ip_count is None:
            await self.redis.setex(ip_key, window, 1)
        elif int(ip_count) >= limit:
            logger.warning(f"Rate limit exceeded for IP: {ip_address}")
            return True
        else:
            await self.redis.incr(ip_key)
        
        return False

class ConversationManager:
    """Manages conversation history and context."""
    
    def __init__(self, redis_client: redis.Redis):
        """Initialize conversation manager."""
        self.redis = redis_client
    
    async def get_conversation(
        self,
        user_id: str,
        max_history: int = 10
    ) -> List[Dict[str, str]]:
        """
        Get conversation history for user.
        
        Args:
            user_id: User identifier
            max_history: Maximum number of messages to retrieve
            
        Returns:
            List of conversation messages
        """
        key = f"conversation:{user_id}"
        messages = await self.redis.lrange(key, -max_history * 2, -1)
        
        conversation = []
        for msg_json in messages:
            try:
                msg = json.loads(msg_json)
                conversation.append(msg)
            except json.JSONDecodeError:
                continue
        
        return conversation
    
    async def add_message(
        self,
        user_id: str,
        role: str,
        content: str,
        ttl: int = CONVERSATION_TTL
    ) -> None:
        """
        Add message to conversation history.
        
        Args:
            user_id: User identifier
            role: Message role (user/assistant)
            content: Message content
            ttl: Time-to-live in seconds
        """
        key = f"conversation:{user_id}"
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        await self.redis.rpush(key, json.dumps(message))
        await self.redis.expire(key, ttl)
    
    async def get_context(
        self,
        user_id: str,
        max_history: int = 5
    ) -> str:
        """
        Get conversation context for LLM.
        
        Args:
            user_id: User identifier
            max_history: Maximum history messages
            
        Returns:
            Formatted context string
        """
        conversation = await self.get_conversation(user_id, max_history)
        
        if not conversation:
            return ""
        
        context = "Previous conversation:\n"
        for msg in conversation:
            role = "User" if msg["role"] == "user" else "Assistant"
            context += f"{role}: {msg['content']}\n"
        
        return context
    
    async def clear_conversation(self, user_id: str) -> None:
        """
        Clear conversation history for user.
        
        Args:
            user_id: User identifier
        """
        key = f"conversation:{user_id}"
        await self.redis.delete(key)
        logger.info(f"Cleared conversation for user: {user_id}")

class LLMStub:
    """
    Stub for LLM API integration.
    Replace this with actual API calls (OpenAI, Anthropic, etc.)
    """
    
    FALLBACK_RESPONSES = [
        "I understand what you're saying. Could you tell me more about that?",
        "That's an interesting point. Let me think about it.",
        "I see. Is there anything specific you'd like to know?",
        "Thanks for sharing that with me. How can I help you further?",
        "I appreciate your question. Let me provide more information.",
        "Based on what you've told me, I think we should explore this further.",
        "I'm not sure I fully understand. Could you rephrase that?",
        "That's a great question! Let me try to help you with that.",
    ]
    
    @staticmethod
    async def generate_response(
        message: str,
        context: str = "",
        conversation_history: List[Dict[str, str]] = None
    ) -> tuple:
        """
        Generate chatbot response (stubbed).
        
        Args:
            message: User message
            context: Conversation context
            conversation_history: Previous messages
            
        Returns:
            Tuple of (response_text, confidence)
        """
        # Simulate API latency
        await asyncio.sleep(0.5)
        
        # Simple pattern matching for demo
        message_lower = message.lower()
        
        # Check for greetings
        if any(word in message_lower for word in ['hi', 'hello', 'hey', 'greetings']):
            return "Hello! How can I help you today?", 0.95
        
        # Check for farewells
        if any(word in message_lower for word in ['bye', 'goodbye', 'see you']):
            return "Goodbye! It was nice talking to you. Feel free to come back anytime!", 0.95
        
        # Check for questions about the bot
        if any(phrase in message_lower for phrase in ['who are you', 'what are you']):
            return "I'm an AI assistant designed to help answer questions and have conversations. How can I assist you?", 0.9
        
        # Check for help requests
        if 'help' in message_lower:
            return "I'm here to help! You can ask me questions, have a conversation, or request information on various topics. What would you like to know?", 0.9
        
        # Use context for more relevant responses
        if context:
            return f"Based on our conversation, I think I can help with that. {random.choice(LLMStub.FALLBACK_RESPONSES)}", 0.7
        
        # Fallback response
        import random
        return random.choice(LLMStub.FALLBACK_RESPONSES), 0.6

@app.on_event("startup")
async def startup():
    """Initialize Redis connection on startup."""
    global redis_client
    try:
        redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
        await redis_client.ping()
        logger.info("Connected to Redis")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        raise

@app.on_event("shutdown")
async def shutdown():
    """Close Redis connection on shutdown."""
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Middleware for rate limiting."""
    if redis_client:
        # Get client IP
        ip_address = request.client.host
        
        # Get user ID from request
        user_id = None
        if request.method == "POST":
            try:
                body = await request.json()
                user_id = body.get("user_id", ip_address)
            except:
                user_id = ip_address
        
        if user_id:
            rate_limiter = RateLimiter(redis_client)
            is_limited = await rate_limiter.is_rate_limited(user_id, ip_address)
            
            if is_limited:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again later."}
                )
    
    response = await call_next(request)
    return response

@app.post("/chat", response_model=ChatResponse)
async def chat(message: ChatMessage, request: Request) -> ChatResponse:
    """
    Process chat message and return response.
    
    Args:
        message: Chat message from user
        request: FastAPI request object
        
    Returns:
        Chat response with context awareness
    """
    try:
        if not redis_client:
            raise HTTPException(
                status_code=503,
                detail="Chat service unavailable"
            )
        
        conversation_manager = ConversationManager(redis_client)
        user_id = message.user_id
        
        # Get conversation context
        context = await conversation_manager.get_context(user_id)
        history = await conversation_manager.get_conversation(user_id)
        
        # Add user message to history
        await conversation_manager.add_message(user_id, "user", message.message)
        
        # Generate response (stubbed LLM call)
        response_text, confidence = await LLMStub.generate_response(
            message.message,
            context,
            history
        )
        
        # Add assistant response to history
        await conversation_manager.add_message(user_id, "assistant", response_text)
        
        # Generate conversation ID
        conversation_id = hashlib.md5(
            f"{user_id}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]
        
        logger.info(f"Chat processed for user {user_id}: {message.message[:50]}...")
        
        return ChatResponse(
            response=response_text,
            confidence=confidence,
            conversation_id=conversation_id,
            timestamp=datetime.now().isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

@app.get("/history/{user_id}")
async def get_history(
    user_id: str,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Get conversation history for user.
    
    Args:
        user_id: User identifier
        limit: Maximum number of messages
        
    Returns:
        Conversation history
    """
    try:
        if not redis_client:
            raise HTTPException(status_code=503, detail="Service unavailable")
        
        conversation_manager = ConversationManager(redis_client)
        history = await conversation_manager.get_conversation(user_id, limit)
        
        return {
            "user_id": user_id,
            "messages": history,
            "count": len(history)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"History error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/history/{user_id}")
async def clear_history(user_id: str) -> Dict[str, str]:
    """
    Clear conversation history for user.
    
    Args:
        user_id: User identifier
        
    Returns:
        Success message
    """
    try:
        if not redis_client:
            raise HTTPException(status_code=503, detail="Service unavailable")
        
        conversation_manager = ConversationManager(redis_client)
        await conversation_manager.clear_conversation(user_id)
        
        return {"message": f"History cleared for user {user_id}"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Clear history error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    if redis_client:
        try:
            await redis_client.ping()
            return {"status": "healthy", "redis": "connected"}
        except:
            return {"status": "unhealthy", "redis": "disconnected"}
    return {"status": "healthy", "redis": "not configured"}

if __name__ == "__main__":
    import uvicorn
    import random
    uvicorn.run(app, host="0.0.0.0", port=8002, reload=True)
