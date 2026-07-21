"""
E-commerce REST API Module

This module provides a simple e-commerce REST API with endpoints for product listing,
product details, and shopping cart management. It uses Flask for the web framework
and in-memory storage with thread-safe operations.
"""

import json
import threading
import uuid
from dataclasses import dataclass, asdict
from http import HTTPStatus
from typing import Dict, List, Optional, Tuple, Union

from flask import Flask, jsonify, request, Response

app = Flask(__name__)

# Thread-safe storage
_products_lock = threading.RLock()
_cart_lock = threading.RLock()

# In-memory data stores
_products: Dict[str, "Product"] = {}
_cart_items: Dict[str, "CartItem"] = {}


@dataclass
class Product:
    """Represents a product in the catalog."""
    id: str
    name: str
    description: str
    price: float
    stock: int


@dataclass
class CartItem:
    """Represents an item in the shopping cart."""
    id: str
    product_id: str
    quantity: int


def _initialize_sample_data() -> None:
    """Initialize sample product data for demonstration."""
    global _products
    with _products_lock:
        _products = {
            "prod_001": Product("prod_001", "Laptop", "High-performance laptop", 999.99, 10),
            "prod_002": Product("prod_002", "Mouse", "Wireless optical mouse", 29.99, 50),
            "prod_003": Product("prod_003", "Keyboard", "Mechanical keyboard", 89.99, 30),
        }


def _validate_product_data(data: dict) -> Tuple[bool, Optional[str]]:
    """Validate product data for creation/update."""
    required_fields = ["name", "description", "price", "stock"]
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"

    if not isinstance(data["name"], str) or not data["name"].strip():
        return False, "Name must be a non-empty string"
    if not isinstance(data["description"], str):
        return False, "Description must be a string"
    if not isinstance(data["price"], (int, float)) or data["price"] < 0:
        return False, "Price must be a non-negative number"
    if not isinstance(data["stock"], int) or data["stock"] < 0:
        return False, "Stock must be a non-negative integer"

    return True, None


def _validate_cart_item_data(data: dict) -> Tuple[bool, Optional[str]]:
    """Validate cart item data for addition."""
    required_fields = ["product_id", "quantity"]
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"

    if not isinstance(data["product_id"], str) or not data["product_id"].strip():
        return False, "Product ID must be a non-empty string"
    if not isinstance(data["quantity"], int) or data["quantity"] <= 0:
        return False, "Quantity must be a positive integer"

    return True, None


def _create_error_response(message: str, status_code: int) -> Response:
    """Create a standardized JSON error response."""
    response = jsonify({"error": message})
    response.status_code = status_code
    return response


@app.route("/products", methods=["GET"])
def get_products() -> Response:
    """
    Retrieve a list of all products.

    Returns:
        Response: JSON array of product objects with HTTP 200 status.
    """
    with _products_lock:
        products_list = [asdict(product) for product in _products.values()]
    return jsonify(products_list)


@app.route("/products/<string:product_id>", methods=["GET"])
def get_product(product_id: str) -> Response:
    """
    Retrieve a specific product by ID.

    Args:
        product_id: The unique identifier of the product.

    Returns:
        Response: JSON product object with HTTP 200 status, or error with HTTP 404.
    """
    with _products_lock:
        product = _products.get(product_id)

    if product is None:
        return _create_error_response("Product not found", HTTPStatus.NOT_FOUND)

    return jsonify(asdict(product))


@app.route("/cart", methods=["POST"])
def add_to_cart() -> Response:
    """
    Add an item to the shopping cart.

    Expects JSON payload with:
        - product_id (str): ID of the product to add
        - quantity (int): Quantity to add (must be positive)

    Returns:
        Response: JSON cart item object with HTTP 201 status, or error with appropriate status.
    """
    if not request.is_json:
        return _create_error_response("Request must be JSON", HTTPStatus.BAD_REQUEST)

    data = request.get_json()
    valid, error_msg = _validate_cart_item_data(data)
    if not valid:
        return _create_error_response(error_msg, HTTPStatus.BAD_REQUEST)

    product_id = data["product_id"]
    quantity = data["quantity"]

    # Verify product exists and has sufficient stock
    with _products_lock:
        product = _products.get(product_id)
        if product is None:
            return _create_error_response("Product not found", HTTPStatus.NOT_FOUND)
        if product.stock < quantity:
            return _create_error_response("Insufficient stock", HTTPStatus.CONFLICT)

    # Create cart item
    cart_item_id = str(uuid.uuid4())
    cart_item = CartItem(id=cart_item_id, product_id=product_id, quantity=quantity)

    with _cart_lock:
        _cart_items[cart_item_id] = cart_item

    response = jsonify(asdict(cart_item))
    response.status_code = HTTPStatus.CREATED
    return response


@app.route("/cart", methods=["GET"])
def get_cart() -> Response:
    """
    Retrieve all items in the shopping cart.

    Returns:
        Response: JSON array of cart item objects with HTTP 200 status.
    """
    with _cart_lock:
        cart_list = [asdict(item) for item in _cart_items.values()]
    return jsonify(cart_list)


@app.route("/cart/<string:cart_item_id>", methods=["DELETE"])
def remove_from_cart(cart_item_id: str) -> Response:
    """
    Remove an item from the shopping cart by cart item ID.

    Args:
        cart_item_id: The unique identifier of the cart item.

    Returns:
        Response: Empty response with HTTP 204 status, or error with HTTP 404.
    """
    with _cart_lock:
        if cart_item_id not in _cart_items:
            return _create_error_response("Cart item not found", HTTPStatus.NOT_FOUND)
        del _cart_items[cart_item_id]

    return Response(status=HTTPStatus.NO_CONTENT)


# Initialize sample data on module load
_initialize_sample_data()


if __name__ == "__main__":
    # Run the Flask development server
    app.run(debug=False, host="0.0.0.0", port=5000)