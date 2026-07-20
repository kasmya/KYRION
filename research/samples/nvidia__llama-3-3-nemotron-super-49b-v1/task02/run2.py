from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import List, Dict, Optional
from uuid import UUID, uuid4
import json
import hashlib
import os

# Initialize FastAPI App
app = FastAPI()

# Security: Basic Auth for protected routes
security = HTTPBasic()

# In-Memory Data Stores (Replace with Database in Production)
products: Dict[str, Dict] = {
    "1": {"id": "1", "name": "Product A", "price": 9.99},
    "2": {"id": "2", "name": "Product B", "price": 19.99},
}
cart: Dict[str, Dict] = {}

# Pydantic Models for Validation
class Product(BaseModel):
    id: str
    name: str
    price: float

class CartItem(BaseModel):
    product_id: str
    quantity: int = 1

class UserCredentials(BaseModel):
    username: str
    password: str

# Security: In-Memory User Store (Replace with Secure Storage)
users: Dict[str, str] = {
    "admin": hashlib.sha256("admin".encode()).hexdigest(),
    # Add more users as needed, ideally through a secure registration process
}

# Dependency for Authentication
async def get_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Validate Basic Auth Credentials"""
    if credentials.username not in users or users[credentials.username] != hashlib.sha256(credentials.password.encode()).hexdigest():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

# Endpoints

## Products
@app.get("/products", response_model=List[Product], dependencies=[Depends(get_credentials)])
async def read_products():
    """List all available products"""
    return list(products.values())

@app.get("/products/{product_id}", response_model=Product, dependencies=[Depends(get_credentials)])
async def read_product(product_id: str):
    """Retrieve details of a specific product by ID"""
    product = products.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

## Cart
@app.post("/cart", status_code=status.HTTP_201_CREATED, dependencies=[Depends(get_credentials)])
async def add_to_cart(item: CartItem):
    """Add an item to the cart"""
    if item.product_id not in products:
        raise HTTPException(status_code=400, detail="Invalid product ID")
    
    # Generate Unique Cart Item ID
    item_id = str(uuid4())
    cart[item_id] = {"product_id": item.product_id, "quantity": item.quantity}
    return {"id": item_id, **item.dict()}

@app.get("/cart", response_model=List[Dict], dependencies=[Depends(get_credentials)])
async def view_cart():
    """View the current state of the cart"""
    return list(cart.values())

@app.delete("/cart/{item_id}", dependencies=[Depends(get_credentials)])
async def remove_from_cart(item_id: str):
    """Remove an item from the cart by its ID"""
    if item_id not in cart:
        raise HTTPException(status_code=404, detail="Cart item not found")
    del cart[item_id]
    return {"message": "Item removed from cart"}

## Health Check (Public)
@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "ok"}

# Registration Endpoint for Demo (INSECURE - Do not use in Production)
@app.post("/register", response_model=UserCredentials)
async def register_user(user: UserCredentials):
    """Register a new user (INSECURE - For demo purposes only)"""
    if user.username in users:
        raise HTTPException(status_code=400, detail="Username already exists")
    users[user.username] = hashlib.sha256(user.password.encode()).hexdigest()
    return user

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)