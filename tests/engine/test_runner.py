import pytest
import pandas as pd
from src.engine.runner import run_backtest
from src.strategies.sma_crossover import SmaCross

def test_run_backtest_execution():
    # Create fake price data
    dates = pd.date_range("2023-01-01", periods=50)
    data = pd.DataFrame({
        'Open': range(100, 150),
        'High': range(101, 151),
        'Low': range(99, 149),
        'Close': range(100, 150),
        'Volume': [1000] * 50
    }, index=dates)
    
    # Run backtest
    results = run_backtest(data, SmaCross, initial_cash=1000000.0)
    
    # Verify results dict contains metrics
    assert "metrics" in results
    assert "final_value" in results["metrics"]
    assert results["metrics"]["final_value"] > 0
