"""
ecommerce_api.py
----------------
A minimal e-commerce REST API implemented with FastAPI.

Endpoints
~~~~~~~~~
* GET /products               – List all available products.
* GET /products/{product_id}  – Retrieve a single product.
* POST /cart                  – Add a product to the shopping cart.
* GET /cart                   – Retrieve current cart contents.
* DELETE /cart/{item_id}      – Remove an item from the cart.

The implementation uses in‑memory storage for demonstration purposes,
includes type hints, comprehensive docstrings, explicit error handling,
and basic security best practices (CORS, input validation, and a simple
API key authentication scheme).
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from fastapi import (
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.security.api_key import APIKeyHeader, APIKey
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, PositiveInt, validator

# --------------------------------------------------------------------------- #
# Configuration & Security
# --------------------------------------------------------------------------- #

API_KEY_NAME = "X-API-Key"
# In a real application this would be stored securely (e.g., env variable, vault)
API_KEY = "super-secret-key"

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_api_key(
    api_key: Optional[str] = Depends(api_key_header),
) -> APIKey:
    """
    Validate the supplied API key.

    Raises
    ------
    HTTPException
        If the API key is missing or invalid.
    """
    if api_key == API_KEY:
        return api_key
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Could not validate credentials",
    )


# --------------------------------------------------------------------------- #
# Data Models
# --------------------------------------------------------------------------- #

class Product(BaseModel):
    """Represent a product available for purchase."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique product identifier")
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    price_cents: PositiveInt = Field(..., description="Price in cents to avoid floating point issues")
    in_stock: PositiveInt = Field(..., description="Number of items available")

    @validator("price_cents", "in_stock")
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("must be non‑negative")
        return v


class CartItem(BaseModel):
    """Represent an item stored in a shopping cart."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique cart‑item identifier")
    product_id: uuid.UUID = Field(..., description="Identifier of the product")
    quantity: PositiveInt = Field(..., description="Quantity of the product in the cart")

    @validator("quantity")
    def quantity_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("quantity must be greater than zero")
        return v


class AddToCartRequest(BaseModel):
    """Payload for adding a product to the cart."""
    product_id: uuid.UUID = Field(..., description="Identifier of the product to add")
    quantity: PositiveInt = Field(..., description="Quantity to add")


# --------------------------------------------------------------------------- #
# In‑Memory Data Stores (for demonstration only)
# --------------------------------------------------------------------------- #

_PRODUCTS: Dict[uuid.UUID, Product] = {}
_CART: Dict[uuid.UUID, CartItem] = {}


def _initialize_demo_data() -> None:
    """Populate the product catalog with a few sample items."""
    sample_products = [
        Product(name="Wireless Mouse", description="Ergonomic mouse", price_cents=2599, in_stock=150),
        Product(name="Mechanical Keyboard", description="RGB backlit", price_cents=7499, in_stock=85),
        Product(name="USB‑C Hub", description="7‑port hub", price_cents=3299, in_stock=200),
    ]
    for prod in sample_products:
        _PRODUCTS[prod.id] = prod


_initialize_demo_data()


# --------------------------------------------------------------------------- #
# FastAPI Application
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="Simple E‑Commerce API",
    description="A minimal example of an e‑commerce backend using FastAPI.",
    version="1.0.0",
)

# Allow only safe origins; adjust as needed for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://example.com"],  # Replace with your front‑end domain(s)
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=[API_KEY_NAME, "Content-Type"],
)


# --------------------------------------------------------------------------- #
# Endpoint Implementations
# --------------------------------------------------------------------------- #

@app.get(
    "/products",
    response_model=List[Product],
    summary="List all products",
    tags=["products"],
)
def list_products(_: APIKey = Depends(get_api_key)) -> List[Product]:
    """
    Return a list of all products in the catalog.

    Parameters
    ----------
    _: APIKey
        Dependency that ensures a valid API key is provided.

    Returns
    -------
    List[Product]
        All available products.
    """
    return list(_PRODUCTS.values())


@app.get(
    "/products/{product_id}",
    response_model=Product,
    summary="Retrieve a product",
    tags=["products"],
)
def get_product(
    product_id: uuid.UUID,
    _: APIKey = Depends(get_api_key),
) -> Product:
    """
    Retrieve a single product by its identifier.

    Parameters
    ----------
    product_id : uuid.UUID
        Identifier of the product to fetch.
    _: APIKey
        Dependency that ensures a valid API key is provided.

    Returns
    -------
    Product
        The requested product.

    Raises
    ------
    HTTPException
        If the product does not exist (404).
    """
    product = _PRODUCTS.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.post(
    "/cart",
    response_model=CartItem,
    status_code=status.HTTP_201_CREATED,
    summary="Add product to cart",
    tags=["cart"],
)
def add_to_cart(
    payload: AddToCartRequest = Body(..., description="Product and quantity to add"),
    _: APIKey = Depends(get_api_key),
) -> CartItem:
    """
    Add a product to the shopping cart.

    The endpoint validates product existence, stock availability, and
    quantity constraints before creating a new cart item.

    Parameters
    ----------
    payload : AddToCartRequest
        The product ID and quantity to add.
    _: APIKey
        Dependency that ensures a valid API key is provided.

    Returns
    -------
    CartItem
        The newly created cart item.

    Raises
    ------
    HTTPException
        * 404 – Product not found.
        * 400 – Insufficient stock.
    """
    product = _PRODUCTS.get(payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if payload.quantity > product.in_stock:
        raise HTTPException(
            status_code=400,
            detail=f"Requested quantity ({payload.quantity}) exceeds stock ({product.in_stock})",
        )

    # Decrement stock atomically (simplified for in‑memory store)
    product.in_stock -= payload.quantity

    cart_item = CartItem(product_id=payload.product_id, quantity=payload.quantity)
    _CART[cart_item.id] = cart_item
    return cart_item


@app.get(
    "/cart",
    response_model=List[CartItem],
    summary="View cart contents",
    tags=["cart"],
)
def view_cart(_: APIKey = Depends(get_api_key)) -> List[CartItem]:
    """
    Retrieve all items currently stored in the shopping cart.

    Parameters
    ----------
    _: APIKey
        Dependency that ensures a valid API key is provided.

    Returns
    -------
    List[CartItem]
        List of cart items.
    """
    return list(_CART.values())


@app.delete(
    "/cart/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove item from cart",
    tags=["cart"],
)
def delete_cart_item(
    item_id: uuid.UUID,
    _: APIKey = Depends(get_api_key),
) -> Response:
    """
    Delete a specific cart item, restoring the product stock.

    Parameters
    ----------
    item_id : uuid.UUID
        Identifier of the cart item to delete.
    _: APIKey
        Dependency that ensures a valid API key is provided.

    Returns
    -------
    Response
        Empty response with HTTP 204 status.

    Raises
    ------
    HTTPException
        If the cart item does not exist (404).
    """
    cart_item = _CART.pop(item_id, None)
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    # Restore stock
    product = _PRODUCTS.get(cart_item.product_id)
    if product:
        product.in_stock += cart_item.quantity

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Application Entry Point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "ecommerce_api:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
        reload=False,
    )