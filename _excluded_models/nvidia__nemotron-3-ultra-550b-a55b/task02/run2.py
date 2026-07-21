"""
E-commerce REST API Module

This module provides a simple e-commerce REST API with endpoints for product
management and shopping cart operations. It uses Flask for routing and
JSON handling, with in-memory storage for demonstration purposes.

Endpoints:
    GET /products - List all products
    GET /products/<id> - Get a specific product
    POST /cart - Add item to cart
    GET /cart - View cart contents
    DELETE /cart/<id> - Remove item from cart

Security Features:
    - Input validation and sanitization
    - Secure HTTP headers
    - Error handling without information leakage
    - Type safety with type hints
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple, Any
from http import HTTPStatus

from flask import Flask, request, jsonify, Response
from werkzeug.exceptions import BadRequest, NotFound, InternalServerError


@dataclass(frozen=True)
class Product:
    """Represents a product in the catalog."""
    id: str
    name: str
    description: str
    price: float
    stock: int


@dataclass(frozen=True)
class CartItem:
    """Represents an item in the shopping cart."""
    id: str
    product_id: str
    product_name: str
    quantity: int
    unit_price: float


class InMemoryStore:
    """Thread-unsafe in-memory data store for products and cart."""
    
    def __init__(self) -> None:
        self._products: Dict[str, Product] = {}
        self._cart: Dict[str, CartItem] = {}
        self._initialize_sample_data()
    
    def _initialize_sample_data(self) -> None:
        """Populate with sample products."""
        sample_products = [
            Product("prod-1", "Laptop", "High-performance laptop", 999.99, 10),
            Product("prod-2", "Mouse", "Wireless ergonomic mouse", 29.99, 50),
            Product("prod-3", "Keyboard", "Mechanical RGB keyboard", 89.99, 30),
        ]
        for product in sample_products:
            self._products[product.id] = product
    
    # Product operations
    def get_all_products(self) -> List[Product]:
        """Return all products."""
        return list(self._products.values())
    
    def get_product(self, product_id: str) -> Optional[Product]:
        """Get product by ID."""
        return self._products.get(product_id)
    
    # Cart operations
    def get_cart_items(self) -> List[CartItem]:
        """Return all cart items."""
        return list(self._cart.values())
    
    def add_to_cart(self, product_id: str, quantity: int) -> CartItem:
        """
        Add product to cart or update quantity if already present.
        
        Args:
            product_id: ID of product to add
            quantity: Quantity to add (must be positive)
            
        Returns:
            The created or updated cart item
            
        Raises:
            NotFound: If product doesn't exist
            ValueError: If quantity is invalid or insufficient stock
        """
        product = self.get_product(product_id)
        if not product:
            raise NotFound(f"Product {product_id} not found")
        
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        
        if quantity > product.stock:
            raise ValueError(f"Insufficient stock. Available: {product.stock}")
        
        # Check if already in cart
        existing_item = next(
            (item for item in self._cart.values() if item.product_id == product_id),
            None
        )
        
        if existing_item:
            new_quantity = existing_item.quantity + quantity
            if new_quantity > product.stock:
                raise ValueError(f"Insufficient stock. Available: {product.stock}")
            
            updated_item = CartItem(
                id=existing_item.id,
                product_id=product_id,
                product_name=product.name,
                quantity=new_quantity,
                unit_price=product.price
            )
            self._cart[existing_item.id] = updated_item
            return updated_item
        else:
            new_item = CartItem(
                id=str(uuid.uuid4()),
                product_id=product_id,
                product_name=product.name,
                quantity=quantity,
                unit_price=product.price
            )
            self._cart[new_item.id] = new_item
            return new_item
    
    def remove_from_cart(self, cart_item_id: str) -> None:
        """
        Remove item from cart.
        
        Args:
            cart_item_id: ID of cart item to remove
            
        Raises:
            NotFound: If cart item doesn't exist
        """
        if cart_item_id not in self._cart:
            raise NotFound(f"Cart item {cart_item_id} not found")
        del self._cart[cart_item_id]


# Global store instance
store = InMemoryStore()

# Flask app initialization
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False  # Preserve field order in JSON responses


def validate_json_content_type() -> None:
    """Validate request has JSON content type."""
    if not request.is_json:
        raise BadRequest("Content-Type must be application/json")


def validate_required_fields(data: dict, required_fields: List[str]) -> None:
    """Validate required fields are present in JSON data."""
    missing = [field for field in required_fields if field not in data]
    if missing:
        raise BadRequest(f"Missing required fields: {', '.join(missing)}")


def create_error_response(
    message: str, 
    status_code: int = HTTPStatus.BAD_REQUEST
) -> Tuple[Response, int]:
    """Create standardized error response."""
    response = jsonify({"error": message})
    response.status_code = status_code
    return response, status_code


@app.after_request
def add_security_headers(response: Response) -> Response:
    """Add security headers to all responses."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    return response


