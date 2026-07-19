"""FastAPI Chatbot with Redis context, rate limiting, and LLM stub."""
import time, logging, asyncio
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import redis.asyncio as redis

logging.basicConfig(level=logging.INFO)
app = FastAPI()
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

RATE_LIMIT = 5  # requests per minute
LLM_STUB_RESPONSES = ["I understand.", "Tell me more.", "That's interesting.", "I'm just an AI."]

class Message(BaseModel):
    user_id: str
    message: str

async def check_rate_limit(user_id: str, ip: str):
    """Check rate limits for user and IP."""
    for key in [f"rate:user:{user_id}", f"rate:ip:{ip}"]:
        current = await redis_client.incr(key)
        if current == 1:
            await redis_client.expire(key, 60)
        if current > RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

async def get_llm_response(context: List[str]) -> str:
    """Stub LLM call with simulated latency."""
    await asyncio.sleep(0.5)
    import random
    return random.choice(LLM_STUB_RESPONSES)

@app.post("/chat")
async def chat(msg: Message, request: Request):
    await check_rate_limit(msg.user_id, request.client.host)
    
    ctx_key = f"context:{msg.user_id}"
    history: List[str] = await redis_client.lrange(ctx_key, 0, -1)
    
    if len(history) > 10:  # Keep context manageable
        await redis_client.ltrim(ctx_key, -10, -1)
        history = await redis_client.lrange(ctx_key, 0, -1)
        
    await redis_client.rpush(ctx_key, f"User: {msg.message}")
    
    try:
        bot_reply = await get_llm_response(history)
    except Exception as e:
        logging.error(f"LLM Error: {e}")
        bot_reply = "Sorry, I'm having trouble thinking right now."
        
    await redis_client.rpush(ctx_key, f"Bot: {bot_reply}")
    return {"reply": bot_reply}

@app.get("/history/{user_id}")
async def get_history(user_id: str):
    return await redis_client.lrange(f"context:{user_id}", 0, -1)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)