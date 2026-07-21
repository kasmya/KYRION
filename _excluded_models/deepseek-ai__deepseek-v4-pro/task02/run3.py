"""
E-commerce REST API module providing product listing and cart management endpoints.
Uses Flask for HTTP handling, Pydantic for data validation, and Flask-CORS for security.
"""
from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import Any, Dict, List, Optional

from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from pydantic import BaseModel, Field, ValidationError, conint

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ---------------------------------------------------------------------------
# In-memory data stores
# ---------------------------------------------------------------------------
PRODUCTS: Dict[str, Dict[str, Any]] = {
    "1": {"id": "1", "name": "Laptop", "price": 999.99, "stock": 10},
    "2": {"id": "2", "name": "Mouse", "price": 29.99, "stock": 100},
    "3": {"id": "3", "name": "Keyboard", "price": 79.99, "stock": 50},
}

CARTS: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Pydantic models for request/response validation
# ---------------------------------------------------------------------------
class CartItemRequest(BaseModel):
    """Expected payload for adding an item to the cart."""

    product_id: str = Field(..., min_length=1, description="ID of the product")
    quantity: conint(gt=0) = Field(..., description="Quantity must be a positive integer")


class CartItemResponse(BaseModel):
    """Item representation returned in cart endpoints."""

    product_id: str
    quantity: int
    product_name: str
    unit_price: float
    total_price: float


class CartResponse(BaseModel):
    """Full cart representation."""

    cart_id: str
    items: List[CartItemResponse]
    total: float


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def _error_response(status_code: int, message: str) -> Response:
    """Return a JSON error response with the given status code and message."""
    response = jsonify({"error": message})
    response.status_code = status_code
    return response


def _compute_cart_response(cart: Dict[str, Any]) -> CartResponse:
    """Build a CartResponse from the internal cart dictionary."""
    items: List[CartItemResponse] = []
    total = 0.0
    for item in cart["items"]:
        product = PRODUCTS.get(item["product_id"])
        if product is None:
            continue
        total_price = round(product["price"] * item["quantity"], 2)
        items.append(
            CartItemResponse(
                product_id=item["product_id"],
                quantity=item["quantity"],
                product_name=product["name"],
                total_price=total_price,
            )
        )
        total += total_price
    total = round(total, 2)
    return CartResponse(cart_id=cart["cart_id"], items=items, total=total)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.route("/products", methods=["GET"])
def get_products() -> Response:
    """
    Return the list of all available products.

    Returns:
        JSON array of product objects with id, name, price, and stock.
    """
    return jsonify(list(PRODUCTS.values())), HTTPStatus.OK


@app.route("/products/<product_id>", methods=["GET"])
def get_product(product_id: str) -> Response:
    """
    Retrieve a single product by its ID.

    Args:
        product_id: The unique identifier of the product.

    Returns:
        JSON object with product details or a 404 error if not found.
    """
    product = PRODUCTS.get(product_id)
    if product is None:
        return _error_response(HTTPStatus.NOT_FOUND, "Product not found")
    return jsonify(product), HTTPStatus.OK


