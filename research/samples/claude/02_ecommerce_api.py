"""
### Task 2: E-Commerce API (FastAPI)

A FastAPI-based e-commerce backend with product CRUD, a shopping cart,
order checkout/history, JWT authentication with user/admin roles, an
admin-only product management surface, and search with filters and
pagination.

Requirements:
    pip install fastapi "uvicorn[standard]" sqlalchemy "python-jose[cryptography]" passlib[bcrypt] pydantic

Run:
    uvicorn 02_ecommerce_api:app --host 0.0.0.0 --port 8002
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import (
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ecommerce_api")

SECRET_KEY = "change-this-secret-in-production"  # nosec: use env var / secrets manager
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

engine = create_engine("sqlite:///ecommerce.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.USER, nullable=False)


class ProductModel(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(String(2000), nullable=True)
    price = Column(Float, nullable=False)
    stock = Column(Integer, nullable=False, default=0)


class CartItemModel(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    product = relationship("ProductModel")


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    total_amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    items = relationship("OrderItemModel", backref="order")


class OrderItemModel(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)


class ProductCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    price: float = Field(..., gt=0)
    stock: int = Field(..., ge=0)


class ProductOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    price: float
    stock: int

    class Config:
        from_attributes = True


class CartItemIn(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)


class CartItemOut(BaseModel):
    product_id: int
    title: str
    quantity: int
    unit_price: float
    subtotal: float


class OrderOut(BaseModel):
    id: int
    total_amount: float
    created_at: datetime
    item_count: int


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


def get_db():
    """FastAPI dependency yielding a scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: timedelta) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + expires_delta
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> UserModel:
    """Decodes the JWT and returns the associated user, raising 401 on failure."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError as exc:
        logger.warning("JWT decode failed: %s", exc)
        raise credentials_exception from exc

    user = db.query(UserModel).filter(UserModel.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user


def require_admin(user: UserModel = Depends(get_current_user)) -> UserModel:
    """Dependency ensuring the current user has admin privileges."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin privileges required")
    return user


app = FastAPI(title="E-Commerce API", version="1.0.0")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    logger.info("E-Commerce API started, database initialized")


@app.post("/register", response_model=Token, status_code=201)
def register(email: str, password: str, db: Session = Depends(get_db)):
    """Registers a new user account with the default 'user' role."""
    if db.query(UserModel).filter(UserModel.email == email).first():
        raise HTTPException(status_code=409, detail="email already registered")

    user = UserModel(email=email, hashed_password=hash_password(password), role=UserRole.USER)
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        {"sub": str(user.id), "role": user.role.value},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=token)


@app.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2-compatible token endpoint (email is submitted as 'username')."""
    user = db.query(UserModel).filter(UserModel.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="incorrect email or password")

    token = create_access_token(
        {"sub": str(user.id), "role": user.role.value},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=token)


@app.post("/admin/products", response_model=ProductOut, status_code=201)
def create_product(
    product: ProductCreate, db: Session = Depends(get_db), _admin: UserModel = Depends(require_admin)
):
    """Creates a new product. Admin only."""
    db_product = ProductModel(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    logger.info("Admin created product '%s' (id=%s)", db_product.title, db_product.id)
    return db_product


@app.put("/admin/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    product: ProductCreate,
    db: Session = Depends(get_db),
    _admin: UserModel = Depends(require_admin),
):
    """Updates an existing product. Admin only."""
    db_product = db.query(ProductModel).filter(ProductModel.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="product not found")

    for field, value in product.model_dump().items():
        setattr(db_product, field, value)
    db.commit()
    db.refresh(db_product)
    return db_product


@app.delete("/admin/products/{product_id}", status_code=204)
def delete_product(
    product_id: int, db: Session = Depends(get_db), _admin: UserModel = Depends(require_admin)
):
    """Deletes a product. Admin only."""
    db_product = db.query(ProductModel).filter(ProductModel.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="product not found")
    db.delete(db_product)
    db.commit()


@app.get("/products", response_model=List[ProductOut])
def search_products(
    q: Optional[str] = Query(default=None, description="Search term for product title"),
    min_price: Optional[float] = Query(default=None, ge=0),
    max_price: Optional[float] = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Searches products with optional text/price filters and pagination."""
    query = db.query(ProductModel)
    if q:
        query = query.filter(ProductModel.title.ilike(f"%{q}%"))
    if min_price is not None:
        query = query.filter(ProductModel.price >= min_price)
    if max_price is not None:
        query = query.filter(ProductModel.price <= max_price)

    offset = (page - 1) * page_size
    return query.offset(offset).limit(page_size).all()


