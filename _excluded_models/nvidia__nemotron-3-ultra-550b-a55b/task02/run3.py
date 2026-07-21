"""
E-commerce REST API module.

This module provides a simple e-commerce REST API with endpoints for product
listing, product details, and shopping cart management. It uses FastAPI for
routing, validation, and automatic API documentation. Data is stored in-memory
for demonstration purposes.

Endpoints:
- GET /products: List all products.
- GET /products/{product_id}: Retrieve a product by ID.
- POST /cart: Add an item to the cart.
- GET /cart: View the current cart contents.
- DELETE /cart/{item_id}: Remove an item from the cart.

Security considerations:
- Input validation via Pydantic models prevents injection attacks.
- Explicit error handling with appropriate HTTP status codes.
- No sensitive data is logged or exposed.
- In a production environment, add authentication, rate limiting, and HTTPS.
"""

from typing import List, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, PositiveInt, PositiveFloat

app = FastAPI(
    title="E-commerce API",
    description="A simple e-commerce REST API for products and cart management.",
    version="1.0.0",
)


class Product(BaseModel):
    """Represents a product in the catalog."""
    id: int
    name: str = Field(..., min_length=1, max_length=100)
    price: PositiveFloat
    description: str = Field("", max_length=500)


class CartItem(BaseModel):
    """Represents an item in the shopping cart."""
    id: int
    product_id: int
    quantity: PositiveInt


class CartItemCreate(BaseModel):
    """Input model for adding an item to the cart."""
    product_id: int
    quantity: PositiveInt = 1


# In-memory data stores
_products: List[Product] = [
    Product(id=1, name="Laptop", price=999.99, description="High-performance laptop"),
    Product(id=2, name="Smartphone", price=699.99, description="Latest smartphone"),
    Product(id=3, name="Headphones", price=199.99, description="Noise-cancelling headphones"),
]

_cart: List[CartItem] = []
_next_cart_item_id: int = 1


def _find_product(product_id: int) -> Optional[Product]:
    """
    Find a product by its ID.

    Args:
        product_id: The ID of the product to find.

    Returns:
        The Product if found, otherwise None.
    """
    for product in _products:
        if product.id == product_id:
            return product
    return None


def _find_cart_item(item_id: int) -> Optional[CartItem]:
    """
    Find a cart item by its ID.

    Args:
        item_id: The ID of the cart item to find.

    Returns:
        The CartItem if found, otherwise None.
    """
    for item in _cart:
        if item.id == item_id:
            return item
    return None


@app.get(
    "/products",
    response_model=List[Product],
    summary="List all products",
    response_description="A list of available products",
)
def list_products() -> List[Product]:
    """
    Retrieve a list of all products.

    Returns:
        List[Product]: A list of all products in the catalog.
    """
    return _products


@app.get(
    "/products/{product_id}",
    response_model=Product,
    summary="Get a product by ID",
    response_description("The requested product"),
    responses={404: {"description": "Product not found"}},
)
def get_product(product_id: int) -> Product:
    """
    Retrieve a single product by its ID.

    Args:
        product_id: The ID of the product to retrieve.

    Returns:
        Product: The product with the given ID.

    Raises:
        HTTPException: If the product is not found (404).
    """
    product = _find_product(product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} not found",
        )
    return product


@app.post(
    "/cart",
    response_model=CartItem,
    status_code=status.HTTP_201_CREATED,
    summary="Add an item to the cart",
    response_description("The created cart item"),
    responses={
        400: {"description": "Invalid input"},
        404: {"description": "Product not found"},
    },
)
def add_to_cart(item_data: CartItemCreate) -> CartItem:
    """
    Add an item to the shopping cart.

    Args:
        item_data: The product ID and quantity to add.

    Returns:
        CartItem: The newly created cart item.

    Raises:
        HTTPException: If the product does not exist (404) or quantity is invalid (400).
    """
    global _next_cart_item_id

    product = _find_product(item_data.product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {item_data.product_id} not found",
        )

    # Check if item already in cart for the same product
    for existing_item in _cart:
        if existing_item.product_id == item_data.product_id:
            existing_item.quantity += item_data.quantity
            return existing_item

    new_item = CartItem(
        id=_next_cart_item_id,
        product_id=item_data.product_id,
        quantity=item_data.quantity,
    )
    _cart.append(new_item)
    _next_cart_item_id += 1
    return new_item


@app.get(
    "/cart",
    response_model=List[CartItem],
    summary="View cart contents",
    response_description("List of items in the cart",
)
def view_cart() -> List[CartItem]:
    """
    Retrieve the current contents of the shopping cart.

    Returns:
        List[CartItem]: A list of all items currently in the cart.
    """
    return _cart


@app.delete(
    "/cart/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an item from the cart",
    responses={404: {"description": "Cart item not found"}},
)
def remove_from_cart(item_id: int) -> None:
    """
    Remove an item from the shopping cart by its ID.

    Args:
        item_id: The ID of the cart item to remove.

    Raises:
        HTTPException: If the cart item is not found (404).
    """
    item = _find_cart_item(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cart item with ID {item_id} not found",
        )
    _cart.remove(item)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)