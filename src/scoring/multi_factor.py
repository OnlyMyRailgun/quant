from __future__ import annotations

import math
from typing import Mapping

import pandas as pd


DEFAULT_LOOKBACK_MOM = 90
DEFAULT_LOOKBACK_VOL = 20
DEFAULT_LOOKBACK_REV = 20
DEFAULT_TOP_N = 10
DEFAULT_WEIGHT_REV = 0.0


def _validate_close_series(df: pd.DataFrame) -> pd.Series:
    if "Close" not in df.columns:
        raise KeyError("DataFrame must contain a 'Close' column")

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if close.empty:
        raise ValueError("Close series is empty after coercion")
    if not pd.Series(close, dtype="float64").map(math.isfinite).all():
        raise ValueError("Close series contains non-finite values")
    if (close <= 0).any():
        raise ValueError("Close series contains non-positive prices")

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
    # A NaN raw value (e.g. a missing optional fundamental) is neutralized to
    # 0.0 rather than propagating NaN into the stock's total_score, which would
    # otherwise sink it to the bottom of the ranking on an unrelated factor.
    return [
        multiplier * ((value - mean) / std) if math.isfinite(value) else 0.0
        for value in values
    ]


def _industry_neutral_zscores(
    values: list[float],
    industries: list[str],
    invert: bool = False,
) -> list[float]:
    """Compute z-scores within each industry, then combine.

    For industry groups with only 1 stock, the stock keeps its raw value
    (no peer comparison available), normalized to the overall cross-section.
    """
    if len(values) < 2:
        return [0.0] * len(values)

    df = pd.DataFrame({"raw": values, "industry": industries})
    # Cross-sectional z-scores used as fallback when an industry group cannot
    # produce its own z-score (single-stock group, or zero/NaN within-group std).
    cross_sectional = _safe_zscores(values, invert=invert)
    result = list(cross_sectional)
    multiplier = -1.0 if invert else 1.0

    for industry, group in df.groupby("industry"):
        idx = group.index.tolist()
        group_vals = group["raw"].tolist()
        if len(group_vals) >= 2:
            series = pd.Series(group_vals, dtype="float64")
            std = series.std(ddof=1)
            if std > 0 and not pd.isna(std):
                mean = series.mean()
                for j, i in enumerate(idx):
                    val = group_vals[j]
                    result[i] = (
                        multiplier * ((val - mean) / std)
                        if math.isfinite(val)
                        else 0.0
                    )
                continue
        # Fallback: single-stock or degenerate-std industry → cross-sectional
        # z-score, matching this function's documented contract.
        for i in idx:
            result[i] = cross_sectional[i]

    return result


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


def _has_only_finite_factors(factors: Mapping[str, float]) -> bool:
    return all(math.isfinite(value) for value in factors.values())


def score_universe(
    data_dfs: Mapping[str, pd.DataFrame],
    top_n: int = DEFAULT_TOP_N,
    weight_mom: float = 1.0,
    weight_vol: float = 1.0,
    weight_rev: float = DEFAULT_WEIGHT_REV,
    weight_val: float = 0.0,
    weight_qual: float = 0.0,
    lookback_mom: int = DEFAULT_LOOKBACK_MOM,
    lookback_vol: int = DEFAULT_LOOKBACK_VOL,
    lookback_rev: int = DEFAULT_LOOKBACK_REV,
    book_values: Mapping[str, float | None] | None = None,
    roe_values: Mapping[str, float | None] | None = None,
    industry_map: dict[str, str] | None = None,
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
    raw_val: list[float] = []
    raw_qual: list[float] = []
    use_value = book_values is not None and weight_val > 0.0
    use_qual = roe_values is not None and weight_qual > 0.0

    for symbol, df in data_dfs.items():
        if df is None or df.empty:
            continue

        try:
            close = _validate_close_series(df)
        except (TypeError, ValueError):
            continue

        required_history = max(lookback_mom, lookback_vol, lookback_rev)
        if len(close) < required_history:
            continue

        factors = _compute_factors(close, lookback_mom, lookback_vol, lookback_rev)
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

        if use_qual:
            roe = roe_values.get(symbol)
            if roe is not None and math.isfinite(roe):
                factors["qual_raw"] = roe
            else:
                roe = math.nan
                factors["qual_raw"] = roe
            raw_qual.append(roe)

        raw_mom.append(factors["mom_raw"])
        raw_vol.append(factors["vol_raw"])
        raw_rev.append(factors["rev_raw"])
        records.append({"symbol": symbol, **factors})

    if not records:
        cols = [
            "symbol", "price",
            "mom_raw", "vol_raw", "rev_raw",
            "mom_z", "vol_z", "rev_z",
            "mom_contribution", "vol_contribution", "rev_contribution",
            "total_score", "rank", "is_top_n",
        ]
        if use_value:
            cols.insert(cols.index("rev_raw") + 1, "val_raw")
            cols.insert(cols.index("rev_z") + 1, "val_z")
            cols.insert(cols.index("rev_contribution") + 1, "val_contribution")
        return pd.DataFrame(columns=cols)

    industries = [industry_map.get(r["symbol"], "Other") for r in records] if industry_map else None
    _z = (lambda v, invert=False: _industry_neutral_zscores(v, industries, invert)) if industries else _safe_zscores

    mom_z = _z(raw_mom, invert=False)
    vol_z = _z(raw_vol, invert=True)
    rev_z = _z(raw_rev, invert=True)
    val_z = _z(raw_val, invert=True) if use_value else [0.0] * len(records)
    qual_z = _z(raw_qual, invert=False) if use_qual else [0.0] * len(records)

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
        if use_qual:
            record["qual_z"] = qual_z[i]
            record["qual_contribution"] = weight_qual * qual_z[i]
            total += record["qual_contribution"]
        record["total_score"] = total

    ranked = pd.DataFrame(records)
    ranked = ranked.sort_values(by="total_score", ascending=False, kind="mergesort")
    ranked["rank"] = range(1, len(ranked) + 1)
    ranked["is_top_n"] = ranked["rank"] <= top_n
    return ranked.reset_index(drop=True)
