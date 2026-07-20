from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import uuid
import hashlib
import logging

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI App
app = FastAPI(
    title="E-commerce REST API",
    description="A simple e-commerce API",
    version="1.0.0"
)

# Security Setup (Basic Auth for Demo; Use more secure methods in production)
security = HTTPBasic()

# In-Memory Data Stores (Replace with Database in Production)
products: dict[str, dict] = {
    "1": {"id": "1", "name": "Product 1", "price": 9.99},
    "2": {"id": "2", "name": "Product 2", "price": 19.99}
}

cart: dict[str, dict] = {}

class Product(BaseModel):
    """Product Model"""
    id: str
    name: str
    price: float

class CartItem(BaseModel):
    """Cart Item Model"""
    product_id: str
    quantity: int = 1

class User(BaseModel):
    """User Model for Basic Auth"""
    username: str
    hashed_password: str

# In-Memory User Store (Replace with Secure Auth in Production)
users: dict[str, User] = {
    "user1": User(username="user1", hashed_password=hashlib.sha256("password1".encode()).hexdigest()),
    "admin": User(username="admin", hashed_password=hashlib.sha256("admin".encode()).hexdigest())
}

async def get_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Validate User Credentials"""
    user = users.get(credentials.username)
    if not user or user.hashed_password != hashlib.sha256(credentials.password.encode()).hexdigest():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Basic"}
        )

# Endpoints

@app.get("/products", response_model=List[Product])
async def read_products(credentials: HTTPBasicCredentials = Depends(get_credentials)):
    """List All Products"""
    return list(products.values())

@app.get("/products/{product_id}", response_model=Product)
async def read_product(product_id: str, credentials: HTTPBasicCredentials = Depends(get_credentials)):
    """Get Product Details"""
    product = products.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@app.post("/cart", status_code=status.HTTP_201_CREATED)
async def add_to_cart(item: CartItem, credentials: HTTPBasicCredentials = Depends(get_credentials)):
    """Add Item to Cart"""
    user_id = credentials.username
    if user_id not in cart:
        cart[user_id] = {}
    cart_id = str(uuid.uuid4())
    cart[user_id][cart_id] = {"product_id": item.product_id, "quantity": item.quantity}
    logger.info(f"Added to cart: {item.product_id} for user {user_id}")
    return {"cart_id": cart_id}

@app.get("/cart", response_model=dict[str, dict])
async def view_cart(credentials: HTTPBasicCredentials = Depends(get_credentials)):
    """View Cart Contents"""
    return cart.get(credentials.username, {})

@app.delete("/cart/{cart_id}")
async def remove_from_cart(cart_id: str, credentials: HTTPBasicCredentials = Depends(get_credentials)):
    """Remove Item from Cart"""
    user_id = credentials.username
    if user_id in cart and cart_id in cart[user_id]:
        del cart[user_id][cart_id]
        logger.info(f"Removed from cart: {cart_id} for user {user_id}")
        return JSONResponse(content={"message": "Item removed from cart"}, status_code=200)
    else:
        raise HTTPException(status_code=404, detail="Cart item not found")

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP Exceptions"""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})