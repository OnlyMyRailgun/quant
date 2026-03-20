import time
import pandas as pd
from pathlib import Path
from src.data.yfinance_loader import fetch_daily_data

CACHE_DIR = Path(".data_cache")

def _get_cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol}.parquet"


def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.index = pd.to_datetime(normalized.index).tz_localize(None)
    return normalized.sort_index()


def _merge_frames(existing: pd.DataFrame, fetched: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        return _normalize_index(fetched)
    if fetched.empty:
        return _normalize_index(existing)

    merged = pd.concat([_normalize_index(existing), _normalize_index(fetched)])
    merged = merged[~merged.index.duplicated(keep="last")]
    return merged.sort_index()


def _ensure_cache_covers_range(
    symbol: str,
    cached_df: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    requested_start = pd.Timestamp(start_date)
    requested_end = pd.Timestamp(end_date)
    merged = _normalize_index(cached_df)

    if merged.empty:
        return merged

    cache_start = pd.Timestamp(merged.index.min())
    cache_end = pd.Timestamp(merged.index.max())

    if requested_start < cache_start:
        fetch_end = (cache_start + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        fetched_left = fetch_daily_data(symbol, start_date, fetch_end)
        if not fetched_left.empty:
            merged = _merge_frames(merged, fetched_left)
            cache_start = pd.Timestamp(merged.index.min())

    if requested_end > cache_end:
        fetch_start = (cache_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        fetch_end = (requested_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        fetched_right = fetch_daily_data(symbol, fetch_start, fetch_end)
        if not fetched_right.empty:
            merged = _merge_frames(merged, fetched_right)

    return merged


def _slice_requested_range(df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    sliced = _normalize_index(df).loc[start_date:end_date]
    return sliced

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
            df = _ensure_cache_covers_range(symbol, df, start_date, end_date)
            if not df.empty:
                df.to_parquet(cache_file)
                sliced = _slice_requested_range(df, start_date, end_date)
                if not sliced.empty:
                    results[symbol] = sliced
        else:
            print(f"[CACHE MISS] Downloading {symbol} from Yahoo Finance...")
            df = fetch_daily_data(symbol, start_date, end_date)
            
            if not df.empty:
                normalized = _normalize_index(df)
                normalized.to_parquet(cache_file)
                sliced = _slice_requested_range(normalized, start_date, end_date)
                if not sliced.empty:
                    results[symbol] = sliced
            
            # Anti-ban delay: sleep half a second between actual hits to Yahoo
            time.sleep(0.5)

    return results
