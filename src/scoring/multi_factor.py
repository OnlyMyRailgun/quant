from __future__ import annotations

import math
from typing import Mapping

import pandas as pd


DEFAULT_LOOKBACK_MOM = 90
DEFAULT_LOOKBACK_VOL = 20
DEFAULT_LOOKBACK_REV = 20


def _validate_close_series(df: pd.DataFrame) -> pd.Series:
    if "Close" not in df.columns:
        raise KeyError("DataFrame must contain a 'Close' column")

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if close.empty:
        raise ValueError("Close series is empty after coercion")

    return close


def _safe_zscores(values: list[float], invert: bool = False) -> list[float]:
    if len(values) < 2:
        return [0.0] * len(values)

    series = pd.Series(values, dtype="float64")
    std = series.std(ddof=1)
    if pd.isna(std) or std == 0.0:
        return [0.0] * len(values)

    mean = series.mean()
    multiplier = -1.0 if invert else 1.0
    return [multiplier * ((value - mean) / std) for value in values]


def _compute_factors(
    close: pd.Series,
    lookback_mom: int,
    lookback_vol: int,
    lookback_rev: int,
) -> dict[str, float]:
    if len(close) < max(lookback_mom, lookback_vol, lookback_rev):
        raise ValueError("Not enough history for requested lookbacks")

    latest_price = float(close.iloc[-1])
    mom_base = float(close.iloc[-lookback_mom])
    mom = (latest_price - mom_base) / mom_base if mom_base != 0.0 else math.nan

    daily_ret = close.pct_change().dropna()
    vol_window = daily_ret.iloc[-lookback_vol:]
    vol = float(vol_window.std(ddof=1)) if not vol_window.empty else math.nan

    sma_window = close.iloc[-lookback_rev:]
    sma = float(sma_window.mean())
    rev = (latest_price - sma) / sma if sma != 0.0 else math.nan

    return {
        "price": latest_price,
        "mom_raw": mom,
        "vol_raw": vol,
        "rev_raw": rev,
    }


def score_universe(
    data_dfs: Mapping[str, pd.DataFrame],
    top_n: int = 3,
    weight_mom: float = 1.0,
    weight_vol: float = 1.0,
    weight_rev: float = 1.0,
    lookback_mom: int = DEFAULT_LOOKBACK_MOM,
    lookback_vol: int = DEFAULT_LOOKBACK_VOL,
    lookback_rev: int = DEFAULT_LOOKBACK_REV,
) -> pd.DataFrame:
    """
    Score a symbol universe using cross-sectional multi-factor ranking.

    Returns the full ranked universe as a DataFrame sorted by total score
    descending. The top N rows are marked with ``is_top_n`` for downstream
    consumers.
    """
    if top_n < 1:
        raise ValueError("top_n must be >= 1")

    records: list[dict[str, float | str]] = []
    raw_mom: list[float] = []
    raw_vol: list[float] = []
    raw_rev: list[float] = []

    for symbol, df in data_dfs.items():
        if df is None or df.empty:
            continue

        close = _validate_close_series(df)
        if len(close) < max(lookback_mom, lookback_vol, lookback_rev):
            continue

        factors = _compute_factors(close, lookback_mom, lookback_vol, lookback_rev)
        raw_mom.append(factors["mom_raw"])
        raw_vol.append(factors["vol_raw"])
        raw_rev.append(factors["rev_raw"])
        records.append({"symbol": symbol, **factors})

    if not records:
        return pd.DataFrame(
            columns=[
                "symbol",
                "price",
                "mom_raw",
                "vol_raw",
                "rev_raw",
                "mom_z",
                "vol_z",
                "rev_z",
                "total_score",
                "rank",
                "is_top_n",
            ]
        )

    mom_z = _safe_zscores(raw_mom, invert=False)
    vol_z = _safe_zscores(raw_vol, invert=True)
    rev_z = _safe_zscores(raw_rev, invert=True)

    for i, record in enumerate(records):
        record["mom_z"] = mom_z[i]
        record["vol_z"] = vol_z[i]
        record["rev_z"] = rev_z[i]
        record["total_score"] = (
            (weight_mom * mom_z[i])
            + (weight_vol * vol_z[i])
            + (weight_rev * rev_z[i])
        )

    ranked = pd.DataFrame(records)
    ranked = ranked.sort_values(by="total_score", ascending=False, kind="mergesort")
    ranked["rank"] = range(1, len(ranked) + 1)
    ranked["is_top_n"] = ranked["rank"] <= top_n
    return ranked.reset_index(drop=True)
