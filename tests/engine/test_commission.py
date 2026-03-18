import pytest
from src.engine.commission import JapanStockCommission

def test_japan_stock_commission():
    # Set a fixed commission rate, e.g., 0.1% for Interactive Brokers / Rakuten
    comm_model = JapanStockCommission(commission=0.001)
    
    # price=1000, size=100 -> value = 100,000. Commission = 100
    fee = comm_model._getcommission(size=100, price=1000, pseudoexec=1000)
    
    assert fee == 100.0
