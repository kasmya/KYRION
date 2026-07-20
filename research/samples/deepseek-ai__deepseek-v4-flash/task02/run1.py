from fastapi import FastAPI, HTTPException, status, Query, Path, Body, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, conint, PositiveInt
from typing import List, Optional, Dict
import uvicorn

# ---------------------------
# In-memory data stores
# ---------------------------

products_db: List[Dict] = [
    {"id": 1, "name": "Laptop", "price": 999.99, "description": "High performance laptop"},
    {"id": 2, "name": "Mouse", "price": 19.99, "description": "Wireless optical mouse"},
    {"id": 3, "name": "Keyboard", "price": 49.99, "description": "Mechanical keyboard"},
    {"id": 4, "name": "Monitor", "price": 299.99, "description": "27 inch 4K monitor"},
]

# Cart storage: keyed by user_id (for demo we use a fixed user)
# In a real application you would retrieve the authenticated user.
cart_db: Dict[int, List[Dict]] = {}  # {user_id: [{"product_id": ..., "quantity": ...}, ...]}

# For simplicity, use a default user_id
DEFAULT_USER_ID = 1

# ---------------------------
# Pydantic Models
# ---------------------------

class ProductOut(BaseModel):
    id: int
    name: str
    price: float
    description: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "id": 1,
                "name": "Laptop",
                "price": 999.99,
                "description": "High performance laptop"
            }
        }

class CartItemIn(BaseModel):
    product_id: PositiveInt = Field(..., description="ID of the product to add")
    quantity: conint(ge=1) = Field(1, description="Quantity of the product")

    class Config:
        schema_extra = {
            "example": {
                "product_id": 1,
                "quantity": 2
            }
        }

class CartItemOut(BaseModel):
    product_id: int
    name: str
    price: float
    quantity: int
    total: float

    class Config:
        schema_extra = {
            "example": {
                "product_id": 1,
                "name": "Laptop",
                "price": 999.99,
                "quantity": 2,
                "total": 1999.98
            }
        }

class CartOut(BaseModel):
    items: List[CartItemOut]
    total_price: float

    class Config:
        schema_extra = {
            "example": {
                "items": [
                    {
                        "product_id": 1,
                        "name": "Laptop",
                        "price": 999.99,
                        "quantity": 2,
                        "total": 1999.98
                    }
                ],
                "total_price": 1999.98
            }
        }

# ---------------------------
# Security & dependencies
# ---------------------------

# In a real application, you would implement proper authentication (e.g., OAuth2, JWT).
# Here we simulate a simple API key header validation.
# For demo purposes, we accept any non-empty API key.
# SECURITY BEST PRACTICE: Never hardcode secrets; use environment variables.
from fastapi.security import APIKeyHeader
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_current_user_id(api_key: Optional[str] = None) -> int:
    """
    Dummy user authentication.
    In production, validate the API key and return the corresponding user ID.
    """
    # For simplicity, return the default user.
    return DEFAULT_USER_ID

# ---------------------------
# FastAPI App
# ---------------------------

app = FastAPI(
    title="E-Commerce API",
    description="A simple e-commerce REST API with product listing and cart management.",
    version="1.0.0",
)

# ---------------------------
# Endpoints
# ---------------------------

@app.get(
    "/products",
    response_model=List[ProductOut],
    summary="Get all products",
    description="Returns a list of all available products.",
    tags=["Products"],
)
async def get_products():
    """
    Retrieve all products from the database.
    """
    return [ProductOut(**prod) for prod in products_db]


@app.get(
    "/products/{product_id}",
    response_model=ProductOut,
    summary="Get product details",
    description="Returns details of a single product by its ID.",
    tags=["Products"],
    responses={404: {"description": "Product not found"}},
)
async def get_product(product_id: int = Path(..., ge=1, description="ID of the product")):
    """
    Retrieve a product by its unique identifier.
    """
    for prod in products_db:
        if prod["id"] == product_id:
            return ProductOut(**prod)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Product with id {product_id} not found",
    )


@app.post(
    "/cart",
    response_model=CartOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add item to cart",
    description="Add a product to the user's cart. Requires product_id and quantity.",
    tags=["Cart"],
    responses={
        400: {"description": "Invalid input (e.g., product does not exist)"},
    },
)
async def add_to_cart(
    item: CartItemIn = Body(..., description="Cart item to add"),
    user_id: int = Depends(get_current_user_id),
):
    """
    Add a product to the shopping cart. If the product already exists in the cart,
    the quantity is increased.
    """
    # Validate product exists
    product = None
    for prod in products_db:
        if prod["id"] == item.product_id:
            product = prod
            break
    if not product:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product with id {item.product_id} does not exist",
        )

    # Initialize cart for user if not exists
    if user_id not in cart_db:
        cart_db[user_id] = []

    # Update existing or append new item
    cart = cart_db[user_id]
    for cart_item in cart:
        if cart_item["product_id"] == item.product_id:
            cart_item["quantity"] += item.quantity
            break
    else:
        cart.append({"product_id": item.product_id, "quantity": item.quantity})

    # Build response
    return _build_cart_out(user_id, cart_db)


@app.get(
    "/cart",
    response_model=CartOut,
    summary="View cart",
    description="Returns the current user's shopping cart with items and total price.",
    tags=["Cart"],
)
async def view_cart(user_id: int = Depends(get_current_user_id)):
    """
    Retrieve all items in the user's cart.
    """
    if user_id not in cart_db:
        return CartOut(items=[], total_price=0.0)
    return _build_cart_out(user_id, cart_db)


@app.delete(
    "/cart/{product_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove item from cart",
    description="Remove a product from the user's cart by product ID.",
    tags=["Cart"],
    responses={
        404: {"description": "Product not found in cart"},
    },
)
async def remove_from_cart(
    product_id: int = Path(..., ge=1, description="ID of the product to remove"),
    user_id: int = Depends(get_current_user_id),
):
    """
    Remove an item from the shopping cart. If the product is not in the cart,
    a 404 error is returned.
    """
    if user_id not in cart_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart is empty",
        )

    cart = cart_db[user_id]
    for i, item in enumerate(cart):
        if item["product_id"] == product_id:
            del cart[i]
            return _build_cart_out(user_id, cart_db)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Product with id {product_id} not found in cart",
    )


# ---------------------------
# Helper function
# ---------------------------

def _build_cart_out(user_id: int, cart_db: Dict[int, List[Dict]]) -> CartOut:
    """
    Build a CartOut response from the internal cart representation.
    """
    cart = cart_db.get(user_id, [])
    items_out: List[CartItemOut] = []
    total_price = 0.0

    # Build item details with product info
    for cart_item in cart:
        product = None
        for prod in products_db:
            if prod["id"] == cart_item["product_id"]:
                product = prod
                break
        if product is None:
            # Product might have been deleted; skip or handle accordingly.
            continue
        price = product["price"]
        quantity = cart_item["quantity"]
        total = round(price * quantity, 2)
        items_out.append(
            CartItemOut(
                product_id=product["id"],
                name=product["name"],
                price=price,
                quantity=quantity,
                total=total,
            )
        )
        total_price += total

    total_price = round(total_price, 2)
    return CartOut(items=items_out, total_price=total_price)


# ---------------------------
# Startup event (for seeding)
# ---------------------------

@app.on_event("startup")
async def startup_event():
    """
    Seed the default user's cart with an empty list.
    """
    if DEFAULT_USER_ID not in cart_db:
        cart_db[DEFAULT_USER_ID] = []


# ---------------------------
# Entry point
# ---------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Disable in production
    )