@app.route("/cart", methods=["POST"])
def add_to_cart() -> Response:
    """
    Add an item to an existing cart or create a new one.

    The request body must include ``product_id`` and ``quantity``.
    A ``cart_id`` can be provided via the ``X-Cart-Id`` header to target
    an existing cart; otherwise a new cart is created.

    Returns:
        JSON representation of the updated cart with a 201 status code,
        or an error response on validation / business-rule failures.
    """
    # Parse and validate input
    try:
        data = request.get_json(silent=True)
        if data is None:
            return _error_response(HTTPStatus.BAD_REQUEST, "Request body must be valid JSON")
        item = CartItemRequest(**data)
    except ValidationError as exc:
        return _error_response(HTTPStatus.BAD_REQUEST, str(exc))

    # Validate product existence
    if item.product_id not in PRODUCTS:
        return _error_response(HTTPStatus.BAD_REQUEST, "Product does not exist")

    # Check stock availability
    product = PRODUCTS[item.product_id]
    if item.quantity > product["stock"]:
        return _error_response(HTTPStatus.BAD_REQUEST, "Insufficient stock")

    # Retrieve or create cart
    cart_id = request.headers.get("X-Cart-ID")
    if cart_id and cart_id in CARTS:
        cart = CARTS[cart_id]
    else:
        cart_id = str(uuid.uuid4())
        cart = {"cart_id": cart_id, "items": []}
        CARTS[cart_id] = cart

    # Update quantity if product already exists in cart
    existing = next((i for i in cart["items"] if i["product_id"] == item.product_id), None)
    if existing:
        new_qty = existing["quantity"] + item.quantity
        if new_qty > product["stock"]:
            return _error_response(HTTPStatus.BAD_REQUEST, "Insufficient stock for the total quantity")
        existing["quantity"] = new_qty
    else:
        cart["items"].append({"product_id": item.product_id, "quantity": item.quantity})

    cart_response = _compute_cart_response(cart)
    resp = jsonify(cart_response.dict())
    resp.status_code = HTTPStatus.CREATED
    resp.headers["X-Cart-ID"] = cart_id
    return resp


@app.route("/cart", methods=["GET"])
def get_cart() -> Response:
    """
    Retrieve the current cart contents.

    The cart is identified by the ``X-Cart-ID`` header.
    If the header is missing or the cart does not exist, an empty cart
    is returned with a newly generated ID.

    Returns:
        JSON representation of the cart.
    """
    cart_id = request.headers.get("X-Cart-ID")
    if not cart_id or cart_id not in CARTS:
        # Create an empty cart and return it
        cart_id = str(uuid.uuid4())
        cart = {"cart_id": cart_id, "items": []}
        CARTS[cart_id] = cart
    else:
        cart = CARTS[cart_id]

    cart_response = _compute_cart_response(cart)
    resp = jsonify(cart_response.dict())
    resp.status_code = HTTPStatus.OK
    resp.headers["X-Cart-ID"] = cart_id
    return resp


@app.route("/cart/<item_product_id>", methods=["DELETE"])
def remove_from_cart(item_product_id: str) -> Response:
    """
    Remove a specific product from the cart.

    The cart is identified by the ``X-Cart-ID`` header.

    Args:
        item_product_id: The product ID to remove from the cart.

    Returns:
        JSON representation of the updated cart, or an error if the
        cart or product is not found.
    """
    cart_id = request.headers.get("X-Cart-ID")
    if not cart_id or cart_id not in CARTS:
        return _error_response(HTTPStatus.NOT_FOUND, "Cart not found")

    cart = CARTS[cart_id]
    original_len = len(cart["items"])
    cart["items"] = [i for i in cart["items"] if i["product_id"] != item_product_id]

    if len(cart["items"]) == original_len:
        return _error_response(HTTPStatus.NOT_FOUND, "Product not found in cart")

    cart_response = _compute_cart_response(cart)
    resp = jsonify(cart_response.dict())
    resp.status_code = HTTPStatus.OK
    resp.headers["X-Cart-ID"] = cart_id
    return resp


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.errorhandler(HTTPStatus.NOT_FOUND)
def handle_not_found(_error: Any) -> Response:
    """Return a JSON 404 for unknown endpoints."""
    return _error_response(HTTPStatus.NOT_FOUND, "The requested resource was not found")


@app.errorhandler(HTTPStatus.METHOD_NOT_ALLOWED)
def handle_method_not_allowed(_error: Any) -> Response:
    """Return a JSON 405 for unsupported HTTP methods."""
    return _error_response(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed")


@app.errorhandler(500)
def handle_internal_error(_error: Any) -> Response:
    """Return a JSON 500 for unhandled internal errors."""
    return _error_response(HTTPStatus.INTERNAL_SERVER_ERROR, "Internal server error")


if __name__ == "__main__":
    app.run(debug=False)