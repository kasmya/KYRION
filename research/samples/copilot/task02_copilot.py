"""
E-Commerce API using FastAPI, SQLAlchemy, and JWT.
Features:
- Product CRUD (admin only)
- Shopping cart (add/remove/view)
- Order processing (checkout, order history)
- JWT authentication with user/admin roles
- Search with filters and pagination
"""

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime, timedelta
import jwt
import logging
import bcrypt

# Configure logging
logging.basicConfig(level=logging.INFO)

# Database setup
DATABASE_URL = "sqlite:///./ecommerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# JWT setup
SECRET_KEY = "supersecretjwt"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# Database Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)
    orders = relationship("Order", back_populates="user")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(String, default=datetime.utcnow)
    items = relationship("OrderItem", back_populates="order")
    user = relationship("User", back_populates="orders")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, nullable=False)
    order = relationship("Order", back_populates="items")


# Pydantic Schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    is_admin: Optional[bool] = False


class ProductCreate(BaseModel):
    title: str
    description: Optional[str]
    price: float
    stock: int


class ProductOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    price: float
    stock: int

    class Config:
        orm_mode = True


class OrderItemOut(BaseModel):
    product_id: int
    quantity: int

    class Config:
        orm_mode = True


class OrderOut(BaseModel):
    id: int
    created_at: str
    items: List[OrderItemOut]

    class Config:
        orm_mode = True


# Utility Functions
def get_db():
    """Provide database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generate JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """Retrieve current user from JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


# FastAPI app
app = FastAPI(title="E-Commerce API")


@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    """Register a new user."""
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_pw = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt()).decode()
    db_user = User(email=user.email, password_hash=hashed_pw, is_admin=user.is_admin)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"msg": "User registered successfully"}


@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login and get JWT token."""
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not bcrypt.checkpw(form_data.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/products", response_model=ProductOut)
def create_product(product: ProductCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create a new product (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    db_product = Product(**product.dict())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


@app.get("/products", response_model=List[ProductOut])
def list_products(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 10,
    search: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
):
    """List products with search and filters."""
    query = db.query(Product)
    if search:
        query = query.filter(Product.title.contains(search))
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
    return query.offset(skip).limit(limit).all()


@app.post("/cart/add/{product_id}")
def add_to_cart(product_id: int, quantity: int = 1, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Add product to cart (stored in session orders)."""
    product = db.query(Product).get(product_id)
    if not product or product.stock < quantity:
        raise HTTPException(status_code=400, detail="Product unavailable")
    order = Order(user_id=current_user.id)
    db.add(order)
    db.commit()
    db.refresh(order)
    order_item = OrderItem(order_id=order.id, product_id=product_id, quantity=quantity)
    db.add(order_item)
    db.commit()
    return {"msg": "Added to cart", "order_id": order.id}


@app.post("/checkout/{order_id}")
def checkout(order_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Checkout an order."""
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == current_user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    for item in order.items:
        product = db.query(Product).get(item.product_id)
        if product.stock < item.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {product.title}")
        product.stock -= item.quantity
    db.commit()
    return {"msg": "Order checked out successfully"}


@app.get("/orders", response_model=List[OrderOut])
def order_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get user's order history."""
    return db.query(Order).filter(Order.user_id == current_user.id).all()


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

