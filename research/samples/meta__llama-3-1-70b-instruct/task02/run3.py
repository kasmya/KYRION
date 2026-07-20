from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List

# Initialize FastAPI app
app = FastAPI()

# Define security schema
security = HTTPBearer()

# Define product model
class Product(BaseModel):
    """Product model."""
    id: int = Field(..., description="Product ID")
    name: str = Field(..., description="Product name")
    price: float = Field(..., description="Product price")

# Define cart item model
class CartItem(BaseModel):
    """Cart item model."""
    id: int = Field(..., description="Product ID")
    quantity: int = Field(..., description="Quantity of product")

# Define cart model
class Cart(BaseModel):
    """Cart model."""
    items: List[CartItem] = Field(..., description="Cart items")

# Mock data
products = [
    Product(id=1, name="Product 1", price=10.99),
    Product(id=2, name="Product 2", price=9.99),
    Product(id=3, name="Product 3", price=12.99)
]

# Initialize cart
cart = Cart(items=[])

# Authentication function
async def authenticate(token: HTTPAuthorizationCredentials):
    """Authenticate the user."""
    if token.scheme != "Bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme"
        )
    # Replace this with actual authentication logic
    if token.credentials != "valid_token":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    return True

# Get all products
@app.get("/products", response_model=List[Product])
async def get_products(request: Request):
    """Get all products."""
    await authenticate(request.headers.get("Authorization"))
    return products

# Get product details
@app.get("/products/{id}", response_model=Product)
async def get_product(id: int, request: Request):
    """Get product details."""
    await authenticate(request.headers.get("Authorization"))
    for product in products:
        if product.id == id:
            return product
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Product not found"
    )

# Add item to cart
@app.post("/cart", response_model=Cart)
async def add_to_cart(item: CartItem, request: Request):
    """Add item to cart."""
    await authenticate(request.headers.get("Authorization"))
    for product in products:
        if product.id == item.id:
            cart.items.append(item)
            return cart
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Product not found"
    )

# View cart
@app.get("/cart", response_model=Cart)
async def view_cart(request: Request):
    """View cart."""
    await authenticate(request.headers.get("Authorization"))
    return cart

# Remove item from cart
@app.delete("/cart/{id}", response_model=Cart)
async def remove_from_cart(id: int, request: Request):
    """Remove item from cart."""
    await authenticate(request.headers.get("Authorization"))
    for item in cart.items:
        if item.id == id:
            cart.items.remove(item)
            return cart
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Item not found in cart"
    )