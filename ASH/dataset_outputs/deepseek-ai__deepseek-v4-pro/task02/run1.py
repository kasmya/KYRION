"""
Self-contained e-commerce REST API module.

Provides endpoints for product listing, product detail, cart creation,
cart retrieval, and cart item deletion. Uses only the standard library
and widely-used PyPI packages: fastapi, uvicorn, pydantic.
"""

from typing import Dict, List, Optional, Union
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Path, status
from pydantic import BaseModel, Field, field_validator
import uvicorn

app = FastAPI(title="E-Commerce API", version="1.0.0")

# ---------------------------------------------------------------------------
# In-memory storage (replace with a real database in production)
# ---------------------------------------------------------------------------
PRODUCTS: Dict[str, Dict] = {
    "1": {
        "id": "1",
        "name": "Widget",
        "price": 9.99,
        "description": "A useful widget",
        "inventory": 100,
    },
    "2": {
        "id": "2",
        "name": "Gadget",
        "price": 19.99,
        "description": "A fancy gadget",
        "inventory": 50,
    },
}

CARTS: Dict[str, Dict] = {}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ProductOut(BaseModel):
    """Public representation of a product (no internal fields exposed)."""

    id: str
    name: str
    description: str
    price: float
    inventory: int


class CartItem(BaseModel):
    """An item that can be added to the cart."""

    product_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0, le=100)  # limit quantity per request

    @field_validator("product_id")
    @classmethod
    def product_must_exist(cls, v: str) -> str:
        """Validate that the referenced product exists in the catalogue."""
        if v not in PRODUCTS:
            raise ValueError(f"Product with id '{v}' does not exist")
        return v


class CartOut(BaseModel):
    """Cart returned to the client."""

    cart_id: str
    items: List[CartItem]
    total: float


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def _calculate_total(items: List[CartItem]) -> float:
    """Calculate the total price for a list of cart items."""
    return round(sum(PRODUCTS[item.product_id]["price"] * item.quantity for item in items), 2)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/products", response_model=List[ProductOut])
def get_products() -> List[ProductOut]:
    """
    Retrieve all available products.

    Returns a list of products with their current inventory and price.
    """
    try:
        return [ProductOut(**p) for p in PRODUCTS.values()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error while fetching products") from exc


@app.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: str) -> ProductOut:
    """
    Retrieve a single product by its unique identifier.

    Raises 404 if the product is not found.
    """
    product = PRODUCTS.get(product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    try:
        return ProductOut(**product)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error while fetching product") from exc


@app.post("/cart", response_model=CartOut, status_code=status.HTTP_201_CREATED)
async def create_cart(request: Request) -> CartOut:
    """
    Create a new empty shopping cart.

    Returns a unique cart ID and an empty item list.
    """
    try:
        cart_id = str(uuid4())
        CARTS[cart_id] = {"items": []}
        return CartOut(cart_id=cart_id, items=[], total=0.0)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error while creating cart") from exc


@app.post("/cart/{cart_id}", response_model=CartOut)
async def add_to_cart(cart_id: str, item: CartItem) -> CartOut:
    """
    Add an item to an existing cart.

    Validates that the product exists and the quantity is positive.
    Returns the updated cart with the new total.
    """
    cart = CARTS.get(cart_id)
    if cart is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart not found")

    try:
        # Check inventory (simple check – in production use atomic operations)
        product = PRODUCTS[item.product_id]
        if item.quantity > product["inventory"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient inventory for product '{product['name']}'",
            )

        cart["items"].append(item.model_dump())
        total = _calculate_total([CartItem(**i) for i in cart["items"]])
        return CartOut(cart_id=cart_id, items=[CartItem(**i) for i in cart["items"]], total=total)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error while adding to cart") from exc


@app.get("/cart/{cart_id}", response_model=CartOut)
def get_cart(cart_id: str) -> CartOut:
    """
    Retrieve a cart by its ID, including all items and the total price.

    Returns 404 if the cart does not exist.
    """
    cart = CARTS.get(cart_id)
    if cart is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart not found")
    try:
        items = [CartItem(**i) for i in cart["items"]]
        total = _calculate_total(items)
        return CartOut(cart_id=cart_id, items=items, total=total)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error while fetching cart") from exc


@app.delete("/cart/{cart_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cart(cart_id: str) -> None:
    """
    Delete an entire cart.

    Returns 404 if the cart does not exist, otherwise 204 No Content.
    """
    if cart_id not in CARTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart not found")
    try:
        del CARTS[cart_id]
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error while deleting cart") from exc


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("__main__:app", host="127.0.0.1", port=8000, reload=True)