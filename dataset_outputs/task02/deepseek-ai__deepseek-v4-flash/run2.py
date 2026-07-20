from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="E-Commerce API",
    description="A simple RESTful e-commerce API with product listing, cart management.",
    version="1.0.0"
)

# CORS configuration (allow frontend from a specific origin)
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage (replace with database in production)
PRODUCTS: Dict[str, dict] = {}
CARTS: Dict[str, dict] = {}  # key: cart_id, value: dict of cart items

# Sample product data (seeded on startup)
SEED_PRODUCTS = [
    {"id": "1", "name": "Wireless Mouse", "price": 29.99, "stock": 100},
    {"id": "2", "name": "Mechanical Keyboard", "price": 89.99, "stock": 50},
    {"id": "3", "name": "USB-C Hub", "price": 39.99, "stock": 200},
]

for p in SEED_PRODUCTS:
    PRODUCTS[p["id"]] = p


# ----------------------------------------------------------------------
# Pydantic models
# ----------------------------------------------------------------------
class Product(BaseModel):
    """Represents a product in the catalog."""
    id: str
    name: str
    price: float
    stock: int


class ProductCreate(BaseModel):  # Not used in endpoints but for extensibility
    """Schema for creating a new product (admin only)."""
    name: str = Field(..., min_length=1, max_length=100)
    price: float = Field(..., gt=0)
    stock: int = Field(..., ge=0)


class CartItem(BaseModel):
    """Represents an item in the shopping cart."""
    id: str
    product_id: str
    quantity: int = Field(..., ge=1)
    product_name: Optional[str] = None
    unit_price: Optional[float] = None


class AddToCartRequest(BaseModel):
    """Request body for adding an item to the cart."""
    product_id: str
    quantity: int = Field(default=1, ge=1, le=100)

    @validator("product_id")
    def product_must_exist(cls, v):
        if v not in PRODUCTS:
            raise ValueError("Product not found")
        return v


class CartResponse(BaseModel):
    """Response containing the cart details."""
    cart_id: str
    items: List[CartItem]
    total: float


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str


# ----------------------------------------------------------------------
# Security: Simple API key check (if SECRET_KEY is set)
# ----------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "")


async def verify_api_key(authorization: Optional[str] = None):
    """Dependency to verify API key in Authorization header."""
    if SECRET_KEY:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = authorization.split(" ")[1]
        if token != SECRET_KEY:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid API key",
            )
    return True


# ----------------------------------------------------------------------
# Endpoints - Products
# ----------------------------------------------------------------------
@app.get(
    "/products",
    response_model=List[Product],
    summary="List all products",
    description="Returns a list of all available products.",
)
async def list_products():
    """Return all products from the in-memory store."""
    return list(PRODUCTS.values())


@app.get(
    "/products/{product_id}",
    response_model=Product,
    responses={404: {"model": ErrorResponse, "description": "Product not found"}},
    summary="Get product details",
    description="Retrieve details for a specific product by its ID.",
)
async def get_product(product_id: str):
    """Get a single product by its ID."""
    product = PRODUCTS.get(product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found",
        )
    return product


# ----------------------------------------------------------------------
# Endpoints - Cart
# ----------------------------------------------------------------------
def _get_or_create_cart(cart_id: str = None) -> str:
    """Get an existing cart or create a new one if no cart_id provided."""
    if cart_id and cart_id in CARTS:
        return cart_id
    new_id = str(uuid.uuid4())
    CARTS[new_id] = {"items": {}}
    return new_id


@app.post(
    "/cart",
    response_model=CartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add item to cart",
    description="Add a product to the cart. If no cart_id is provided, a new cart is created.",
    responses={400: {"model": ErrorResponse, "description": "Invalid input or insufficient stock"}},
)
async def add_to_cart(
    request: AddToCartRequest,
    cart_id: Optional[str] = None
):
    """
    Add a product to the cart.

    - **product_id**: ID of the product to add.
    - **quantity**: Number of units (1-100).
    - **cart_id** (optional): Existing cart ID. If empty, creates a new cart.
    """
    product = PRODUCTS.get(request.product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product '{request.product_id}' does not exist.",
        )

    # Check stock availability
    cart = CARTS.get(cart_id, {"items": {}})
    current_qty = cart["items"].get(request.product_id, {}).get("quantity", 0)
    total_requested = current_qty + request.quantity
    if total_requested > product["stock"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock for '{product['name']}'. "
                   f"Available: {product['stock'] - current_qty}, requested: {request.quantity}.",
        )

    # Create or update cart
    cart_id = _get_or_create_cart(cart_id)
    cart = CARTS[cart_id]

    if request.product_id in cart["items"]:
        cart["items"][request.product_id]["quantity"] += request.quantity
    else:
        item_id = str(uuid.uuid4())
        cart["items"][request.product_id] = {
            "id": item_id,
            "product_id": request.product_id,
            "quantity": request.quantity,
            "product_name": product["name"],
            "unit_price": product["price"],
        }

    # Build response
    items = list(cart["items"].values())
    total = sum(item["unit_price"] * item["quantity"] for item in items)
    return CartResponse(cart_id=cart_id, items=items, total=round(total, 2))


@app.get(
    "/cart",
    response_model=CartResponse,
    summary="View cart",
    description="Retrieve the contents and total of a specific cart.",
    responses={404: {"model": ErrorResponse, "description": "Cart not found"}},
)
async def get_cart(cart_id: str):
    """Get the current cart's items and total price."""
    cart = CARTS.get(cart_id)
    if not cart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cart with id {cart_id} not found.",
        )

    items = list(cart["items"].values())
    total = sum(item["unit_price"] * item["quantity"] for item in items)
    return CartResponse(cart_id=cart_id, items=items, total=round(total, 2))


@app.delete(
    "/cart/{item_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove item from cart",
    description="Remove a specific line item from the cart using its item ID.",
    responses={
        404: {"model": ErrorResponse, "description": "Cart or item not found"},
        400: {"model": ErrorResponse, "description": "Cart ID required"},
    },
)
async def remove_cart_item(
    item_id: str,
    cart_id: Optional[str] = None
):
    """
    Remove an item from the cart.

    - **item_id**: The unique identifier of the item (from the CartItem response).
    - **cart_id** (optional): ID of the cart. If not provided, the request will fail.
    """
    if not cart_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'cart_id' is required.",
        )

    cart = CARTS.get(cart_id)
    if not cart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cart with id {cart_id} not found.",
        )

    # Find item by ID in the cart's items
    item_to_remove = None
    product_id_to_remove = None
    for pid, item in cart["items"].items():
        if item["id"] == item_id:
            item_to_remove = item
            product_id_to_remove = pid
            break

    if not item_to_remove:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found in cart {cart_id}.",
        )

    del cart["items"][product_id_to_remove]

    # Recalculate and return updated cart
    items = list(cart["items"].values())
    total = sum(item["unit_price"] * item["quantity"] for item in items)
    return CartResponse(cart_id=cart_id, items=items, total=round(total, 2))


# ----------------------------------------------------------------------
# Run the application
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=True)