import os
import uuid
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, text
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import List, Optional
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Log environment variables for debugging
logger.info(f"TRON_SEED set: {bool(os.getenv('TRON_SEED'))}")
logger.info(f"TRON_PRIVATE_KEY set: {bool(os.getenv('TRON_PRIVATE_KEY'))}")
logger.info(f"TRON_ADDRESS set: {bool(os.getenv('TRON_ADDRESS'))}")

# Currency and bank configuration
CURRENCY_BANKS_CONFIG = {
    "RUB": ["Сбербанк", "Тинькофф", "Альфа-Банк", "ВТБ", "Райффайзен"],
    "USD": ["Chase Bank", "Bank of America", "Wells Fargo", "Citi", "Capital One"],
    "EUR": ["Deutsche Bank", "BNP Paribas", "Société Générale", "ING", "Unicredit"],
    "GBP": ["Barclays", "HSBC", "Lloyds", "NatWest", "Santander UK"],
    "KZT": ["Halyk Bank", "Kaspi Bank", "ForteBank", "Bank CenterCredit", "Sberbank KZ"]
}

app = FastAPI(title="Crypto Exchange API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if os.getenv("RENDER"):
    try:
        DB_PATH = "/var/data/orders.db"
        os.makedirs("/var/data", exist_ok=True)
    except:
        DB_PATH = os.path.join(BASE_DIR, "orders.db")
else:
    DB_PATH = os.path.join(BASE_DIR, "orders.db")

DATABASE_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.now)
    amount_usdt = Column(Float)
    currency = Column(String)  # New field for target currency
    bank = Column(String)
    phone = Column(String)
    deposit_address = Column(String)
    status = Column(String, default="pending")
    order_type = Column(String, default="buy")  # "buy" or "sell"

Base.metadata.create_all(bind=engine)

# Migration: Add currency column if it doesn't exist
try:
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(orders)"))
        columns = [row[1] for row in result.fetchall()]
        if 'currency' not in columns:
            conn.execute(text("ALTER TABLE orders ADD COLUMN currency TEXT"))
            # Set default currency for existing orders
            conn.execute(text("UPDATE orders SET currency = 'RUB'"))
            conn.commit()
        if 'order_type' not in columns:
            conn.execute(text("ALTER TABLE orders ADD COLUMN order_type TEXT"))
            # Set default order_type for existing orders (assume they are buys)
            conn.execute(text("UPDATE orders SET order_type = 'buy'"))
            conn.commit()
except Exception as e:
    logger.error(f"Migration error: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class OrderCreate(BaseModel):
    amount_usdt: float
    currency: str
    bank: str
    phone: str
    order_type: str = "buy"  # Default to "buy"

class OrderUpdate(BaseModel):
    status: str

@app.get("/", response_class=HTMLResponse)
async def payment_page(request: Request):
    template_path = os.path.join(BASE_DIR, "templates", "payment.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/sell", response_class=HTMLResponse)
async def sell_page(request: Request):
    template_path = os.path.join(BASE_DIR, "templates", "sell.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    template_path = os.path.join(BASE_DIR, "templates", "admin.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/orders")
async def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    logger.info(f"Creating order: {order}")
    
    order_id = str(uuid.uuid4())[:8].upper()
    
    # Получаем количество заказов для индекса
    order_count = db.query(Order).count()
    address_index = order_count
    
    try:
        from tron_wallet import create_trc20_address
        deposit_address = create_trc20_address(address_index)
        logger.info(f"Deposit address: {deposit_address}")
        
        if not deposit_address:
            # Fallback: Generate a dummy address if TRON credentials are not set
            logger.warning("No TRON credentials set, using dummy address")
            deposit_address = f"TR{str(uuid.uuid4()).replace('-', '')[:33]}"
    except Exception as e:
        logger.error(f"Error creating address: {e}")
        # Fallback: Generate a dummy address
        deposit_address = f"TR{str(uuid.uuid4()).replace('-', '')[:33]}"
        logger.warning(f"Using dummy address due to error: {deposit_address}")
    
    new_order = Order(
        order_id=order_id,
        amount_usdt=order.amount_usdt,
        currency=order.currency,
        bank=order.bank,
        phone=order.phone,
        deposit_address=deposit_address,
        status="pending",
        order_type=order.order_type
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)
    
    return {
        "order_id": new_order.order_id,
        "deposit_address": new_order.deposit_address,
        "amount_usdt": new_order.amount_usdt,
        "status": new_order.status,
        "created_at": new_order.created_at.isoformat()
    }

@app.get("/api/orders", response_model=List[dict])
async def get_orders(db: Session = Depends(get_db)):
    orders = db.query(Order).order_by(Order.created_at.desc()).all()
    return [{
        "id": o.id,
        "order_id": o.order_id,
        "created_at": o.created_at.isoformat(),
        "amount_usdt": o.amount_usdt,
        "currency": o.currency,
        "bank": o.bank,
        "phone": o.phone,
        "deposit_address": o.deposit_address,
        "status": o.status,
        "order_type": o.order_type
    } for o in orders]

@app.patch("/api/orders/{order_id}")
async def update_order_status(order_id: str, update: OrderUpdate, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    
    if update.status not in ["pending", "paid", "canceled"]:
        raise HTTPException(status_code=400, detail="Неверный статус")
    
    # Set status - SQLAlchemy handles the attribute assignment
    order.status = update.status  # type: ignore
    db.commit()
    return {"status": "success", "new_status": order.status}

@app.get("/api/currencies")
async def get_currencies():
    """Get available currencies and their banks"""
    return {
        "currencies": list(CURRENCY_BANKS_CONFIG.keys()),
        "banks": CURRENCY_BANKS_CONFIG
    }

@app.get("/api/rate")
async def get_usdt_rate(currency: str = "RUB"):
    try:
        import requests
        from xml.etree import ElementTree as ET
        
        url = 'https://api.rapira.net/open/market/rates_xml'
        headers = {'Accept': 'application/xml'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        for item in root.findall('item'):
            fr_elem = item.find('from')
            to_elem = item.find('to')
            out_elem = item.find('out')
            if fr_elem is not None and to_elem is not None and out_elem is not None:
                fr = fr_elem.text
                to = to_elem.text
                out = out_elem.text
                if fr == 'USDT' and to == currency.upper() and out is not None:
                    return {"rate": float(out), "currency": currency, "source": "Rapira"}
        
        return {"error": f"Пара USDT/{currency.upper()} не найдена"}
    except Exception as e:
        logger.error(f"Rate fetch error: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

