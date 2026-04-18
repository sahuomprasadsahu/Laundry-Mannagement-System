# ================== IMPORTS ==================
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List
import uuid

# ================== DATABASE ==================
from sqlalchemy import create_engine, Column, String, Integer, Float, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = "sqlite:///./laundry.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ================== AUTH ==================
from jose import JWTError, jwt
from datetime import datetime, timedelta

SECRET_KEY = "supersecret123"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

security = HTTPBearer()

# 🔥 SIMPLE LOGIN (NO bcrypt → NO ERROR)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# ================== APP ==================
app = FastAPI(title="Laundry System FINAL")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================== DATABASE TABLES ==================

class OrderTable(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    customer_name = Column(String)
    phone_number = Column(String)
    status = Column(String)
    total_bill = Column(Float)

    garments = relationship("GarmentTable", back_populates="order", cascade="all, delete")


class GarmentTable(Base):
    __tablename__ = "garments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, ForeignKey("orders.id"))
    name = Column(String)
    quantity = Column(Integer)
    price_per_item = Column(Float)

    order = relationship("OrderTable", back_populates="garments")


Base.metadata.create_all(bind=engine)

# ================== MODELS ==================

class Garment(BaseModel):
    name: str
    quantity: int
    price_per_item: float

class OrderCreate(BaseModel):
    customer_name: str
    phone_number: str
    garments: List[Garment]

class LoginData(BaseModel):
    username: str
    password: str

# ================== AUTH FUNCTIONS ==================

def create_token(data: dict):
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ================== FRONTEND ==================

@app.get("/")
def home():
    return FileResponse("templates/index.html")

# ================== LOGIN ==================

@app.post("/login")
def login(data: LoginData):
    # ✅ SIMPLE LOGIN FIXED
    if data.username != ADMIN_USERNAME or data.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({"sub": data.username})
    return {"access_token": token}

# ================== CREATE ORDER ==================

@app.post("/orders")
def create_order(order_data: OrderCreate, user=Depends(verify_token)):

    db = SessionLocal()

    order_id = str(uuid.uuid4())[:8].upper()

    total = sum(g.quantity * g.price_per_item for g in order_data.garments)

    order = OrderTable(
        id=order_id,
        customer_name=order_data.customer_name,
        phone_number=order_data.phone_number,
        status="RECEIVED",
        total_bill=total
    )

    db.add(order)
    db.commit()

    for g in order_data.garments:
        db.add(GarmentTable(
            order_id=order_id,
            name=g.name,
            quantity=g.quantity,
            price_per_item=g.price_per_item
        ))

    db.commit()

    return {"id": order_id}

# ================== GET ORDERS ==================

@app.get("/orders")
def get_orders(user=Depends(verify_token)):
    db = SessionLocal()
    orders = db.query(OrderTable).all()

    result = []

    for o in orders:
        result.append({
            "id": o.id,
            "customer_name": o.customer_name,
            "status": o.status,
            "total_bill": o.total_bill
        })

    return result

# ================== UPDATE STATUS ==================

@app.patch("/orders/{order_id}/status")
def update_status(order_id: str, user=Depends(verify_token)):
    db = SessionLocal()

    order = db.query(OrderTable).filter(OrderTable.id == order_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Not found")

    flow = ["RECEIVED", "PROCESSING", "READY", "DELIVERED"]

    idx = flow.index(order.status)

    if idx < len(flow) - 1:
        order.status = flow[idx + 1]
        db.commit()
        return {"status": order.status}

    raise HTTPException(status_code=400, detail="Already delivered")

# ================== DELETE ==================

@app.delete("/orders/{order_id}")
def delete_order(order_id: str, user=Depends(verify_token)):
    db = SessionLocal()

    order = db.query(OrderTable).filter(OrderTable.id == order_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Not found")

    db.delete(order)
    db.commit()

    return {"message": "Deleted"}

# ================== DASHBOARD ==================

@app.get("/dashboard")
def dashboard(user=Depends(verify_token)):
    db = SessionLocal()

    orders = db.query(OrderTable).all()

    total_revenue = sum(o.total_bill for o in orders)

    status_counts = {
        "RECEIVED": 0,
        "PROCESSING": 0,
        "READY": 0,
        "DELIVERED": 0
    }

    for o in orders:
        status_counts[o.status] += 1

    return {
        "total_orders": len(orders),
        "total_revenue": total_revenue,
        "orders_per_status": status_counts
    }