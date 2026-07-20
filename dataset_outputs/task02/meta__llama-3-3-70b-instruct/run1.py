from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional

# Initialize the FastAPI application
app = FastAPI()

# Define the security scheme
security = HTTPBearer()

# Define the product model
class Product(BaseModel):
    """Product model"""
    id: int
    name: str
    price: float

# Define the cart item model
class CartItem(BaseModel):
    """Cart item model"""
    product_id: int
    quantity: int

# Define the cart model
class Cart(BaseModel):
    """Cart model"""
    items: List[CartItem]

# In-memory data store for products
products = [
    {"id": 1, "name": "Product 1", "price": 10.99},
    {"id": 2, "name": "Product 2", "price": 9.99},
    {"id": 3, "name": "Product 3", "price": 12.99},
]

# In-memory data store for cart
cart = {}

# Endpoint to list all products
@app.get("/products", response_model=List[Product], status_code=status.HTTP_200_OK)
async def get_products():
    """List all products"""
    return products

# Endpoint to get product details
@app.get("/products/{id}", response_model=Product, status_code=status.HTTP_200_OK)
async def get_product(id: int):
    """Get product details"""
    for product in products:
        if product["id"] == id:
            return product
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

# Endpoint to add item to cart
@app.post("/cart", status_code=status.HTTP_201_CREATED)
async def add_item_to_cart(item: CartItem, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Add item to cart"""
    if credentials.token != "secret_token":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    if item.product_id not in [product["id"] for product in products]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    
    if item.quantity <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantity must be greater than 0")
    
    if credentials.username not in cart:
        cart[credentials.username] = []
    
    existing_item = next((i for i, x in enumerate(cart[credentials.username]) if x.product_id == item.product_id), None)
    if existing_item is not None:
        cart[credentials.username][existing_item].quantity += item.quantity
    else:
        cart[credentials.username].append(item)
    
    return JSONResponse(content={"message": "Item added to cart"}, status_code=status.HTTP_201_CREATED)

# Endpoint to view cart
@app.get("/cart", response_model=Cart, status_code=status.HTTP_200_OK)
async def view_cart(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """View cart"""
    if credentials.token != "secret_token":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    if credentials.username not in cart:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart not found")
    
    return cart[credentials.username]

# Endpoint to remove item from cart
@app.delete("/cart/{id}", status_code=status.HTTP_200_OK)
async def remove_item_from_cart(id: int, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Remove item from cart"""
    if credentials.token != "secret_token":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    if credentials.username not in cart:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart not found")
    
    existing_item = next((i for i, x in enumerate(cart[credentials.username]) if x.product_id == id), None)
    if existing_item is not None:
        del cart[credentials.username][existing_item]
        return JSONResponse(content={"message": "Item removed from cart"}, status_code=status.HTTP_200_OK)
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found in cart")