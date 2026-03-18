import json
import backtrader as bt
from pathlib import Path

FRICTION_FILE = Path(".data_cache/friction.json")

def load_live_slippage() -> float:
    """
    Reads the slippage rate calibrated by the Paper Trader's Feedback Loop.
    If the file doesn't exist, returns the conservative default.
    
    This is the core of the 'Anti-Fragile Feedback Loop':
    As the paper trader records real execution slippages, this function
    allows the backtesting engine to self-correct its assumptions.
    """
    if FRICTION_FILE.exists():
        try:
            with open(FRICTION_FILE, "r") as f:
                data = json.load(f)
                rate = data.get("default_slippage_pct", 0.0005)
                print(f"[Engine] Loaded live-calibrated slippage from paper trader feedback: {rate*100:.4f}%")
                return rate
        except (json.JSONDecodeError, KeyError):
            pass
    return 0.0005  # Naive theoretical default


class JapanStockCommission(bt.CommInfoBase):
    """
    Custom Commission model simulating Japanese Stock Trading friction.
    Assumes percentage-based commission.
    
    Slippage Rate: Dynamically loaded from .data_cache/friction.json if available.
    This file is updated automatically by the Paper Trader Feedback Loop whenever 
    a real-world order is filled, ensuring backtests reflect your actual execution quality.
    """
    params = (
        ('commission', 0.001),  # 0.1% brokerage commission (Tokyo Stock Exchange standard)
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_FIXED),
    )

    def _getcommission(self, size, price, pseudoexec):
        """Calculate commission (brokerage fee only — slippage is set separately by runner.py)."""
        return abs(size) * price * self.p.commission
