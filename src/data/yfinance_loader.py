import yfinance as yf
import pandas as pd

def fetch_daily_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetches daily historical data from Yahoo Finance."""
    data = yf.download(ticker, start=start_date, end=end_date, progress=False)
    
    # Handle yfinance multi-index columns if they exist
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
        
    return data
