from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

# Define a product model
class Product(BaseModel):
    id: int
    name: str
    price: float

# Define a cart item model
class CartItem(BaseModel):
    product_id: int
    quantity: int

# Define a cart model
class Cart(BaseModel):
    items: List[CartItem]

# In-memory data storage
products = [
    Product(id=1, name="Product 1", price=10.99),
    Product(id=2, name="Product 2", price=5.99),
    Product(id=3, name="Product 3", price=7.99),
]

cart = Cart(items=[])

# GET /products
@app.get("/products", response_model=List[Product])
async def get_products():
    """Return a list of all products"""
    return products

# GET /products/{id}
@app.get("/products/{id}", response_model=Product)
async def get_product(id: int):
    """Return product details by ID"""
    product = next((p for p in products if p.id == id), None)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

# POST /cart
@app.post("/cart", response_model=Cart)
async def add_to_cart(item: CartItem):
    """Add an item to the cart"""
    # Check if product exists
    product = next((p for p in products if p.id == item.product_id), None)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    # Add item to cart
    existing_item = next((i for i in cart.items if i.product_id == item.product_id), None)
    if existing_item is None:
        cart.items.append(item)
    else:
        existing_item.quantity += item.quantity

    return cart

# GET /cart
@app.get("/cart", response_model=Cart)
async def view_cart():
    """Return the current cart"""
    return cart

# DELETE /cart/{id}
@app.delete("/cart/{id}")
async def remove_from_cart(id: int):
    """Remove an item from the cart by product ID"""
    cart.items = [i for i in cart.items if i.product_id != id]
    return {"message": "Item removed from cart"}