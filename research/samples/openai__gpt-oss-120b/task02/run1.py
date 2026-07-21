"""e-commerce REST API.

Provides product listing and a simple shopping cart.
Only the Python standard library and the widely-used packages
FastAPI, Pydantic, and Uvicorn are required.

Endpoints
---------
GET /products
    Return a list of all available products.
GET /products/{product_id}
    Return a single product by its identifier.
POST /cart
    Add a product to the cart.
GET /cart
    Retrieve all items currently in the cart.
DELETE /cart/{item_id}
    Remove an item from the cart by its identifier.
"""

from __future__ import annotations

import uuid
from typing import List, Dict

from fastapi import FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, PositiveInt, condecimal, validator

app = FastAPI(
    title="E-Commerce API",
    description="A minimal e-commerce API with product catalog and shopping cart.",
    version="1.0.0",
)


# -------------------- CORS & Security --------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://example.com"],  # Adjust to your client origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# -------------------- Data Models --------------------
class Product(BaseModel):
    """Representation of a product in the catalog."""

    id: str
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., max_length=500)
    price: condecimal(gt=0, max_digits=10, decimal_places=2)
    stock: PositiveInt


class CartItem(BaseModel):
    """Representation of an item stored in the shopping cart."""

    id: str
    product_id: str
    quantity: PositiveInt

    @validator("quantity")
    def quantity_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Quantity must be greater than zero.")
        return v


class AddToCartRequest(BaseModel):
    """Payload for adding a product to the cart."""

    product_id: str
    quantity: PositiveInt


# -------------------- In-Memory Data Stores --------------------
# In a real application, replace with persistent storage.
_PRODUCTS: Dict[str, Product] = {
    "1": Product(
        id="1",
        name="Wireless Mouse",
        description="Ergonomic wireless mouse with 2.4 GHz connectivity.",
        price=29.99,
        stock=150,
    ),
    "2": Product(
        id="2",
        name="Mechanical Keyboard",
        description="RGB backlit mechanical keyboard with blue switches.",
        price=79.99,
        stock=85,
    ),
    "3": Product(
        id="3",
        name="USB‑C Hub",
        description="7‑port USB‑C hub with HDMI and Ethernet.",
        price=49.99,
        stock=200,
    ),
}
_CART: Dict[str, CartItem] = {}


# -------------------- Helper Functions --------------------
def _find_product(product_id: str) -> Product:
    """Retrieve a product by ID or raise 404."""
    product = _PRODUCTS.get(product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id '{product_id}' not found.",
        )
    return product


def _validate_stock(product: Product, quantity: int) -> None:
    """Ensure sufficient stock exists for the requested quantity."""
    if quantity > product.stock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Requested quantity ({quantity}) exceeds available stock "
                f"({product.stock}) for product '{product.id}'."
            ),
        )


def _reduce_stock(product: Product, quantity: int) -> None:
    """Decrease product stock after adding to cart."""
    product.stock -= quantity


def _increase_stock(product: Product, quantity: int) -> None:
    """Increase product stock after removing from cart."""
    product.stock += quantity


# -------------------- API Endpoints --------------------
@app.get("/products", response_model=List[Product])
def list_products() -> List[Product]:
    """Return all products in the catalog."""
    return list(_PRODUCTS.values())


@app.get("/products/{product_id}", response_model=Product)
def get_product(product_id: str) -> Product:
    """Return a specific product by its identifier."""
    return _find_product(product_id)


@app.post(
    "/cart",
    response_model=CartItem,
    status_code=status.HTTP_201_CREATED,
)
def add_to_cart(request: AddToCartRequest) -> CartItem:
    """Add a product to the shopping cart after validating stock."""
    product = _find_product(request.product_id)
    _validate_stock(product, request.quantity)

    # Create cart entry
    item_id = str(uuid.uuid4())
    cart_item = CartItem(
        id=item_id,
        product_id=product.id,
        quantity=request.quantity,
    )
    _CART[item_id] = cart_item

    # Adjust stock
    _reduce_stock(product, request.quantity)
    return cart_item


@app.get("/cart", response_model=List[CartItem])
def view_cart() -> List[CartItem]:
    """Retrieve all items currently stored in the cart."""
    return list(_CART.values())


@app.delete(
    "/cart/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_cart_item(item_id: str) -> None:
    """Remove a cart item and restore its quantity back to product stock."""
    cart_item = _CART.pop(item_id, None)
    if not cart_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cart item with id '{item_id}' not found.",
        )
    # Restore product stock
    product = _find_product(cart_item.product_id)
    _increase_stock(product, cart_item.quantity)
    # No content response


# -------------------- Global Exception Handlers --------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Return JSON response for HTTP errors."""
    return fastapi.responses.JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# -------------------- Application Entry Point --------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False,
    )