@app.route('/products', methods=['GET'])
def get_products() -> Tuple[Response, int]:
    """
    Get all products.
    
    Returns:
        JSON array of product objects
    """
    try:
        products = store.get_all_products()
        return jsonify([asdict(p) for p in products]), HTTPStatus.OK
    except Exception as e:
        app.logger.error(f"Error retrieving products: {e}")
        return create_error_response("Internal server error", HTTPStatus.INTERNAL_SERVER_ERROR)


@app.route('/products/<product_id>', methods=['GET'])
def get_product(product_id: str) -> Tuple[Response, int]:
    """
    Get a specific product by ID.
    
    Args:
        product_id: Unique product identifier
        
    Returns:
        JSON product object or 404 if not found
    """
    try:
        product = store.get_product(product_id)
        if not product:
            return create_error_response("Product not found", HTTPStatus.NOT_FOUND)
        return jsonify(asdict(product)), HTTPStatus.OK
    except Exception as e:
        app.logger.error(f"Error retrieving product {product_id}: {e}")
        return create_error_response("Internal server error", HTTPStatus.INTERNAL_SERVER_ERROR)


@app.route('/cart', methods=['POST'])
def add_to_cart() -> Tuple[Response, int]:
    """
    Add item to shopping cart.
    
    Expected JSON payload:
        {
            "product_id": "string",
            "quantity": positive integer
        }
        
    Returns:
        Created cart item with 201 status, or error response
    """
    try:
        validate_json_content_type()
        data = request.get_json()
        
        if data is None:
            raise BadRequest("Invalid JSON payload")
            
        validate_required_fields(data, ['product_id', 'quantity'])
        
        product_id = data['product_id']
        quantity = data['quantity']
        
        # Type validation
        if not isinstance(product_id, str):
            raise BadRequest("product_id must be a string")
        if not isinstance(quantity, int):
            raise BadRequest("quantity must be an integer")
            
        cart_item = store.add_to_cart(product_id, quantity)
        response = jsonify(asdict(cart_item))
        response.status_code = HTTPStatus.CREATED
        return response
        
    except BadRequest as e:
        return create_error_response(str(e), HTTPStatus.BAD_REQUEST)
    except NotFound as e:
        return create_error_response(str(e), HTTPStatus.NOT_FOUND)
    except ValueError as e:
        return create_error_response(str(e), HTTPStatus.BAD_REQUEST)
    except Exception as e:
        app.logger.error(f"Error adding to cart: {e}")
        return create_error_response("Internal server error", HTTPStatus.INTERNAL_SERVER_ERROR)


@app.route('/cart', methods=['GET'])
def get_cart() -> Tuple[Response, int]:
    """
    Get all items in shopping cart.
    
    Returns:
        JSON array of cart items
    """
    try:
        cart_items = store.get_cart_items()
        return jsonify([asdict(item) for item in cart_items]), HTTPStatus.OK
    except Exception as e:
        app.logger.error(f"Error retrieving cart: {e}")
        return create_error_response("Internal server error", HTTPStatus.INTERNAL_SERVER_ERROR)


@app.route('/cart/<cart_item_id>', methods=['DELETE'])
def remove_from_cart(cart_item_id: str) -> Tuple[Response, int]:
    """
    Remove item from shopping cart.
    
    Args:
        cart_item_id: Unique cart item identifier
        
    Returns:
        204 No Content on success, 404 if not found
    """
    try:
        store.remove_from_cart(cart_item_id)
        return '', HTTPStatus.NO_CONTENT
    except NotFound as e:
        return create_error_response(str(e), HTTPStatus.NOT_FOUND)
    except Exception as e:
        app.logger.error(f"Error removing cart item {cart_item_id}: {e}")
        return create_error_response("Internal server error", HTTPStatus.INTERNAL_SERVER_ERROR)


@app.errorhandler(BadRequest)
def handle_bad_request(e: BadRequest) -> Tuple[Response, int]:
    """Handle 400 Bad Request errors."""
    return create_error_response(str(e), HTTPStatus.BAD_REQUEST)


@app.errorhandler(NotFound)
def handle_not_found(e: NotFound) -> Tuple[Response, int]:
    """Handle 404 Not Found errors."""
    return create_error_response(str(e), HTTPStatus.NOT_FOUND)


@app.errorhandler(InternalServerError)
def handle_internal_error(e: InternalServerError) -> Tuple[Response, int]:
    """Handle 500 Internal Server errors."""
    app.logger.error(f"Internal server error: {e}")
    return create_error_response("Internal server error", HTTPStatus.INTERNAL_SERVER_ERROR)


if __name__ == '__main__':
    # Run with debug=False for production
    app.run(host='0.0.0.0', port=5000, debug=False)