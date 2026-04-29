"""Fetch and cache annual book-value-per-share from yfinance.

Point-in-time rule: fiscal-year-end + 60 days = data available date.
Only use book values whose available date <= scoring date.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import yfinance as yf

CACHE_DIR = Path(".data_cache")
FUNDAMENTAL_CACHE = CACHE_DIR / "fundamentals.json"

PUBLICATION_DELAY_DAYS = 60


def _load_cache() -> dict:
    if not FUNDAMENTAL_CACHE.exists():
        return {}
    with open(FUNDAMENTAL_CACHE) as f:
        return json.load(f)


def _save_cache(data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(FUNDAMENTAL_CACHE, "w") as f:
        json.dump(data, f, indent=2)


def _compute_book_value_per_share(ticker: str) -> dict[str, float]:
    """Fetch annual balance sheet and compute BVPS for each fiscal year.

    Returns:
        {fiscal_year_end_date_str: book_value_per_share}
    """
    t = yf.Ticker(ticker)
    try:
        bs = t.balance_sheet
    except Exception:
        return {}

    if bs is None or bs.empty:
        return {}

    if "Stockholders Equity" not in bs.index:
        return {}
    if "Ordinary Shares Number" not in bs.index:
        return {}

    result = {}
    for col in bs.columns:
        date_str = col.strftime("%Y-%m-%d")
        equity = bs.loc["Stockholders Equity", col]
        shares = bs.loc["Ordinary Shares Number", col]
        treasury = 0.0
        if "Treasury Shares Number" in bs.index:
            ts = bs.loc["Treasury Shares Number", col]
            if not pd.isna(ts):
                treasury = float(ts)

        if pd.isna(equity) or pd.isna(shares) or shares == 0:
            continue

        outstanding = float(shares) - float(treasury)
        if outstanding <= 0:
            continue

        bvps = float(equity) / outstanding
        result[date_str] = round(bvps, 4)

    return result


def get_book_values(
    symbols: list[str],
    as_of_date: pd.Timestamp | None = None,
    force_refresh: bool = False,
) -> dict[str, float | None]:
    """Get point-in-time book-value-per-share for a list of symbols.

    Args:
        symbols: List of ticker symbols (e.g. ["7203.T", "8306.T"])
        as_of_date: Only use fiscal years where (fy_end + 60d) <= as_of_date.
                    If None, returns the latest available.
        force_refresh: If True, re-fetch from yfinance even if cached.

    Returns:
        {symbol: book_value_per_share or None if unavailable}
    """
    cache = _load_cache() if not force_refresh else {}

    result = {}
    for sym in symbols:
        if sym not in cache or force_refresh:
            try:
                bvps = _compute_book_value_per_share(sym)
                cache[sym] = bvps
            except Exception:
                cache[sym] = {}

        fiscal_years = cache.get(sym, {})
        if not fiscal_years:
            result[sym] = None
            continue

        if as_of_date is None:
            # Return the latest fiscal year
            latest = max(fiscal_years.keys())
            result[sym] = fiscal_years[latest]
            continue

        # Point-in-time: find the most recent fiscal year that was
        # published (fy_end + 60 days) before as_of_date
        available = {}
        for fy_str, bvps in fiscal_years.items():
            fy_date = pd.Timestamp(fy_str)
            pub_date = fy_date + pd.DateOffset(days=PUBLICATION_DELAY_DAYS)
            if pub_date <= as_of_date:
                available[fy_date] = bvps

        if available:
            best_fy = max(available.keys())
            result[sym] = available[best_fy]
        else:
            result[sym] = None

    # Always save cache if we fetched anything new or had cache hits
    _save_cache(cache)

    return result
