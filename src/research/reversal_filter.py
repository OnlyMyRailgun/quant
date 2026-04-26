from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class ReversalFilterParams:
    lookback_days: int = 20
    threshold: float = 0.10


def _close_series(frame: pd.DataFrame) -> pd.Series:
    if "Close" not in frame.columns:
        return pd.Series(dtype="float64", index=frame.index)
    return pd.to_numeric(frame["Close"], errors="coerce")


def _compute_drawdown(frame: pd.DataFrame, lookback_days: int) -> tuple[float, float, float]:
    """Return (drawdown, recent_high, latest_price).

    drawdown = (latest - recent_high) / recent_high.
    Negative values mean the stock is below its recent high.
    """
    close = _close_series(frame)
    if len(close) < lookback_days:
        return float("nan"), float("nan"), float("nan")

    recent = close.iloc[-lookback_days:]
    recent_high = float(recent.max())
    latest_price = float(close.iloc[-1])

    if recent_high == 0.0 or pd.isna(recent_high) or pd.isna(latest_price):
        return float("nan"), float("nan"), float("nan")

    drawdown = (latest_price - recent_high) / recent_high
    return drawdown, recent_high, latest_price


def apply_reversal_filter(
    scored_df: pd.DataFrame,
    data_dfs: Mapping[str, pd.DataFrame],
    params: ReversalFilterParams | None = None,
) -> dict:
    if params is None:
        params = ReversalFilterParams()

    if scored_df.empty:
        empty_df = scored_df.copy()
        empty_df["reversal_drawdown"] = pd.Series(dtype="float64")
        empty_df["reversal_flagged"] = pd.Series(dtype="bool")
        return {
            "filtered_scores": empty_df,
            "retained_symbols": [],
            "flagged_symbols": [],
            "by_symbol": {},
            "summary": {
                "scored_symbol_count": 0,
                "retained_symbol_count": 0,
                "flagged_symbol_count": 0,
                "retention_ratio": 0.0,
            },
        }

    top_n = int(scored_df["is_top_n"].sum())
    scored_count = len(scored_df)

    # If universe is smaller than top_n, don't filter — problem is universe, not timing
    if scored_count < top_n:
        scored_df = scored_df.copy()
        scored_df["reversal_drawdown"] = 0.0
        scored_df["reversal_flagged"] = False
        return {
            "filtered_scores": scored_df,
            "retained_symbols": list(scored_df["symbol"]),
            "flagged_symbols": [],
            "by_symbol": {
                sym: {"drawdown": 0.0, "recent_high": 0.0, "latest_price": 0.0, "flagged": False}
                for sym in scored_df["symbol"]
            },
            "summary": {
                "scored_symbol_count": scored_count,
                "retained_symbol_count": scored_count,
                "flagged_symbol_count": 0,
                "retention_ratio": 1.0,
            },
        }

    # Compute per-symbol metrics
    by_symbol: dict = {}
    for _, row in scored_df.iterrows():
        sym = row["symbol"]
        frame = data_dfs.get(sym)

        if frame is None or frame.empty:
            by_symbol[sym] = {"drawdown": float("nan"), "recent_high": float("nan"),
                              "latest_price": float("nan"), "flagged": True}
            continue

        dd, high, latest = _compute_drawdown(frame, params.lookback_days)

        if pd.isna(dd):
            by_symbol[sym] = {"drawdown": float("nan"), "recent_high": float("nan"),
                              "latest_price": float("nan"), "flagged": True}
            continue

        flagged = dd < -params.threshold
        by_symbol[sym] = {"drawdown": round(float(dd), 6), "recent_high": float(high),
                          "latest_price": float(latest), "flagged": flagged}

    # Fallback: relax threshold if retained < top_n
    retained = [sym for sym, info in by_symbol.items() if not info["flagged"]]

    if len(retained) < top_n:
        relaxed = params.threshold + 0.05
        max_relaxed = params.threshold * 3.0
        while len(retained) < top_n and relaxed <= max_relaxed:
            for sym, info in by_symbol.items():
                if info["flagged"] and not pd.isna(info["drawdown"]) and info["drawdown"] >= -relaxed:
                    info["flagged"] = False
            retained = [sym for sym, info in by_symbol.items() if not info["flagged"]]
            relaxed += 0.05

        # If still not enough, fill with least-negative-drawdown stocks
        if len(retained) < min(top_n, scored_count):
            flagged_stocks = [(sym, info["drawdown"]) for sym, info in by_symbol.items()
                              if info["flagged"] and not pd.isna(info["drawdown"])]
            flagged_stocks.sort(key=lambda x: x[1], reverse=True)  # closest to 0 first
            needed = min(top_n, scored_count) - len(retained)
            for sym, _ in flagged_stocks[:needed]:
                by_symbol[sym]["flagged"] = False
            retained = [sym for sym, info in by_symbol.items() if not info["flagged"]]

    flagged = [sym for sym, info in by_symbol.items() if info["flagged"]]

    # Build filtered DataFrame
    scored_df = scored_df.copy()
    scored_df["reversal_drawdown"] = scored_df["symbol"].map(
        lambda s: by_symbol[s]["drawdown"] if s in by_symbol else float("nan")
    )
    scored_df["reversal_flagged"] = scored_df["symbol"].map(
        lambda s: by_symbol[s]["flagged"] if s in by_symbol else True
    )

    filtered = scored_df[~scored_df["reversal_flagged"]].copy()
    if not filtered.empty:
        filtered = filtered.sort_values(by="total_score", ascending=False, kind="mergesort")
        filtered["rank"] = range(1, len(filtered) + 1)
        filtered["is_top_n"] = filtered["rank"] <= top_n

    return {
        "filtered_scores": filtered.reset_index(drop=True),
        "retained_symbols": retained,
        "flagged_symbols": flagged,
        "by_symbol": by_symbol,
        "summary": {
            "scored_symbol_count": scored_count,
            "retained_symbol_count": len(retained),
            "flagged_symbol_count": len(flagged),
            "retention_ratio": len(retained) / scored_count if scored_count > 0 else 0.0,
        },
    }
