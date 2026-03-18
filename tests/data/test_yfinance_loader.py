import pytest
import pandas as pd
from src.data.yfinance_loader import fetch_daily_data

def test_fetch_daily_data_returns_dataframe():
    # Use a well-known ticker like '7203.T' (Toyota) or 'AAPL'
    df = fetch_daily_data("AAPL", start_date="2023-01-01", end_date="2023-01-10")
    
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    # Backtrader expects specific column names
    expected_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    for col in expected_cols:
        assert col in df.columns
