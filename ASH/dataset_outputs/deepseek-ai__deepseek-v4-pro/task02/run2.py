"""
E-commerce REST API module.

Provides endpoints for product listing, cart management, and related operations.
Designed as a self-contained module using only standard library and Flask.
"""

from http import HTTPStatus
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from flask import Flask, jsonify, request

app: Flask = Flask(__name__)

# In-memory data stores for demonstration purposes.
# In production, replace with persistent storage and proper ORM.
_PRODUCTS: Dict[str, Dict[str, Any]] = {
    "1": {"id": "1", "name": "Widget", "price": 19.99, "stock": 100},
    "2": {"id": "2", "name": "Gadget", "price": 29.99, "stock": 50},
    "3": {"id": "3", "name": "Doohickey", "price": 9.99, "stock": 200},
}

_CARTS: Dict[str, Dict[str, Any]] = {}


def _validate_product_id(product_id: str) -> Optional[Tuple[Dict[str, Any], int]]:
    """
    Validate that a product exists.

    Args:
        product_id: The product identifier string.

    Returns:
        A tuple of (error_response, HTTP status code) if invalid, else None.
    """
    if product_id not in _PRODUCTS:
        return jsonify({"error": "Product not found"}), HTTPStatus.NOT_FOUND
    return None


def _validate_cart_exists(cart_id: str) -> Optional[Tuple[Dict[str, Any], int]]:
    """
    Validate that a cart exists.

    Args:
        cart_id: The cart identifier string.

    Returns:
        A tuple of (error_response, HTTP status code) if missing, else None.
    """
    if cart_id not in _CARTS:
        return jsonify({"error": "Cart not found"}), HTTPStatus.NOT_FOUND
    return None


def _validate_cart_item(cart_id: str, item_id: str) -> Optional[Tuple[Dict[str, Any], int]]:
    """
    Validate that a specific item exists within a cart.

    Args:
        cart_id: The cart identifier string.
        item_id: The item identifier string within the cart.

    Returns:
        A tuple of (error_response, HTTP status code) if missing, else None.
    """
    cart = _CARTS.get(cart_id)
    if cart is None:
        return jsonify({"error": "Cart not found"}), HTTPStatus.NOT_FOUND
    if item_id not in cart.get("items", {}):
        return jsonify({"error": "Item not found in cart"}), HTTPStatus.NOT_FOUND
    return None


@app.route("/products", methods=["GET"])
def list_products() -> Tuple[Dict[str, Any], int]:
    """
    GET /products
    Retrieve a list of all available products.

    Returns:
        JSON response with product list and HTTP 200.
    """
    products_list: List[Dict[str, Any]] = list(_PRODUCTS.values())
    return jsonify({"products": products_list}), HTTPStatus.OK


@app.route("/products/<product_id>", methods=["GET"])
def get_product(product_id: str) -> Tuple[Dict[str, Any], int]:
    """
    GET /products/{id}
    Retrieve a single product by identifier.

    Args:
        product_id: The product identifier from the URL path.

    Returns:
        JSON response with product data or error.
    """
    error = _validate_product_id(product_id)
    if error:
        return error
    return jsonify(_PRODUCTS[product_id]), HTTPStatus.OK


@app.route("/cart", methods=["POST"])
def create_cart() -> Tuple[Dict[str, Any], int]:
    """
    POST /cart
    Create a new shopping cart.

    Body (JSON): optional initial items
        {
            "items": [
                {"product_id": "1", "quantity": 2}
            ]
        }

    Returns:
        JSON response with the new cart ID and contents, HTTP 201.
    """
    cart_id: str = str(uuid4())
    items: Dict[str, Dict[str, Any]] = {}

    body: Optional[Dict[str, Any]] = request.get_json(silent=True)
    if body:
        # Validate and add initial items
        raw_items: List[Dict[str, Any]] = body.get("items", [])
        for entry in raw_items:
            prod_id: str = str(entry.get("product_id", ""))
            quantity: int = int(entry.get("quantity", 1))
            if quantity < 1:
                return jsonify({"error": "Quantity must be at least 1"}), HTTPStatus.BAD_REQUEST
            if prod_id not in _PRODUCTS:
                return jsonify({"error": f"Invalid product_id: {prod_id}"}), HTTPStatus.BAD_REQUEST
            # Prevent duplicate items by merging quantities
            if prod_id in items:
                items[prod_id]["quantity"] += quantity
            else:
                items[prod_id] = {"product_id": prod_id, "quantity": quantity}

    _CARTS[cart_id] = {"id": cart_id, "items": items}
    return jsonify(_CARTS[cart_id]), HTTPStatus.CREATED


@app.route("/cart/<cart_id>", methods=["GET"])
def get_cart(cart_id: str) -> Tuple[Dict[str, Any], int]:
    """
    GET /cart/{id}
    Retrieve the contents of a specific cart.

    Args:
        cart_id: The cart identifier from the URL path.

    Returns:
        JSON response with cart data or error.
    """
    error = _validate_cart_exists(cart_id)
    if error:
        return error
    return jsonify(_CARTS[cart_id]), HTTPStatus.OK


@app.route("/cart/<cart_id>/<item_id>", methods=["DELETE"])
def delete_cart_item(cart_id: str, item_id: str) -> Tuple[Dict[str, Any], int]:
    """
    DELETE /cart/{id}/{item_id}
    Remove a specific item from a cart.

    Args:
        cart_id: The cart identifier.
        item_id: The item identifier within the cart.

    Returns:
        JSON response with updated cart or error.
    """
    error = _validate_cart_item(cart_id, item_id)
    if error:
        return error
    del _CARTS[cart_id]["items"][item_id]
    return jsonify(_CARTS[cart_id]), HTTPStatus.OK


@app.errorhandler(HTTPStatus.NOT_FOUND)
def handle_not_found(error: Any) -> Tuple[Dict[str, Any], int]:
    """
    Custom handler for 404 errors to return consistent JSON.

    Args:
        error: The Flask error object.

    Returns:
        JSON error response with 404 status.
    """
    return jsonify({"error": "Resource not found"}), HTTPStatus.NOT_FOUND


@app.errorhandler(HTTPStatus.METHOD_NOT_ALLOWED)
def handle_method_not_allowed(error: Any) -> Tuple[Dict[str, Any], int]:
    """
    Custom handler for 405 errors to return consistent JSON.

    Args:
        error: The Flask error object.

    Returns:
        JSON error response with 405 status.
    """
    return jsonify({"error": "Method not allowed"}), HTTPStatus.METHOD_NOT_ALLOWED


if __name__ == "__main__":
    # Run only for development; in production use a proper WSGI server with HTTPS.
    app.run(host="127.0.0.1", port=8080, debug=False)