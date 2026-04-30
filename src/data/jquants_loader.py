"""J-Quants daily price data loader.

Replaces yfinance with official JPX data. Advantages:
- Correctly adjusted for splits/dividends (AdjClose)
- Includes delisted stocks (no survivorship bias)
- Consistent ticker codes
- Faster batch fetching
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

import time

import pandas as pd

CACHE_DIR = Path(".data_cache/jquants")

JST = timezone(timedelta(hours=9))


def _get_client():
    from jquantsapi import ClientV2
    return ClientV2()


def _fetch_with_retry(cli, start_dt, end_dt, max_retries=3):
    """Fetch with exponential backoff for rate limits."""
    for attempt in range(max_retries):
        try:
            return cli.get_eq_bars_daily_range(start_dt=start_dt, end_dt=end_dt)
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"  Rate limited, retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


def _codes_to_jquants(tickers: list[str]) -> list[str]:
    """Strip .T suffix for J-Quants API."""
    return [t.replace(".T", "") for t in tickers]


def _to_jquants_date(date_str: str) -> datetime:
    """Convert YYYY-MM-DD to JST datetime for J-Quants API."""
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=JST)


def _parquet_path(code: str) -> Path:
    return CACHE_DIR / f"{code}.parquet"


def fetch_daily_bars(
    tickers: list[str],
    start: str,
    end: str,
    force_refresh: bool = False,
) -> dict[str, pd.DataFrame]:
    """Fetch daily OHLCV data for tickers, caching as Parquet.

    Args:
        tickers: List of ticker symbols with .T suffix (e.g. ["7203.T"]).
        start: Start date YYYY-MM-DD.
        end: End date YYYY-MM-DD.
        force_refresh: Ignore cache and re-fetch.

    Returns:
        {ticker: DataFrame with columns [Open, High, Low, Close, Volume]}
        Index is DatetimeIndex (tz-naive, date only).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    start_dt = _to_jquants_date(start)
    end_dt = _to_jquants_date(end)
    codes = _codes_to_jquants(tickers)

    result = {}
    to_fetch = []
    for ticker, code in zip(tickers, codes):
        cache_path = _parquet_path(code)
        if not force_refresh and cache_path.exists():
            cached = pd.read_parquet(cache_path)
            cached.index = pd.to_datetime(cached.index)
            result[ticker] = cached
        else:
            to_fetch.append((ticker, code))

    if not to_fetch:
        return result

    # J-Quants returns ALL stocks in one call — filter by code afterward
    cli = _get_client()
    code_set = {c for _, c in to_fetch}
    print(f"  [J-Quants] Fetching {len(code_set)} symbols {start}→{end}...")

    df = _fetch_with_retry(cli, start_dt, end_dt)
    if df.empty:
        return result

    # Filter to only our requested codes
    df = df[df["Code"].isin(code_set)]
    if df.empty:
        return result

    # Group by code and build per-symbol DataFrames
    code_to_ticker = {c: t for t, c in to_fetch}

    for code, group in df.groupby("Code"):
        ticker = code_to_ticker.get(code, f"{code}.T")
        bars = group.copy()
        bars["Date"] = pd.to_datetime(bars["Date"])
        bars = bars.set_index("Date").sort_index()

        # Rename columns to match our standard
        col_map = {
            "Open": "Open", "High": "High", "Low": "Low",
            "Close": "Close", "Volume": "Volume",
        }
        # J-Quants uses "AdjClose" for adjusted close
        close_col = "AdjClose" if "AdjClose" in bars.columns else "Close"
        output = pd.DataFrame()
        for col, name in col_map.items():
            jq_col = close_col if col == "Close" else col
            if jq_col in bars.columns:
                output[name] = bars[jq_col]
        if "Close" not in output.columns and close_col in bars.columns:
            output["Close"] = bars[close_col]

        if output.empty:
            continue

        # Strip timezone for consistency
        output.index = pd.DatetimeIndex(output.index.values)

        # Cache
        cache_path = _parquet_path(code)
        combined = output
        if cache_path.exists():
            existing = pd.read_parquet(cache_path)
            existing.index = pd.to_datetime(existing.index)
            combined = pd.concat([existing, output])
            combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        combined.index = pd.DatetimeIndex(combined.index.values)
        combined.to_parquet(cache_path)
        result[ticker] = combined

    return result


def fetch_universe(
    tickers: list[str],
    start: str,
    end: str,
    force_refresh: bool = False,
) -> dict[str, pd.DataFrame]:
    """Fetch daily data for a universe, returning data_dfs format.

    Compatible with the existing data_dfs interface used by scorers and engines.
    """
    return fetch_daily_bars(tickers, start, end, force_refresh)
