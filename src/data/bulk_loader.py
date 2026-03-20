import time
import pandas as pd
from pathlib import Path
from src.data.yfinance_loader import fetch_daily_data
from src.research.data_validation import validate_price_frame

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


def _slice_requested_range_raw(df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    raw_index = pd.to_datetime(df.index)
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    return df[(raw_index >= start) & (raw_index <= end)]

def fetch_universe(symbols: list[str], start_date: str, end_date: str) -> dict[str, pd.DataFrame]:
    """
    Fetches daily data for multiple symbols.
    Checks local parquet cache first. If MISS, delegates to yfinance_loader and caches.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    
    for symbol in symbols:
        cache_file = _get_cache_path(symbol)
        raw_df = pd.DataFrame()
        
        # Simplified cache hit verification
        if cache_file.exists():
            print(f"[CACHE HIT] Loading {symbol} from disk...")
            raw_df = pd.read_parquet(cache_file)
            df = _ensure_cache_covers_range(symbol, raw_df, start_date, end_date)
            if not df.empty:
                sliced = _slice_requested_range(df, start_date, end_date)
                validation = validate_price_frame(sliced)
                if validation.is_valid:
                    cache_validation = validate_price_frame(df)
                    if cache_validation.is_valid:
                        df.to_parquet(cache_file)
                    results[symbol] = _normalize_index(sliced)
                else:
                    print(f"[SKIP] {symbol}: {', '.join(validation.issues)}")
        else:
            print(f"[CACHE MISS] Downloading {symbol} from Yahoo Finance...")
            raw_df = fetch_daily_data(symbol, start_date, end_date)
            
            if not raw_df.empty:
                sliced = _slice_requested_range_raw(raw_df, start_date, end_date)
                validation = validate_price_frame(sliced)
                if validation.is_valid:
                    normalized = _normalize_index(raw_df)
                    normalized.to_parquet(cache_file)
                    results[symbol] = _slice_requested_range(normalized, start_date, end_date)
                else:
                    print(f"[SKIP] {symbol}: {', '.join(validation.issues)}")
            
            # Anti-ban delay: sleep half a second between actual hits to Yahoo
            time.sleep(0.5)

    return results
