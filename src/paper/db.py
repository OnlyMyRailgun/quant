import sqlite3
import json
import os
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime

CACHE_DIR = Path(".data_cache")
DB_PATH = CACHE_DIR / "paper_trade.db"
FRICTION_FILE = CACHE_DIR / "friction.json"


@contextmanager
def _connect():
    """Yield a connection that commits on success, rolls back on error, and
    always closes. `with sqlite3.connect()` alone does NOT close the handle."""
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

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
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute('SELECT balance FROM wallet')
        return cur.fetchone()[0]

def place_pending_order(symbol: str, action: str, shares: int, theoretical_price: float):
    """Registers a 'thought' trade from the quantitative engine, pending real execution."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO orders (date, symbol, action, target_shares, theoretical_price, status)
            VALUES (?, ?, ?, ?, ?, 'PENDING')
        ''', (date_str, symbol, action, shares, theoretical_price))
        order_id = cur.lastrowid
    print(f"[{date_str}] SIGNAL GENERATED: {action} {shares} shares of {symbol} (Target theoretical price: ¥{theoretical_price:.2f})")
    return order_id

def fetch_pending_orders():
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, date, symbol, action, target_shares, theoretical_price FROM orders WHERE status='PENDING'")
        return cur.fetchall()

def fill_order(order_id: int, actual_price: float, is_synthetic: bool = False):
    """
    Marks an order as executed and updates portfolio and wallet.

    `is_synthetic=True` marks an auto-fill whose price was generated from the
    current friction assumption (theoretical * (1 ± seed_slippage)). Such a fill
    carries no real market information — recalibrating the friction model from it
    would merely re-learn its own seed, so synthetic fills DO NOT feed the loop.
    Only real manual fills (is_synthetic=False) recalibrate friction.json.
    """
    with _connect() as conn:
        cur = conn.cursor()

        cur.execute('SELECT symbol, action, target_shares, theoretical_price FROM orders WHERE id=?', (order_id,))
        order = cur.fetchone()
        if not order:
            print(f"Order ID {order_id} not found.")
            return

        symbol, action, shares, theo_price = order

        # For SELL, clamp to the shares actually held so we can never oversell or
        # sell a position we do not own (which would credit phantom cash).
        if action == 'SELL':
            cur.execute('SELECT shares, avg_price FROM portfolio WHERE symbol=?', (symbol,))
            pos = cur.fetchone()
            held = pos[0] if pos else 0
            if held <= 0:
                print(f"Order {order_id} rejected: SELL {shares} {symbol} but 0 shares held.")
                return
            if shares > held:
                print(f"Order {order_id}: SELL clamped from {shares} to {held} (shares held).")
                shares = held
        else:
            pos = None

        # 1. Feedback Loop Maths: Slippage %
        # If Buying: paying higher than theoretical is positive slippage (bad for us)
        # If Selling: receiving lower than theoretical is positive slippage (bad for us)
        if action == 'BUY':
            slip_pct = (actual_price - theo_price) / theo_price
        else:
            slip_pct = (theo_price - actual_price) / theo_price

        # 2. Update Order (record the actually-executed share count)
        cur.execute('''
            UPDATE orders
            SET actual_price=?, slippage_pct=?, target_shares=?, status='FILLED'
            WHERE id=?
        ''', (actual_price, slip_pct, shares, order_id))

        # 3. Adjust Cash Wallet
        cashflow = -(actual_price * shares) if action == 'BUY' else (actual_price * shares)
        cur.execute('UPDATE wallet SET balance = balance + ?', (cashflow,))

        # 4. Adjust Portfolio
        if action == 'BUY':
            cur.execute('SELECT shares, avg_price FROM portfolio WHERE symbol=?', (symbol,))
            existing = cur.fetchone()
            if existing:
                new_shares = existing[0] + shares
                new_avg = ((existing[0] * existing[1]) + (shares * actual_price)) / new_shares
                cur.execute('UPDATE portfolio SET shares=?, avg_price=? WHERE symbol=?', (new_shares, new_avg, symbol))
            else:
                cur.execute('INSERT INTO portfolio (symbol, shares, avg_price) VALUES (?, ?, ?)', (symbol, shares, actual_price))
        elif action == 'SELL':
            new_shares = pos[0] - shares
            if new_shares <= 0:
                cur.execute('DELETE FROM portfolio WHERE symbol=?', (symbol,))
            else:
                cur.execute('UPDATE portfolio SET shares=? WHERE symbol=?', (new_shares, symbol))
        # `with sqlite3.connect(...)` commits on clean exit, rolls back on exception.

    print(f"Order {order_id} FILLED. {action} {shares} {symbol} @ ¥{actual_price:.2f}.")
    print(f"Slippage Realized: {slip_pct*100:.3f}%")

    if not is_synthetic:
        _recalibrate_friction_model()

def _recalibrate_friction_model():
    """
    The heart of the feedback loop: averages historical out-of-sample slippage
    and overwrites the friction.json so tomorrow's backtests use reality.
    """
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT AVG(slippage_pct) FROM orders WHERE status='FILLED' AND slippage_pct IS NOT NULL")
        avg_slip = cur.fetchone()[0]
    
    if avg_slip is None:
        # Default to standard model
        avg_slip = 0.0005
    else:
        # Heavily cap maximum systemic slippage to prevent wild one-off outliers
        avg_slip = max(0.0001, min(avg_slip, 0.005))
        
    with open(FRICTION_FILE, "w") as f:
        json.dump({"default_slippage_pct": avg_slip}, f)
    
    print(f"🔄 LEARNING LOOP: Engine backtesting slippage recalibrated to: {avg_slip*100:.3f}% base on real executions.")
