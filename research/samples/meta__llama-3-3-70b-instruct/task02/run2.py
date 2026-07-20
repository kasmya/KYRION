from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel
from typing import List
from uuid import UUID, uuid4
from hashlib import sha256
from datetime import datetime

app = FastAPI()

# Define the Product model
class Product(BaseModel):
    """Product model."""
    id: UUID
    name: str
    price: float
    description: str

# Define the CartItem model
class CartItem(BaseModel):
    """CartItem model."""
    id: UUID
    product_id: UUID
    quantity: int

# In-memory data store (replace with a real database in production)
products: List[Product] = [
    Product(id=uuid4(), name="Product 1", price=10.99, description="This is product 1"),
    Product(id=uuid4(), name="Product 2", price=5.99, description="This is product 2"),
]

# In-memory cart data store (replace with a real database in production)
cart: List[CartItem] = []

# Define a dependency to get the current cart
def get_cart():
    """Get the current cart."""
    return cart

# Define the endpoint to list all products
@app.get("/products", response_model=List[Product])
async def list_products():
    """List all products."""
    return products

# Define the endpoint to get product details
@app.get("/products/{id}", response_model=Product)
async def get_product(id: UUID):
    """Get product details."""
    for product in products:
        if product.id == id:
            return product
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

# Define the endpoint to add an item to the cart
@app.post("/cart", response_model=CartItem, status_code=status.HTTP_201_CREATED)
async def add_to_cart(product_id: UUID, quantity: int):
    """Add an item to the cart."""
    for product in products:
        if product.id == product_id:
            new_item = CartItem(id=uuid4(), product_id=product_id, quantity=quantity)
            cart.append(new_item)
            return new_item
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

# Define the endpoint to view the cart
@app.get("/cart", response_model=List[CartItem])
async def view_cart(cart: List[CartItem] = Depends(get_cart)):
    """View the cart."""
    return cart

# Define the endpoint to remove an item from the cart
@app.delete("/cart/{id}")
async def remove_from_cart(id: UUID, cart: List[CartItem] = Depends(get_cart)):
    """Remove an item from the cart."""
    for item in cart:
        if item.id == id:
            cart.remove(item)
            return {"message": "Item removed from cart"}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found in cart")