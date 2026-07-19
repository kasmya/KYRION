"""FastAPI E-Commerce with JWT, SQLAlchemy, and Pydantic."""
import os, jwt, datetime
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import sessionmaker, Session, declarative_base

DB_URL = "sqlite:///./ecommerce.db"
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
SECRET = "secret"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    role = Column(String, default="user")

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    price = Column(Float)
    stock = Column(Integer)

class CartItem(Base):
    __tablename__ = "cart_items"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer)

Base.metadata.create_all(bind=engine)
app = FastAPI()

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def create_token(user_id: int, role: str) -> str:
    payload = {"sub": str(user_id), "role": role, "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)}
    return jwt.encode(payload, SECRET, algorithm="HS256")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        user = db.query(User).filter(User.id == int(payload["sub"])).first()
        if not user: raise HTTPException(status_code=404, detail="User not found")
        return user
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

class ProductCreate(BaseModel):
    title: str; description: str; price: float; stock: int

@app.post("/register")
def register(username: str, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(400, "Username exists")
    user = User(username=username)
    db.add(user); db.commit(); db.refresh(user)
    return {"token": create_token(user.id, user.role)}

@app.post("/products", dependencies=[Depends(get_current_user)])
def create_product(p: ProductCreate, db: Session = Depends(get_db)):
    prod = Product(**p.dict())
    db.add(prod); db.commit(); db.refresh(prod)
    return prod

@app.get("/products")
def list_products(skip: int = 0, limit: int = 10, q: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Product)
    if q: query = query.filter(Product.title.ilike(f"%{q}%"))
    return query.offset(skip).limit(limit).all()

@app.post("/cart/{product_id}")
def add_to_cart(product_id: int, qty: int = 1, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(CartItem).filter_by(user_id=user.id, product_id=product_id).first()
    if item: item.quantity += qty
    else: db.add(CartItem(user_id=user.id, product_id=product_id, quantity=qty))
    db.commit()
    return {"message": "Added to cart"}

@app.get("/cart")
def view_cart(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(CartItem).filter_by(user_id=user.id).all()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)