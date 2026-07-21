"""
ecommerce_api.py
A minimal e-commerce REST API implemented with FastAPI.

Endpoints:
- GET    /products           : List all available products.
- GET    /products/{id}     : Retrieve a product by its ID.
- POST   /cart               : Add a product to the shopping cart.
- GET    /cart               : Retrieve all items in the shopping cart.
- DELETE /cart/{id}         : Remove an item from the shopping cart.

Security:
- Simple API key authentication via the `X-API-Key` header.
- CORS middleware with a restrictive default configuration.

All functions are fully typed and include docstrings.
"""

from __future__ import annotations

import os
import uuid
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, PositiveInt, validator

# --------------------------------------------------------------------------- #
# Configuration and security
# --------------------------------------------------------------------------- #

API_KEY_NAME = "X-API-Key"
# In production, load this from a secure source (e.g., environment variable, vault)
API_KEY = os.getenv("API_KEY", "super-secret-key")

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def verify_api_key(
    request: Request, api_key: Optional[str] = Depends(api_key_header)
) -> None:
    """
    Dependency that validates the API key supplied in the request header.

    Raises:
        HTTPException: 401 Unauthorized if the key is missing or invalid.
    """
    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "API key"},
        )


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #

class Product(BaseModel):
    """Representation of a product in the catalogue."""
    id: str = Field(..., description="Unique identifier of the product")
    name: str = Field(..., min_length=1, description="Human‑readable product name")
    description: Optional[str] = Field(None, description="Detailed product description")
    price_cents: PositiveInt = Field(..., description="Price in cents (positive integer)")

    @validator("id")
    def validate_uuid(cls, v: str) -> str:
        """Ensures the product ID is a valid UUID string."""
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError("id must be a valid UUID") from exc
        return v


class CartItemCreate(BaseModel):
    """Payload for adding a product to the cart."""
    product_id: str = Field(..., description="ID of the product to add")
    quantity: PositiveInt = Field(..., description="Number of units to add (>=1)")

    @validator("product_id")
    def validate_product_uuid(cls, v: str) -> str:
        """Ensures the product ID is a valid UUID string."""
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError("product_id must be a valid UUID") from exc
        return v


class CartItem(BaseModel):
    """Representation of an item stored in the shopping cart."""
    id: str = Field(..., description="Unique identifier of the cart entry")
    product: Product = Field(..., description="Embedded product details")
    quantity: PositiveInt = Field(..., description="Quantity of the product in the cart")
    total_price_cents: PositiveInt = Field(..., description="Subtotal for this line item")


# --------------------------------------------------------------------------- #
# In‑memory data stores (for demonstration purposes only)
# --------------------------------------------------------------------------- #

# Pre‑populated product catalogue
_PRODUCTS: Dict[str, Product] = {
    str(uuid.uuid4()): Product(
        id=str(uuid.uuid4()),
        name="Wireless Mouse",
        description="Ergonomic wireless mouse with USB‑C receiver",
        price_cents=2599,
    ),
    str(uuid.uuid4()): Product(
        id=str(uuid.uuid4()),
        name="Mechanical Keyboard",
        description="RGB backlit mechanical keyboard with blue switches",
        price_cents=7499,
    ),
    str(uuid.uuid4()): Product(
        id=str(uuid.uuid4()),
        name="Noise‑Cancelling Headphones",
        description="Over‑ear headphones with active noise cancellation",
        price_cents=12999,
    ),
}
# Normalise keys to product.id
_PRODUCTS = {p.id: p for p in _PRODUCTS.values()}

# Shopping cart storage
_CART: Dict[str, CartItem] = {}


# --------------------------------------------------------------------------- #
# FastAPI application setup
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="Minimal E‑Commerce API",
    version="1.0.0",
    description="A simple, self‑contained e‑commerce API for demonstration purposes.",
    docs_url="/docs",
    redoc_url="/redoc",
)


# Restrictive CORS (adjust origins as needed for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://example.com"],  # Change to your allowed origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=[API_KEY_NAME],
)


# --------------------------------------------------------------------------- #
# Endpoint implementations
# --------------------------------------------------------------------------- #

@app.get("/products", response_model=List[Product], tags=["Products"])
def list_products(_: None = Depends(verify_api_key)) -> List[Product]:
    """
    Return the full list of available products.

    Returns:
        List[Product]: All products in the catalogue.
    """
    return list(_PRODUCTS.values())


@app.get(
    "/products/{product_id}",
    response_model=Product,
    tags=["Products"],
    responses={404: {"description": "Product not found"}},
)
def get_product(
    product_id: str,
    _: None = Depends(verify_api_key),
) -> Product:
    """
    Retrieve a single product by its unique identifier.

    Args:
        product_id: UUID string of the desired product.

    Returns:
        Product: The matching product.

    Raises:
        HTTPException: 404 if the product does not exist.
    """
    product = _PRODUCTS.get(product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id '{product_id}' not found",
        )
    return product


@app.post(
    "/cart",
    response_model=CartItem,
    status_code=status.HTTP_201_CREATED,
    tags=["Cart"],
    responses={400: {"description": "Invalid request"}, 404: {"description": "Product not found"}},
)
def add_to_cart(
    payload: CartItemCreate,
    _: None = Depends(verify_api_key),
) -> CartItem:
    """
    Add a product to the shopping cart.

    Args:
        payload: Details of the product and quantity to add.

    Returns:
        CartItem: The newly created cart entry.

    Raises:
        HTTPException: 404 if the referenced product does not exist.
    """
    product = _PRODUCTS.get(payload.product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id '{payload.product_id}' not found",
        )

    cart_item_id = str(uuid.uuid4())
    total_price = product.price_cents * payload.quantity

    cart_item = CartItem(
        id=cart_item_id,
        product=product,
        quantity=payload.quantity,
        total_price_cents=total_price,
    )
    _CART[cart_item_id] = cart_item
    return cart_item


@app.get(
    "/cart",
    response_model=List[CartItem],
    tags=["Cart"],
)
def list_cart(_: None = Depends(verify_api_key)) -> List[CartItem]:
    """
    Retrieve all items currently stored in the shopping cart.

    Returns:
        List[CartItem]: All cart entries.
    """
    return list(_CART.values())


@app.delete(
    "/cart/{cart_item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Cart"],
    responses={404: {"description": "Cart item not found"}},
)
def delete_cart_item(
    cart_item_id: str,
    _: None = Depends(verify_api_key),
) -> None:
    """
    Remove a specific item from the shopping cart.

    Args:
        cart_item_id: UUID string of the cart entry to delete.

    Raises:
        HTTPException: 404 if the cart entry does not exist.
    """
    if cart_item_id not in _CART:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cart item with id '{cart_item_id}' not found",
        )
    del _CART[cart_item_id]
    return None