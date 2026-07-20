"""
Simple e‑commerce REST API using FastAPI.

Endpoints
---------
GET /products
    List all available products.

GET /products/{product_id}
    Retrieve details of a single product.

POST /cart
    Add a product to the current user's cart.
    Body: {"product_id": int, "quantity": int}

GET /cart
    Retrieve the current user's cart contents.

DELETE /cart/{item_id}
    Remove a cart item by its identifier.

Security
--------
- API key authentication via the "X-API-Key" header.
- CORS middleware for controlled origins.
- Input validation with Pydantic models.
"""

from __future__ import annotations

import uuid
from typing import List, Dict

from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, PositiveInt, conint

# -------------------- Configuration --------------------
API_KEY = "super-secret-api-key"  # In production, load from env/secret manager
ALLOWED_ORIGINS = ["http://localhost", "http://127.0.0.1"]


def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    """
    Simple API‑key dependency. Raises 401 if the key does not match.
    """
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "API key"},
        )


# -------------------- Data Models --------------------
class Product(BaseModel):
    id: int
    name: str = Field(..., max_length=100)
    description: str = Field("", max_length=500)
    price_cents: PositiveInt  # store price in cents to avoid floating point issues
    in_stock: conint(ge=0)


class ProductCreate(Product):
    """Model for creating a product – currently unused but kept for extensibility."""


class CartItem(BaseModel):
    id: str  # UUID string
    product_id: int
    quantity: PositiveInt
    total_price_cents: PositiveInt


class AddToCartRequest(BaseModel):
    product_id: int
    quantity: PositiveInt = 1


# -------------------- In‑Memory Store --------------------
# In real applications replace with a persistent DB.
_products: Dict[int, Product] = {
    1: Product(id=1, name="T‑Shirt", description="Cotton t‑shirt", price_cents=1999, in_stock=50),
    2: Product(id=2, name="Coffee Mug", description="Ceramic mug", price_cents=1299, in_stock=120),
    3: Product(id=3, name="Notebook", description="Paper notebook", price_cents=799, in_stock=200),
}
_user_carts: Dict[str, Dict[str, CartItem]] = {}  # api_key -> {item_id: CartItem}


# -------------------- FastAPI App --------------------
app = FastAPI(
    title="Simple E‑Commerce API",
    version="1.0.0",
    description="Demo API for product catalog and shopping cart operations.",
    dependencies=[Depends(verify_api_key)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# -------------------- Helper Functions --------------------
def get_cart(api_key: str) -> Dict[str, CartItem]:
    """Retrieve or initialise a cart for the given API key."""
    return _user_carts.setdefault(api_key, {})


def calculate_total_price(product: Product, quantity: int) -> int:
    """Return total price in cents."""
    return product.price_cents * quantity


# -------------------- Endpoints --------------------
@app.get("/products", response_model=List[Product])
def list_products() -> List[Product]:
    """
    Return a list of all products.
    """
    return list(_products.values())


@app.get("/products/{product_id}", response_model=Product)
def get_product(product_id: int) -> Product:
    """
    Return details for a single product.
    """
    product = _products.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.post(
    "/cart",
    response_model=CartItem,
    status_code=status.HTTP_201_CREATED,
)
def add_to_cart(
    payload: AddToCartRequest,
    api_key: str = Depends(lambda x_api_key=Header(..., alias="X-API-Key"): x_api_key),
) -> CartItem:
    """
    Add a product to the authenticated user's cart.
    """
    product = _products.get(payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.in_stock < payload.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient stock. Available: {product.in_stock}",
        )

    cart = get_cart(api_key)

    # Create a new cart item
    item_id = str(uuid.uuid4())
    total_price = calculate_total_price(product, payload.quantity)
    cart_item = CartItem(
        id=item_id,
        product_id=product.id,
        quantity=payload.quantity,
        total_price_cents=total_price,
    )
    cart[item_id] = cart_item

    # Decrease product stock
    product.in_stock -= payload.quantity

    return cart_item


@app.get("/cart", response_model=List[CartItem])
def view_cart(
    api_key: str = Depends(lambda x_api_key=Header(..., alias="X-API-Key"): x_api_key),
) -> List[CartItem]:
    """
    Retrieve the current user's cart items.
    """
    cart = get_cart(api_key)
    return list(cart.values())


@app.delete("/cart/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_cart(
    item_id: str,
    api_key: str = Depends(lambda x_api_key=Header(..., alias="X-API-Key"): x_api_key),
) -> None:
    """
    Remove a cart item and restore product stock.
    """
    cart = get_cart(api_key)
    cart_item = cart.pop(item_id, None)
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    # Restore stock
    product = _products.get(cart_item.product_id)
    if product:
        product.in_stock += cart_item.quantity
    # No content returned


# -------------------- Run Server (optional) --------------------
# The block below enables running the app with `python this_file.py`.
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",  # Adjust if saved under a different filename
        host="0.0.0.0",
        port=8000,
        reload=True,
    )