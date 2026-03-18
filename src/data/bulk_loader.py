import time
import pandas as pd
from pathlib import Path
from src.data.yfinance_loader import fetch_daily_data

CACHE_DIR = Path(".data_cache")

def _get_cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol}.parquet"

def fetch_universe(symbols: list[str], start_date: str, end_date: str) -> dict[str, pd.DataFrame]:
    """
    Fetches daily data for multiple symbols.
    Checks local parquet cache first. If MISS, delegates to yfinance_loader and caches.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    
    for symbol in symbols:
        cache_file = _get_cache_path(symbol)
        
        # Simplified cache hit verification
        if cache_file.exists():
            print(f"[CACHE HIT] Loading {symbol} from disk...")
            df = pd.read_parquet(cache_file)
            results[symbol] = df
        else:
            print(f"[CACHE MISS] Downloading {symbol} from Yahoo Finance...")
            df = fetch_daily_data(symbol, start_date, end_date)
            
            if not df.empty:
                df.to_parquet(cache_file)
                results[symbol] = df
            
            # Anti-ban delay: sleep half a second between actual hits to Yahoo
            time.sleep(0.5)

    return results
