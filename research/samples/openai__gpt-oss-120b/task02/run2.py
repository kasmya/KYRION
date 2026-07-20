"""E‑commerce REST API using FastAPI.

Provides:
- GET /products
- GET /products/{product_id}
- POST /cart
- GET /cart
- DELETE /cart/{cart_item_id}

Features:
- Type hints and Pydantic models
- Basic API‑Key security
- CORS handling
- In‑memory data stores (for demonstration)
- Detailed docstrings and error handling
"""

from __future__ import annotations

from typing import Dict, List

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Header,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, PositiveInt, conint, confloat

# --------------------------------------------------------------------------- #
# Security
# --------------------------------------------------------------------------- #

API_KEY = "secret-key"  # In production use environment variables / secret manager


def api_key_auth(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    """Simple API‑Key authentication dependency."""
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #

class Product(BaseModel):
    """Product representation."""
    id: int
    name: str = Field(..., max_length=100)
    description: str = Field(..., max_length=500)
    price: confloat(gt=0)  # positive float
    available_quantity: conint(ge=0)


class ProductCreate(BaseModel):
    """Model for creating a product (used internally)."""
    name: str = Field(..., max_length=100)
    description: str = Field(..., max_length=500)
    price: confloat(gt=0)
    available_quantity: conint(ge=0)


class CartItem(BaseModel):
    """Cart item representation."""
    id: int
    product_id: int
    quantity: PositiveInt


class CartItemCreate(BaseModel):
    """Payload for adding an item to the cart."""
    product_id: int
    quantity: PositiveInt


# --------------------------------------------------------------------------- #
# In‑memory stores (replace with DB in real applications)
# --------------------------------------------------------------------------- #

class Store:
    """Thread‑unsafe in‑memory store used for demonstration."""
    _products: Dict[int, Product] = {}
    _next_product_id: int = 1

    _cart_items: Dict[int, CartItem] = {}
    _next_cart_item_id: int = 1

    @classmethod
    def init_sample_data(cls) -> None:
        """Populate the store with a handful of sample products."""
        sample = [
            ProductCreate(
                name="Wireless Mouse",
                description="Ergonomic wireless mouse with 2.4 GHz connectivity.",
                price=29.99,
                available_quantity=150,
            ),
            ProductCreate(
                name="Mechanical Keyboard",
                description="RGB backlit mechanical keyboard with blue switches.",
                price=79.5,
                available_quantity=85,
            ),
            ProductCreate(
                name="Noise‑Cancelling Headphones",
                description="Over‑ear headphones with active noise cancellation.",
                price=199.99,
                available_quantity=40,
            ),
        ]
        for p in sample:
            cls.add_product(p)

    @classmethod
    def add_product(cls, data: ProductCreate) -> Product:
        """Add a new product and return the created instance."""
        product = Product(
            id=cls._next_product_id,
            **data.dict(),
        )
        cls._products[product.id] = product
        cls._next_product_id += 1
        return product

    @classmethod
    def get_product(cls, product_id: int) -> Product | None:
        """Retrieve a product by its ID."""
        return cls._products.get(product_id)

    @classmethod
    def list_products(cls) -> List[Product]:
        """Return all products."""
        return list(cls._products.values())

    @classmethod
    def add_to_cart(cls, product_id: int, quantity: int) -> CartItem:
        """Add an item to the cart after validating stock."""
        product = cls.get_product(product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found",
            )
        if product.available_quantity < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Requested quantity exceeds available stock",
            )
        # Reserve stock
        product.available_quantity -= quantity

        cart_item = CartItem(
            id=cls._next_cart_item_id,
            product_id=product_id,
            quantity=quantity,
        )
        cls._cart_items[cart_item.id] = cart_item
        cls._next_cart_item_id += 1
        return cart_item

    @classmethod
    def list_cart_items(cls) -> List[CartItem]:
        """Return all items currently in the cart."""
        return list(cls._cart_items.values())

    @classmethod
    def get_cart_item(cls, cart_item_id: int) -> CartItem | None:
        """Retrieve a cart item by ID."""
        return cls._cart_items.get(cart_item_id)

    @classmethod
    def remove_cart_item(cls, cart_item_id: int) -> None:
        """Remove a cart item and restore product stock."""
        cart_item = cls._cart_items.pop(cart_item_id, None)
        if cart_item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cart item {cart_item_id} not found",
            )
        product = cls.get_product(cart_item.product_id)
        if product:
            product.available_quantity += cart_item.quantity


# Initialise sample catalogue
Store.init_sample_data()

# --------------------------------------------------------------------------- #
# FastAPI application
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="E‑commerce API",
    version="1.0.0",
    description="A simple demo e‑commerce REST API built with FastAPI.",
    swagger_ui_parameters={"docExpansion": "none"},
)


# Allow calls from any origin for demo purposes.
# In production restrict this list.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@app.get(
    "/products",
    response_model=List[Product],
    summary="List all products",
    dependencies=[Depends(api_key_auth)],
)
def list_products() -> List[Product]:
    """Return a list of all available products."""
    return Store.list_products()


@app.get(
    "/products/{product_id}",
    response_model=Product,
    summary="Get product details",
    responses={404: {"description": "Product not found"}},
    dependencies=[Depends(api_key_auth)],
)
def get_product(product_id: int) -> Product:
    """
    Retrieve a single product by its unique identifier.

    Args:
        product_id: Identifier of the product.

    Returns:
        Product data.

    Raises:
        HTTPException: 404 if product does not exist.
    """
    product = Store.get_product(product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found",
        )
    return product


@app.post(
    "/cart",
    response_model=CartItem,
    status_code=status.HTTP_201_CREATED,
    summary="Add an item to the cart",
    responses={400: {"description": "Invalid request"}, 404: {"description": "Product not found"}},
    dependencies=[Depends(api_key_auth)],
)
def add_to_cart(item: CartItemCreate) -> CartItem:
    """
    Add a product to the shopping cart.

    Validates product existence and available stock before reserving items.

    Args:
        item: Payload containing `product_id` and desired `quantity`.

    Returns:
        The created `CartItem`.

    Raises:
        HTTPException: 400 if stock insufficient, 404 if product missing.
    """
    return Store.add_to_cart(product_id=item.product_id, quantity=item.quantity)


@app.get(
    "/cart",
    response_model=List[CartItem],
    summary="View cart contents",
    dependencies=[Depends(api_key_auth)],
)
def view_cart() -> List[CartItem]:
    """Retrieve the list of items currently stored in the cart."""
    return Store.list_cart_items()


@app.delete(
    "/cart/{cart_item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an item from the cart",
    responses={404: {"description": "Cart item not found"}},
    dependencies=[Depends(api_key_auth)],
)
def delete_cart_item(cart_item_id: int, response: Response) -> None:
    """
    Remove a specific item from the cart and restore its stock.

    Args:
        cart_item_id: Identifier of the cart entry to delete.

    Returns:
        Empty response with HTTP 204 status.

    Raises:
        HTTPException: 404 if the cart item does not exist.
    """
    Store.remove_cart_item(cart_item_id)
    response.status_code = status.HTTP_204_NO_CONTENT


# --------------------------------------------------------------------------- #
# Run with: uvicorn <module_name>:app --reload
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)