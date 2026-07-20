"""
E‑commerce REST API implemented with FastAPI.

Endpoints
---------
GET /products
GET /products/{product_id}
POST /cart          (requires JSON body with product_id and quantity)
GET /cart
DELETE /cart/{item_id}
"""

import os
import uuid
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, PositiveInt, conint, validator

# --------------------------------------------------------------------------- #
# Configuration & Security
# --------------------------------------------------------------------------- #

API_KEY_NAME = "X-API-Key"
API_KEY = os.getenv("API_KEY", "dev-secret-key")  # In production use a secure secret


def verify_api_key(x_api_key: str = Header(..., description="API key for authentication")):
    """Simple API‑key based dependency."""
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return True


# --------------------------------------------------------------------------- #
# Data Models
# --------------------------------------------------------------------------- #

class Product(BaseModel):
    """Product representation."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique product identifier")
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    price_cents: PositiveInt = Field(..., description="Price in cents to avoid floating point issues")
    in_stock: conint(ge=0) = Field(..., description="Available quantity")


class CartItem(BaseModel):
    """Item stored inside a user's cart."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique cart‑item identifier")
    product_id: str = Field(..., description="ID of the product")
    quantity: conint(gt=0) = Field(..., description="Quantity requested")
    unit_price_cents: PositiveInt = Field(..., description="Snapshot of product price at add time")

    @validator("quantity")
    def quantity_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Quantity must be greater than zero")
        return v


class AddToCartRequest(BaseModel):
    """Payload for adding an item to the cart."""
    product_id: str = Field(..., description="ID of the product to add")
    quantity: conint(gt=0) = Field(..., description="Desired quantity")


class CartResponse(BaseModel):
    """Cart view returned to the client."""
    items: List[CartItem]
    total_cents: int = Field(..., description="Total price in cents")


# --------------------------------------------------------------------------- #
# In‑memory storage (replace with a database in production)
# --------------------------------------------------------------------------- #

PRODUCTS: Dict[str, Product] = {}
CART: Dict[str, CartItem] = {}

# Pre‑populate some products for demo purposes
def _seed_products() -> None:
    sample = [
        Product(name="Wireless Mouse", description="Ergonomic wireless mouse", price_cents=2599, in_stock=150),
        Product(name="Mechanical Keyboard", description="RGB backlit mechanical keyboard", price_cents=7499, in_stock=80),
        Product(name="USB‑C Hub", description="5‑port USB‑C hub", price_cents=1999, in_stock=200),
    ]
    for p in sample:
        PRODUCTS[p.id] = p

_seed_products()


# --------------------------------------------------------------------------- #
# FastAPI app definition
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="Simple E‑Commerce API",
    version="1.0.0",
    description="A minimal e‑commerce API with product catalog and shopping cart.",
    docs_url="/docs",
    redoc_url="/redoc",
)


# --------------------------------------------------------------------------- #
# Middleware: simple request logging (avoid leaking sensitive data)
# --------------------------------------------------------------------------- #

@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    # Basic request logging; could be extended with structured logging libraries.
    request_path = request.url.path
    method = request.method
    status_code = response.status_code
    print(f"{method} {request_path} -> {status_code}")
    return response


# --------------------------------------------------------------------------- #
# Exception Handlers
# --------------------------------------------------------------------------- #

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Uniform JSON error response
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@app.get("/products", response_model=List[Product], tags=["Products"])
def list_products(_: bool = Depends(verify_api_key)):
    """Return a list of all available products."""
    return list(PRODUCTS.values())


@app.get("/products/{product_id}", response_model=Product, tags=["Products"])
def get_product(product_id: str, _: bool = Depends(verify_api_key)):
    """Return details of a single product."""
    product = PRODUCTS.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.post("/cart", response_model=CartItem, status_code=201, tags=["Cart"])
def add_to_cart(payload: AddToCartRequest, _: bool = Depends(verify_api_key)):
    """Add a product to the shopping cart."""
    product = PRODUCTS.get(payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if payload.quantity > product.in_stock:
        raise HTTPException(
            status_code=400,
            detail=f"Requested quantity ({payload.quantity}) exceeds stock ({product.in_stock})",
        )

    # Decrease stock atomically (simplified for in‑memory store)
    product.in_stock -= payload.quantity

    # Create cart item
    cart_item = CartItem(
        product_id=product.id,
        quantity=payload.quantity,
        unit_price_cents=product.price_cents,
    )
    CART[cart_item.id] = cart_item
    return cart_item


@app.get("/cart", response_model=CartResponse, tags=["Cart"])
def view_cart(_: bool = Depends(verify_api_key)):
    """Retrieve the current cart contents."""
    items = list(CART.values())
    total_cents = sum(item.unit_price_cents * item.quantity for item in items)
    return CartResponse(items=items, total_cents=total_cents)


@app.delete("/cart/{item_id}", status_code=204, tags=["Cart"])
def remove_cart_item(item_id: str, _: bool = Depends(verify_api_key)):
    """Remove a specific item from the cart."""
    cart_item = CART.pop(item_id, None)
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    # Return stock to inventory
    product = PRODUCTS.get(cart_item.product_id)
    if product:
        product.in_stock += cart_item.quantity
    # 204 No Content response
    return


# --------------------------------------------------------------------------- #
# Run with: uvicorn this_file_name:app --reload
# --------------------------------------------------------------------------- #