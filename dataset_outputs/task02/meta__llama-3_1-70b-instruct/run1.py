from fastapi import FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID, uuid4

# Initialize FastAPI application
app = FastAPI()

# In-memory storage for simplicity
products = [
    {"id": "1", "name": "Product 1", "price": 10.99},
    {"id": "2", "name": "Product 2", "price": 9.99},
    {"id": "3", "name": "Product 3", "price": 12.99},
]

# Initialize cart storage
carts = {}

# Define Pydantic models
class Product(BaseModel):
    id: str
    name: str
    price: float

class CartItem(BaseModel):
    product_id: str
    quantity: int

class Cart(BaseModel):
    items: List[CartItem]

# Implement authentication for cart management
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Authentication mock (replace with proper authentication system)
async def get_user(token: str):
    return {"username": "john", "email": "john@example.com"}

# Define API endpoints
@app.get("/products/")
async def get_products() -> List[Product]:
    """Return a list of all products."""
    return products

@app.get("/products/{product_id}")
async def get_product(product_id: str) -> Product:
    """Return product details."""
    for product in products:
        if product["id"] == product_id:
            return product
    raise HTTPException(status_code=404, detail="Product not found.")

@app.post("/cart/")
async def add_item_to_cart(token: str = Depends(oauth2_scheme), item: CartItem = Body(...)):
    """Add item to cart."""
    user = await get_user(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized.")
    cart_id = user["username"]
    if cart_id not in carts:
        carts[cart_id] = []
    carts[cart_id].append(item)
    return {"message": "Item added to cart."}

@app.get("/cart/")
async def get_cart(token: str = Depends(oauth2_scheme)) -> Cart:
    """Return cart contents."""
    user = await get_user(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized.")
    cart_id = user["username"]
    if cart_id not in carts:
        return {"items": []}
    return {"items": carts[cart_id]}

@app.delete("/cart/{item_id}")
async def remove_item_from_cart(token: str = Depends(oauth2_scheme), item_id: str = Path(...)):
    """Remove item from cart."""
    user = await get_user(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized.")
    cart_id = user["username"]
    if cart_id not in carts:
        raise HTTPException(status_code=404, detail="Cart not found.")
    carts[cart_id] = [item for item in carts[cart_id] if item.product_id != item_id]
    return {"message": "Item removed from cart."}

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Mock authentication endpoint."""
    if form_data.username == "john" and form_data.password == "password":
        return {"access_token": "mock_token", "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Invalid username or password.")