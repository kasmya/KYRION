from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from uuid import uuid4

app = FastAPI()

class Product(BaseModel):
    """Product model"""
    id: str
    name: str
    price: float

class CartItem(BaseModel):
    """Cart item model"""
    product_id: str
    quantity: int

class Cart(BaseModel):
    """Cart model"""
    items: List[CartItem]

# In-memory data store for products and cart
products = [
    {"id": "1", "name": "Product 1", "price": 10.99},
    {"id": "2", "name": "Product 2", "price": 5.99},
    {"id": "3", "name": "Product 3", "price": 7.99}
]

cart = {}

# Endpoint to list all products
@app.get("/products", response_model=List[Product])
def get_products():
    """List all products"""
    return products

# Endpoint to get product details
@app.get("/products/{product_id}", response_model=Product)
def get_product(product_id: str):
    """Get product details"""
    for product in products:
        if product["id"] == product_id:
            return product
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

# Endpoint to add item to cart
@app.post("/cart", status_code=status.HTTP_201_CREATED)
def add_to_cart(item: CartItem):
    """Add item to cart"""
    if item.product_id not in [product["id"] for product in products]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid product ID")
    
    if cart.get("items") is None:
        cart["items"] = []
    
    existing_item = next((i for i in cart["items"] if i["product_id"] == item.product_id), None)
    if existing_item:
        existing_item["quantity"] += item.quantity
    else:
        cart["items"].append({"product_id": item.product_id, "quantity": item.quantity})
    
    return {"message": "Item added to cart"}

# Endpoint to view cart
@app.get("/cart", response_model=Cart)
def view_cart():
    """View cart"""
    if not cart:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart is empty")
    return cart

# Endpoint to remove item from cart
@app.delete("/cart/{item_id}", status_code=status.HTTP_200_OK)
def remove_from_cart(item_id: str):
    """Remove item from cart"""
    if cart.get("items") is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart is empty")
    
    item_to_remove = next((i for i in cart["items"] if i["product_id"] == item_id), None)
    if item_to_remove:
        cart["items"].remove(item_to_remove)
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found in cart")
    
    return {"message": "Item removed from cart"}