@app.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Fetches a single product by id."""
    product = db.query(ProductModel).filter(ProductModel.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="product not found")
    return product


@app.post("/cart/items", status_code=201)
def add_to_cart(
    item: CartItemIn, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)
):
    """Adds a product to the current user's cart, or increments quantity if present."""
    product = db.query(ProductModel).filter(ProductModel.id == item.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="product not found")
    if product.stock < item.quantity:
        raise HTTPException(status_code=400, detail="insufficient stock")

    existing = (
        db.query(CartItemModel)
        .filter(CartItemModel.user_id == user.id, CartItemModel.product_id == item.product_id)
        .first()
    )
    if existing:
        existing.quantity += item.quantity
    else:
        db.add(CartItemModel(user_id=user.id, product_id=item.product_id, quantity=item.quantity))
    db.commit()
    return {"message": "added to cart"}


@app.delete("/cart/items/{product_id}")
def remove_from_cart(
    product_id: int, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)
):
    """Removes a product entirely from the current user's cart."""
    item = (
        db.query(CartItemModel)
        .filter(CartItemModel.user_id == user.id, CartItemModel.product_id == product_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="item not in cart")
    db.delete(item)
    db.commit()
    return {"message": "removed from cart"}


@app.get("/cart", response_model=List[CartItemOut])
def view_cart(db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    """Returns the current user's cart contents with computed subtotals."""
    items = db.query(CartItemModel).filter(CartItemModel.user_id == user.id).all()
    return [
        CartItemOut(
            product_id=i.product.id,
            title=i.product.title,
            quantity=i.quantity,
            unit_price=i.product.price,
            subtotal=round(i.product.price * i.quantity, 2),
        )
        for i in items
    ]


@app.post("/orders/checkout", response_model=OrderOut, status_code=201)
def checkout(db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    """Converts the current cart into an order, decrementing stock and clearing the cart."""
    cart_items = db.query(CartItemModel).filter(CartItemModel.user_id == user.id).all()
    if not cart_items:
        raise HTTPException(status_code=400, detail="cart is empty")

    for item in cart_items:
        if item.product.stock < item.quantity:
            raise HTTPException(
                status_code=400, detail=f"insufficient stock for '{item.product.title}'"
            )

    total = sum(item.product.price * item.quantity for item in cart_items)
    order = OrderModel(user_id=user.id, total_amount=round(total, 2))
    db.add(order)
    db.flush()  # populate order.id before creating order items

    for item in cart_items:
        db.add(
            OrderItemModel(
                order_id=order.id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.product.price,
            )
        )
        item.product.stock -= item.quantity
        db.delete(item)

    db.commit()
    db.refresh(order)
    logger.info("User %s checked out order %s for %.2f", user.id, order.id, order.total_amount)
    return OrderOut(
        id=order.id,
        total_amount=order.total_amount,
        created_at=order.created_at,
        item_count=len(cart_items),
    )


@app.get("/orders", response_model=List[OrderOut])
def order_history(db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    """Returns the current user's order history."""
    orders = db.query(OrderModel).filter(OrderModel.user_id == user.id).all()
    return [
        OrderOut(
            id=o.id, total_amount=o.total_amount, created_at=o.created_at, item_count=len(o.items)
        )
        for o in orders
    ]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
