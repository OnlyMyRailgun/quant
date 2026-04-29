from __future__ import annotations

import math
from typing import Mapping, Literal

import pandas as pd
from src.scoring.multi_factor import (
    _validate_close_series,
    _safe_zscores,
    _has_only_finite_factors,
    DEFAULT_LOOKBACK_MOM,
    DEFAULT_LOOKBACK_VOL,
    DEFAULT_LOOKBACK_REV,
)

def _compute_research_factors(
    close: pd.Series,
    momentum_definition: Literal["90d", "12_1"],
    lookback_vol: int,
    lookback_rev: int,
) -> dict[str, float]:
    latest_price = float(close.iloc[-1])
    
    # 1. Momentum calculation
    if momentum_definition == "12_1":
        # Classic 12-1 momentum: (Close_{t-21} / Close_{t-251}) - 1
        # Needs at least 252 points
        if len(close) < 252:
            raise ValueError("Not enough history for 12-1 momentum (need 252 days)")
        
        # t is at len-1
        # t-21 is at len-1-21 = len-22
        # t-251 is at len-1-251 = len-252
        p_t_minus_21 = float(close.iloc[-22])
        p_t_minus_251 = float(close.iloc[-252])
        mom = (p_t_minus_21 - p_t_minus_251) / p_t_minus_251 if p_t_minus_251 != 0.0 else math.nan
    else:
        # Default 90d momentum: (Close_t / Close_{t-90}) - 1
        lookback_mom = DEFAULT_LOOKBACK_MOM
        if len(close) < lookback_mom:
            raise ValueError(f"Not enough history for 90d momentum (need {lookback_mom} days)")
        mom_base = float(close.iloc[-lookback_mom])
        mom = (latest_price - mom_base) / mom_base if mom_base != 0.0 else math.nan

    # 2. Volatility (same as default)
    daily_ret = close.pct_change().dropna()
    vol_window = daily_ret.iloc[-lookback_vol:]
    vol = float(vol_window.std(ddof=1)) if not vol_window.empty else math.nan

    # 3. Mean Reversion (same as default)
    sma_window = close.iloc[-lookback_rev:]
    sma = float(sma_window.mean())
    rev = (latest_price - sma) / sma if sma != 0.0 else math.nan

    return {
        "price": latest_price,
        "mom_raw": mom,
        "vol_raw": vol,
        "rev_raw": rev,
    }

def score_research_universe(
    data_dfs: Mapping[str, pd.DataFrame],
    top_n: int = 3,
    weight_mom: float = 1.0,
    weight_vol: float = 1.0,
    weight_rev: float = 1.0,
    weight_val: float = 0.0,
    momentum_definition: Literal["90d", "12_1"] = "90d",
    lookback_vol: int = DEFAULT_LOOKBACK_VOL,
    lookback_rev: int = DEFAULT_LOOKBACK_REV,
    book_values: Mapping[str, float | None] | None = None,
) -> pd.DataFrame:
    """
    Score a symbol universe using cross-sectional multi-factor ranking with
    optional research momentum definitions.
    """
    if top_n < 1:
        raise ValueError("top_n must be >= 1")

    records: list[dict[str, float | str]] = []
    raw_mom: list[float] = []
    raw_vol: list[float] = []
    raw_rev: list[float] = []
    raw_val: list[float] = []
    use_value = book_values is not None and weight_val > 0.0

    required_history = 252 if momentum_definition == "12_1" else max(DEFAULT_LOOKBACK_MOM, lookback_vol, lookback_rev)

    for symbol, df in data_dfs.items():
        if df is None or df.empty:
            continue

        try:
            close = _validate_close_series(df)
        except (TypeError, ValueError):
            continue

        if len(close) < required_history:
            continue

        try:
            factors = _compute_research_factors(
                close, 
                momentum_definition, 
                lookback_vol, 
                lookback_rev
            )
        except ValueError:
            continue

        if not _has_only_finite_factors(factors):
            continue

        if use_value:
            bv = book_values.get(symbol)
            if bv is not None and bv > 0:
                pb_raw = factors["price"] / bv
            else:
                pb_raw = math.nan
            factors["val_raw"] = pb_raw
            raw_val.append(pb_raw)

        raw_mom.append(factors["mom_raw"])
        raw_vol.append(factors["vol_raw"])
        raw_rev.append(factors["rev_raw"])
        records.append({"symbol": symbol, **factors})

    if not records:
        return pd.DataFrame(
            columns=[
                "symbol", "price", "mom_raw", "vol_raw", "rev_raw",
                "mom_z", "vol_z", "rev_z",
                "mom_contribution", "vol_contribution", "rev_contribution",
                "total_score", "rank", "is_top_n",
            ]
        )

    mom_z = _safe_zscores(raw_mom, invert=False)
    vol_z = _safe_zscores(raw_vol, invert=True)
    rev_z = _safe_zscores(raw_rev, invert=True)
    val_z = _safe_zscores(raw_val, invert=True) if use_value else [0.0] * len(records)

    for i, record in enumerate(records):
        record["mom_z"] = mom_z[i]
        record["vol_z"] = vol_z[i]
        record["rev_z"] = rev_z[i]
        record["mom_contribution"] = weight_mom * mom_z[i]
        record["vol_contribution"] = weight_vol * vol_z[i]
        record["rev_contribution"] = weight_rev * rev_z[i]
        total = record["mom_contribution"] + record["vol_contribution"] + record["rev_contribution"]
        if use_value:
            record["val_z"] = val_z[i]
            record["val_contribution"] = weight_val * val_z[i]
            total += record["val_contribution"]
        record["total_score"] = total

    ranked = pd.DataFrame(records)
    ranked = ranked.sort_values(by="total_score", ascending=False, kind="mergesort")
    ranked["rank"] = range(1, len(ranked) + 1)
    ranked["is_top_n"] = ranked["rank"] <= top_n
    return ranked.reset_index(drop=True)
