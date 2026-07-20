from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import List, Optional
import uuid
from hashlib import sha256

# Security Setup
security = HTTPBasic()

app = FastAPI(docs_url=None)

# In-Memory Data Stores (Replace with Database in Production)
products = {
    "1": {"id": "1", "name": "Product A", "price": 9.99},
    "2": {"id": "2", "name": "Product B", "price": 19.99},
}
cart = {}

# Pydantic Models
class Product(BaseModel):
    id: str
    name: str
    price: float

class CartItem(BaseModel):
    product_id: str
    quantity: int = 1

class Cart(BaseModel):
    items: List[CartItem]

# Authentication
async def get_credentials(credentials: Optional[HTTPBasicCredentials] = Depends(security)):
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    # Simple Auth for Demo (Use Secure Storage and Comparison in Production)
    if credentials.username != "admin" or sha256(credentials.password.encode()).hexdigest() != "e10adc3949ba59abbe56e057f20f883e":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials

# Endpoints
@app.get("/products", response_model=List[Product])
async def read_products():
    """List all available products."""
    return list(products.values())

@app.get("/products/{product_id}", response_model=Product)
async def read_product(product_id: str):
    """Retrieve details of a specific product by ID."""
    if product_id not in products:
        raise HTTPException(status_code=404, detail="Product not found")
    return products[product_id]

@app.post("/cart", status_code=201, response_model=CartItem)
async def add_to_cart(item: CartItem, credentials: HTTPBasicCredentials = Depends(security)):
    """Add an item to the user's cart."""
    # Simulate User Cart (In Production, use User ID from Auth)
    user_cart = cart.setdefault(credentials.username, [])
    
    # Check for existing item and update quantity
    for i, existing_item in enumerate(user_cart):
        if existing_item.product_id == item.product_id:
            user_cart[i].quantity += item.quantity
            return user_cart[i]
    
    # Add new item
    user_cart.append(item)
    return item

@app.get("/cart", response_model=Cart)
async def view_cart(credentials: HTTPBasicCredentials = Depends(security)):
    """View the current state of the user's cart."""
    if credentials.username not in cart:
        raise HTTPException(status_code=404, detail="Cart is empty")
    return {"items": cart[credentials.username]}

@app.delete("/cart/{item_id}", status_code=204)
async def remove_from_cart(item_id: str, credentials: HTTPBasicCredentials = Depends(security)):
    """Remove a specific item from the cart by its ID in the cart."""
    if credentials.username not in cart:
        raise HTTPException(status_code=404, detail="Cart is empty")
    
    # Simplified Removal by Index (Assuming item_id is the index for demo)
    try:
        del cart[credentials.username][int(item_id)]
    except (IndexError, ValueError):
        raise HTTPException(status_code=404, detail="Item not found in cart")

# Error Handling
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return {"detail": exc.detail}

# Startup Message
@app.on_event("startup")
async def startup_event():
    print("Server Started. Authenticate with username: 'admin', password: 'admin' (Note: Insecure for demo purposes only!)")