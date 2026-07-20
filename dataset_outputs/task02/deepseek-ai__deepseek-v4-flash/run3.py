from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import uuid4, UUID

# ------------------------------------------------------------------
# Application setup
app = FastAPI(
    title="E-Commerce REST API",
    description="Simple e-commerce API with products and cart management",
    version="1.0.0"
)

# ------------------------------------------------------------------
# In-memory data stores (for demonstration only)
# Product catalog (mocked)
products_db = [
    {"id": 1, "name": "Laptop", "price": 999.99, "stock": 10},
    {"id": 2, "name": "Smartphone", "price": 499.99, "stock": 25},
    {"id": 3, "name": "Headphones", "price": 79.99, "stock": 50},
    {"id": 4, "name": "Keyboard", "price": 49.99, "stock": 100},
]

# In-memory cart using a dictionary keyed by cart item id (UUID)
cart_db: dict[UUID, dict] = {}

# ------------------------------------------------------------------
# Pydantic models (type hints and validation)

class Product(BaseModel):
    """Product response model."""
    id: int
    name: str
    price: float = Field(gt=0, description="Price must be positive")
    stock: int = Field(ge=0, description="Stock cannot be negative")

class CartItemCreate(BaseModel):
    """Request body for adding an item to the cart."""
    product_id: int = Field(gt=0, description="Product ID must be positive")
    quantity: int = Field(gt=0, description="Quantity must be at least 1")

class CartItem(BaseModel):
    """Cart item response model."""
    id: UUID
    product_id: int
    product_name: str
    price: float
    quantity: int
    total: float

# ------------------------------------------------------------------
# Helper functions

def find_product(product_id: int) -> Optional[dict]:
    """Return product dict if found, else None."""
    for prod in products_db:
        if prod["id"] == product_id:
            return prod
    return None

def compute_cart_item_total(price: float, quantity: int) -> float:
    """Compute total price for a cart item."""
    return round(price * quantity, 2)

# ------------------------------------------------------------------
# Endpoints

@app.get("/products", response_model=List[Product], tags=["Products"])
def get_products():
    """
    Retrieve all available products.

    Returns:
        List[Product]: List of all products in the catalog.
    """
    return [Product(**prod) for prod in products_db]  # Validate and convert to model

@app.get("/products/{product_id}", response_model=Product, tags=["Products"])
def get_product(product_id: int):
    """
    Retrieve details of a single product by ID.

    Args:
        product_id: The ID of the product to fetch.

    Returns:
        Product: Product details.

    Raises:
        404: If product with given ID does not exist.
    """
    product = find_product(product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} not found"
        )
    return Product(**product)

@app.post("/cart", response_model=CartItem, status_code=status.HTTP_201_CREATED, tags=["Cart"])
def add_to_cart(item: CartItemCreate):
    """
    Add an item to the shopping cart.

    Args:
        item: The product ID and quantity to add.

    Returns:
        CartItem: The newly created cart item with calculated total.

    Raises:
        404: If the product_id does not exist.
        400: If requested quantity exceeds available stock.
    """
    product = find_product(item.product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {item.product_id} not found"
        )

    if item.quantity > product["stock"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock. Available: {product['stock']}, requested: {item.quantity}"
        )

    # Create cart item with unique ID
    cart_id = uuid4()
    total = compute_cart_item_total(product["price"], item.quantity)
    cart_item = {
        "id": cart_id,
        "product_id": item.product_id,
        "product_name": product["name"],
        "price": product["price"],
        "quantity": item.quantity,
        "total": total
    }
    cart_db[cart_id] = cart_item
    return CartItem(**cart_item)

@app.get("/cart", response_model=List[CartItem], tags=["Cart"])
def get_cart():
    """
    Retrieve all items currently in the cart.

    Returns:
        List[CartItem]: List of cart items.
    """
    return [CartItem(**item) for item in cart_db.values()]

@app.delete("/cart/{item_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Cart"])
def remove_from_cart(item_id: UUID):
    """
    Remove an item from the cart by its unique ID.

    Args:
        item_id: UUID of the cart item to remove.

    Raises:
        404: If cart item with given ID does not exist.
    """
    if item_id not in cart_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cart item with ID {item_id} not found"
        )
    del cart_db[item_id]
    return  # 204 No Content