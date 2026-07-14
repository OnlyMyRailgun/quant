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
QUALITY_CACHE = CACHE_DIR / "quality.json"

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
        # An empty cache entry means a prior fetch failed to return data; retry
        # rather than treating the transient failure as a permanent result.
        if not cache.get(sym) or force_refresh:
            try:
                bvps = _compute_book_value_per_share(sym)
            except Exception:
                bvps = {}
            if bvps:
                cache[sym] = bvps

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


# ── ROE (Return on Equity) quality factor ──


def _compute_roe(ticker: str) -> dict[str, float]:
    """Fetch ROE from quarterly financials. ROE = TTM Net Income / Equity.

    Returns: {fiscal_quarter_end_date_str: roe}
    """
    t = yf.Ticker(ticker)
    try:
        income = t.quarterly_financials
        bs = t.quarterly_balance_sheet
    except Exception:
        return {}

    if income is None or income.empty or bs is None or bs.empty:
        return {}

    ni_key = None
    for k in ["Net Income Common Stockholders", "Net Income"]:
        if k in income.index:
            ni_key = k
            break
    eq_key = None
    for k in ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"]:
        if k in bs.index:
            eq_key = k
            break
    if ni_key is None or eq_key is None:
        return {}

    # Align quarters and compute TTM ROE. Columns are sorted newest first, so
    # each current quarter uses itself plus the next three older quarters.
    common = sorted(set(income.columns) & set(bs.columns), reverse=True)
    result = {}
    for i, col in enumerate(common):
        ttm_cols = common[i : i + 4]
        if len(ttm_cols) < 4:
            continue
        # Guard against misaligned statements: the intersection can leave gaps
        # so that 4 consecutive columns span more than a year. Such a window is
        # not a true trailing-twelve-month figure, so skip it.
        span_days = (pd.Timestamp(ttm_cols[0]) - pd.Timestamp(ttm_cols[-1])).days
        if span_days > 320:
            continue
        ni_values = income.loc[ni_key, ttm_cols]
        eq = bs.loc[eq_key, col]
        if ni_values.isna().any() or pd.isna(eq) or eq == 0:
            continue
        roe = float(ni_values.sum()) / float(eq)
        result[col.strftime("%Y-%m-%d")] = round(roe, 6)

    return result


def _load_quality_cache() -> dict:
    if not QUALITY_CACHE.exists():
        return {}
    with open(QUALITY_CACHE) as f:
        return json.load(f)


def _save_quality_cache(data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(QUALITY_CACHE, "w") as f:
        json.dump(data, f, indent=2)


def get_roe_values(
    symbols: list[str],
    as_of_date: pd.Timestamp | None = None,
    force_refresh: bool = False,
) -> dict[str, float | None]:
    """Get point-in-time ROE for a list of symbols.

    Args:
        symbols: List of ticker symbols.
        as_of_date: PIT filter. None = latest available.
        force_refresh: Re-fetch from yfinance.

    Returns:
        {symbol: ROE as fraction (e.g., 0.10 = 10%) or None}
    """
    cache = _load_quality_cache() if not force_refresh else {}

    result = {}
    for sym in symbols:
        # An empty cache entry means a prior fetch failed to return data; retry
        # rather than treating the transient failure as a permanent result.
        if not cache.get(sym) or force_refresh:
            try:
                roe_data = _compute_roe(sym)
            except Exception:
                roe_data = {}
            if roe_data:
                cache[sym] = roe_data

        roe_by_quarter = cache.get(sym, {})
        if not roe_by_quarter:
            result[sym] = None
            continue

        if as_of_date is None:
            latest = max(roe_by_quarter.keys())
            result[sym] = roe_by_quarter[latest]
            continue

        available = {}
        for q_str, roe in roe_by_quarter.items():
            q_date = pd.Timestamp(q_str)
            pub_date = q_date + pd.DateOffset(days=PUBLICATION_DELAY_DAYS)
            if pub_date <= as_of_date:
                available[q_date] = roe

        if available:
            result[sym] = available[max(available.keys())]
        else:
            result[sym] = None

    _save_quality_cache(cache)
    return result


# ── Earnings Yield (1/trailingPE) quality factor ──


def get_earnings_yield(
    symbols: list[str],
    force_refresh: bool = False,
) -> dict[str, float | None]:
    """Fetch trailingPE from yfinance info, compute earnings yield = 1/PE.

    Uses current (latest) PE — suitable for live trading, NOT historical
    backtesting due to look-ahead bias if used on past dates.

    Returns: {symbol: earnings_yield (e.g. 0.09 = 9%) or None}
    """
    result = {}
    for sym in symbols:
        try:
            t = yf.Ticker(sym)
            pe = t.info.get("trailingPE")
            if pe is not None and pe > 0 and not pd.isna(pe):
                result[sym] = round(1.0 / float(pe), 6)
            else:
                result[sym] = None
        except Exception:
            result[sym] = None
    return result
