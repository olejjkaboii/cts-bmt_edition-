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
    amount_rub = Column(Float)  # Amount in RUB at creation time
    rate_at_creation = Column(Float)  # Rate at order creation
    currency = Column(String)
    bank = Column(String)
    phone = Column(String)
    deposit_address = Column(String)
    status = Column(String, default="pending")
    order_type = Column(String, default="buy")

Base.metadata.create_all(bind=engine)

# Migration: Add currency column if it doesn't exist
try:
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(orders)"))
        columns = [row[1] for row in result.fetchall()]
        if 'currency' not in columns:
            conn.execute(text("ALTER TABLE orders ADD COLUMN currency TEXT"))
            conn.execute(text("UPDATE orders SET currency = 'RUB'"))
            conn.commit()
        if 'order_type' not in columns:
            conn.execute(text("ALTER TABLE orders ADD COLUMN order_type TEXT"))
            conn.execute(text("UPDATE orders SET order_type = 'buy'"))
            conn.commit()
        if 'amount_rub' not in columns:
            conn.execute(text("ALTER TABLE orders ADD COLUMN amount_rub REAL"))
            conn.commit()
        if 'rate_at_creation' not in columns:
            conn.execute(text("ALTER TABLE orders ADD COLUMN rate_at_creation REAL"))
            conn.commit()
        # Migration for support_tickets
        result2 = conn.execute(text("PRAGMA table_info(support_tickets)"))
        columns2 = [row[1] for row in result2.fetchall()]
        if 'status' not in columns2:
            conn.execute(text("ALTER TABLE support_tickets ADD COLUMN status TEXT DEFAULT 'pending'"))
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

class SupportRequest(BaseModel):
    deposit_address: Optional[str] = None
    order_id: Optional[str] = None
    email: str
    message: str

class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.now)
    deposit_address = Column(String, nullable=True)
    order_id = Column(String, nullable=True)
    email = Column(String)
    message = Column(String)
    status = Column(String, default="pending")

Base.metadata.create_all(bind=engine)

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

@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    template_path = os.path.join(BASE_DIR, "templates", "about.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/rules", response_class=HTMLResponse)
async def rules_page(request: Request):
    template_path = os.path.join(BASE_DIR, "templates", "rules.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/support", response_class=HTMLResponse)
async def support_page(request: Request):
    template_path = os.path.join(BASE_DIR, "templates", "support.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/admin/support", response_class=HTMLResponse)
async def admin_support_page(request: Request):
    template_path = os.path.join(BASE_DIR, "templates", "admin_support.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/support")
async def submit_support(ticket: SupportRequest, db: Session = Depends(get_db)):
    new_ticket = SupportTicket(
        deposit_address=ticket.deposit_address,
        order_id=ticket.order_id,
        email=ticket.email,
        message=ticket.message
    )
    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)
    logger.info(f"Support ticket created: {new_ticket.id}")
    return {"status": "ok", "ticket_id": new_ticket.id}

@app.get("/api/support")
async def get_support_tickets(db: Session = Depends(get_db)):
    tickets = db.query(SupportTicket).order_by(SupportTicket.created_at.desc()).all()
    return [{
        "id": t.id,
        "created_at": t.created_at.isoformat(),
        "deposit_address": t.deposit_address,
        "order_id": t.order_id,
        "email": t.email,
        "message": t.message,
        "status": t.status
    } for t in tickets]

@app.patch("/api/support/{ticket_id}")
async def update_support_ticket(ticket_id: int, update: OrderUpdate, db: Session = Depends(get_db)):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Обращение не найдено")
    if update.status not in ["pending", "rejected", "resolved"]:
        raise HTTPException(status_code=400, detail="Неверный статус")
    ticket.status = update.status  # type: ignore
    db.commit()
    return {"status": "success", "new_status": ticket.status}

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
    
    # Get rate for RUB conversion
    rate = None
    amount_rub = None
    try:
        import requests
        url = f'https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=rub'
        response = requests.get(url, timeout=5)
        data = response.json()
        if 'tether' in data and 'rub' in data['tether']:
            rate = data['tether']['rub']
            amount_rub = order.amount_usdt * rate
    except Exception as e:
        logger.warning(f"Could not fetch rate: {e}")
    
    new_order = Order(
        order_id=order_id,
        amount_usdt=order.amount_usdt,
        amount_rub=amount_rub,
        rate_at_creation=rate,
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
        "amount_rub": o.amount_rub,
        "rate_at_creation": o.rate_at_creation,
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
        
        # Try CoinGecko first
        try:
            currency_lower = currency.lower()
            currency_map = {
                'rub': 'rub',
                'usd': 'usd',
                'eur': 'eur',
                'gbp': 'gbp',
                'kzt': 'kzt'
            }
            
            cg_currency = currency_map.get(currency_lower, currency_lower)
            
            # Get price of USDT in target currency
            url = f'https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies={cg_currency}'
            response = requests.get(url, timeout=5)
            data = response.json()
            
            if 'tether' in data and cg_currency in data['tether']:
                rate = data['tether'][cg_currency]
                return {"rate": rate, "currency": currency, "source": "CoinGecko"}
        except Exception as cg_error:
            logger.warning(f"CoinGecko API failed: {cg_error}")
        
        # Fallback to Rapira for RUB
        if currency.upper() == 'RUB':
            try:
                url = 'https://api.rapira.net/open/market/rates_xml'
                headers = {'Accept': 'application/xml'}
                response = requests.get(url, headers=headers, timeout=5)
                response.raise_for_status()
                
                from xml.etree import ElementTree as ET
                root = ET.fromstring(response.content)
                for item in root.findall('item'):
                    fr_elem = item.find('from')
                    to_elem = item.find('to')
                    out_elem = item.find('out')
                    if fr_elem is not None and to_elem is not None and out_elem is not None:
                        fr = fr_elem.text
                        to = to_elem.text
                        out = out_elem.text
                        if fr == 'USDT' and to == 'RUB' and out is not None:
                            return {"rate": float(out), "currency": currency, "source": "Rapira"}
            except Exception as rapira_error:
                logger.warning(f"Rapira API failed: {rapira_error}")
        
        # Final fallback: hardcoded rates
        hardcoded_rates = {
            'RUB': 75.0,  # Example rate
            'USD': 1.0,
            'EUR': 0.92,
            'GBP': 0.79,
            'KZT': 450.0
        }
        
        if currency.upper() in hardcoded_rates:
            return {"rate": hardcoded_rates[currency.upper()], "currency": currency, "source": "fallback"}
        
        return {"error": f"Не удалось получить курс для {currency.upper()}"}
                
    except Exception as e:
        logger.error(f"Rate fetch error: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

