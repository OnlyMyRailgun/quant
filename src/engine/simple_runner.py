"""Simple monthly-rebalance backtest engine.

No framework dependencies — pure pandas/numpy.
Execution: month-end scoring, month-start entry, integer shares,
equal dollar allocation, 5bp fee per side.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.scoring.multi_factor import score_universe


def _first_trading_days(data_dfs: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    """Find the first trading day of each month from the union of all symbols' dates."""
    all_dates = set()
    for df in data_dfs.values():
        if df is not None and not df.empty:
            all_dates.update(df.index)
    dates = pd.DatetimeIndex(sorted(all_dates))
    df = pd.DataFrame({"date": dates})
    first_days = df.groupby([df["date"].dt.year, df["date"].dt.month])["date"].first()
    return pd.DatetimeIndex(first_days.values)


def run_backtest_simple(
    data_dfs: dict[str, pd.DataFrame],
    start: str,
    end: str,
    weights: tuple[float, float, float],
    top_n: int = 3,
    initial_cash: float = 1_000_000.0,
    fee_rate: float = 0.0005,
    momentum_definition: str = "90d",
    reversal_filter_params=None,
    evaluation_start: str | None = None,
    evaluation_end: str | None = None,
    book_values: dict[str, float | None] | None = None,
    roe_values: dict[str, float | None] | None = None,
    industry_map: dict[str, str] | None = None,
) -> dict:
    w_mom, w_vol, w_rev = weights[:3]
    w_val = weights[3] if len(weights) > 3 else 0.0
    w_qual = weights[4] if len(weights) > 4 else 0.0

    if momentum_definition == "12_1":
        lookback = 252
    else:
        lookback = 90

    all_first_days = _first_trading_days(data_dfs)
    exec_dates = all_first_days[
        (all_first_days >= pd.Timestamp(start))
        & (all_first_days <= pd.Timestamp(end))
    ]

    cash = initial_cash
    holdings: dict[str, tuple[int, float]] = {}
    records: list[tuple[pd.Timestamp, float]] = []

    for exec_date in exec_dates:
        # Score using data strictly BEFORE the execution date
        window_dfs = {}
        for sym, df in data_dfs.items():
            if df is None or df.empty:
                continue
            sliced = df.loc[df.index < exec_date]
            if len(sliced) >= lookback:
                window_dfs[sym] = sliced

        if not window_dfs:
            continue

        try:
            if momentum_definition != "90d":
                from src.research.research_scoring import score_research_universe
                scored = score_research_universe(
                    window_dfs, top_n=top_n,
                    weight_mom=w_mom, weight_vol=w_vol, weight_rev=w_rev,
                    weight_val=w_val, weight_qual=w_qual, book_values=book_values, roe_values=roe_values,
                    momentum_definition=momentum_definition,
                )
            else:
                scored = score_universe(
                    window_dfs, top_n=top_n,
                    weight_mom=w_mom, weight_vol=w_vol, weight_rev=w_rev,
                    weight_val=w_val, weight_qual=w_qual, book_values=book_values, roe_values=roe_values,
                    industry_map=industry_map,
                )
        except ValueError:
            continue

        if scored.empty:
            continue

        if reversal_filter_params is not None:
            from src.research.reversal_filter import apply_reversal_filter
            result = apply_reversal_filter(scored, window_dfs, reversal_filter_params)
            scored = result["filtered_scores"]
            if scored.empty:
                continue

        picks = scored[scored["is_top_n"]]["symbol"].tolist()

        # Get execution prices (first bar on or after exec_date)
        prices = {}
        for sym in set(picks) | set(holdings.keys()):
            df = data_dfs.get(sym)
            if df is not None and "Close" in df.columns:
                mask = df.index >= exec_date
                if mask.any():
                    prices[sym] = float(df.loc[mask, "Close"].iloc[0])

        # Sell all current holdings
        for sym in list(holdings.keys()):
            if sym in prices:
                shares, _ = holdings[sym]
                cash += shares * prices[sym] * (1 - fee_rate)
                del holdings[sym]

        # Buy new picks with equal dollar allocation
        holdings = {}
        if picks and prices:
            budget = cash * 0.95 / len(picks)
            for sym in picks:
                px = prices.get(sym)
                if px and px > 0:
                    shares = int(budget / px / 100) * 100
                    cost = shares * px * (1 + fee_rate)
                    cash -= cost
                    holdings[sym] = (shares, px)

        # Mark to market
        equity = cash
        for sym, (shares, _) in holdings.items():
            if sym in prices:
                equity += shares * prices[sym]
        records.append((exec_date, equity))

    if not records:
        return {
            "return_pct": 0.0, "sharpe": 0.0, "drawdown": 0.0,
            "symbol_returns": {}, "scores": scored if 'scored' in dir() else pd.DataFrame(),
        }

    # Slice to evaluation window
    eval_start = pd.Timestamp(evaluation_start) if evaluation_start else records[0][0]
    eval_end = pd.Timestamp(evaluation_end) if evaluation_end else records[-1][0]
    eval_records = [(d, v) for d, v in records if eval_start <= d <= eval_end]
    if not eval_records:
        eval_records = records

    vals = pd.Series([v for _, v in eval_records])
    total_return = (vals.iloc[-1] / initial_cash - 1) * 100

    monthly_returns = vals.pct_change().dropna()
    if len(monthly_returns) > 1 and monthly_returns.std() > 0:
        sharpe = float(monthly_returns.mean() / monthly_returns.std() * np.sqrt(12))
    else:
        sharpe = 0.0

    drawdown = float((vals / vals.cummax() - 1).min()) * 100

    return {
        "return_pct": round(total_return, 4),
        "sharpe": round(sharpe, 4),
        "drawdown": round(drawdown, 4),
        "symbol_returns": {},
        "scores": scored if 'scored' in dir() else pd.DataFrame(),
    }
