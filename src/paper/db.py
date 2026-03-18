import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime

CACHE_DIR = Path(".data_cache")
DB_PATH = CACHE_DIR / "paper_trade.db"
FRICTION_FILE = CACHE_DIR / "friction.json"

def init_db():
    """Initializes the SQLite database tables and seed cash if empty."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Virtual Portfolio Holdings
    cur.execute('''
    CREATE TABLE IF NOT EXISTS portfolio (
        symbol TEXT PRIMARY KEY,
        shares INTEGER DEFAULT 0,
        avg_price REAL DEFAULT 0.0
    )
    ''')
    
    # Virtual Cash Account
    cur.execute('CREATE TABLE IF NOT EXISTS wallet (balance REAL)')
    cur.execute('SELECT COUNT(*) FROM wallet')
    if cur.fetchone()[0] == 0:
        cur.execute('INSERT INTO wallet (balance) VALUES (1000000.0)') # Start with 1 million JPY
        
    # Transaction/Order Log for Feedback Loop
    cur.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        symbol TEXT,
        action TEXT,
        target_shares INTEGER,
        theoretical_price REAL,
        actual_price REAL,
        slippage_pct REAL,
        status TEXT
    )
    ''')
    conn.commit()
    conn.close()

    # Initialize default historical friction map if it doesn't exist
    if not os.path.exists(FRICTION_FILE):
        with open(FRICTION_FILE, "w") as f:
            json.dump({"default_slippage_pct": 0.0005}, f)

def get_wallet_balance() -> float:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT balance FROM wallet')
    balance = cur.fetchone()[0]
    conn.close()
    return balance

def place_pending_order(symbol: str, action: str, shares: int, theoretical_price: float):
    """Registers a 'thought' trade from the quantitative engine, pending real execution."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    date_str = datetime.now().strftime("%Y-%m-%d")
    cur.execute('''
        INSERT INTO orders (date, symbol, action, target_shares, theoretical_price, status)
        VALUES (?, ?, ?, ?, ?, 'PENDING')
    ''', (date_str, symbol, action, shares, theoretical_price))
    conn.commit()
    conn.close()
    print(f"[{date_str}] SIGNAL GENERATED: {action} {shares} shares of {symbol} (Target theoretical price: ¥{theoretical_price:.2f})")

def fetch_pending_orders():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, date, symbol, action, target_shares, theoretical_price FROM orders WHERE status='PENDING'")
    orders = cur.fetchall()
    conn.close()
    return orders

def fill_order(order_id: int, actual_price: float):
    """
    Marks an order as executed at the manual broker price.
    Automatically calculates slippage and updates portfolio and wallet.
    Triggers the feedback loop down to the engine.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute('SELECT symbol, action, target_shares, theoretical_price FROM orders WHERE id=?', (order_id,))
    order = cur.fetchone()
    if not order:
        print(f"Order ID {order_id} not found.")
        return
        
    symbol, action, shares, theo_price = order
    
    # 1. Feedback Loop Maths: Slippage %
    # If Buying: paying higher than theoretical is positive slippage (bad for us)
    # If Selling: receiving lower than theoretical is positive slippage (bad for us)
    if action == 'BUY':
        slip_pct = (actual_price - theo_price) / theo_price
    else:
        slip_pct = (theo_price - actual_price) / theo_price
        
    # 2. Update Order
    cur.execute('''
        UPDATE orders 
        SET actual_price=?, slippage_pct=?, status='FILLED' 
        WHERE id=?
    ''', (actual_price, slip_pct, order_id))
    
    # 3. Adjust Cash Wallet
    cashflow = -(actual_price * shares) if action == 'BUY' else (actual_price * shares)
    cur.execute('UPDATE wallet SET balance = balance + ?', (cashflow,))
    
    # 4. Adjust Portfolio
    cur.execute('SELECT shares, avg_price FROM portfolio WHERE symbol=?', (symbol,))
    pos = cur.fetchone()
    
    if action == 'BUY':
        if pos:
            new_shares = pos[0] + shares
            new_avg = ((pos[0] * pos[1]) + (shares * actual_price)) / new_shares
            cur.execute('UPDATE portfolio SET shares=?, avg_price=? WHERE symbol=?', (new_shares, new_avg, symbol))
        else:
            cur.execute('INSERT INTO portfolio (symbol, shares, avg_price) VALUES (?, ?, ?)', (symbol, shares, actual_price))
    elif action == 'SELL':
        if pos:
            new_shares = pos[0] - shares
            if new_shares <= 0:
                cur.execute('DELETE FROM portfolio WHERE symbol=?', (symbol,))
            else:
                cur.execute('UPDATE portfolio SET shares=? WHERE symbol=?', (new_shares, symbol))

    conn.commit()
    conn.close()
    
    print(f"Order {order_id} FILLED. {action} {shares} {symbol} @ ¥{actual_price:.2f}.")
    print(f"Slippage Realized: {slip_pct*100:.3f}%")
    
    _recalibrate_friction_model()

def _recalibrate_friction_model():
    """
    The heart of the feedback loop: averages historical out-of-sample slippage
    and overwrites the friction.json so tomorrow's backtests use reality.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT AVG(slippage_pct) FROM orders WHERE status='FILLED' AND slippage_pct IS NOT NULL")
    avg_slip = cur.fetchone()[0]
    conn.close()
    
    if avg_slip is None:
        # Default to standard model
        avg_slip = 0.0005
    else:
        # Heavily cap maximum systemic slippage to prevent wild one-off outliers
        avg_slip = max(0.0001, min(avg_slip, 0.005))
        
    with open(FRICTION_FILE, "w") as f:
        json.dump({"default_slippage_pct": avg_slip}, f)
    
    print(f"🔄 LEARNING LOOP: Engine backtesting slippage recalibrated to: {avg_slip*100:.3f}% base on real executions.")
