"""Simple monthly-rebalance backtest engine.

No framework dependencies — pure pandas/numpy.
Execution: month-end scoring, month-start entry, integer shares,
equal dollar allocation, 5bp fee per side.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping

import numpy as np
import pandas as pd

from src.scoring.multi_factor import DEFAULT_TOP_N, score_universe

BookValuesInput = (
    Mapping[str, float | None]
    | Callable[[pd.Timestamp], Mapping[str, float | None] | None]
    | None
)


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


def _all_trading_days(data_dfs: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    all_dates = set()
    for df in data_dfs.values():
        if df is not None and not df.empty:
            all_dates.update(df.index)
    return pd.DatetimeIndex(sorted(all_dates))


def _price_on_or_after(df: pd.DataFrame, date: pd.Timestamp) -> float | None:
    if df is None or df.empty or "Close" not in df.columns:
        return None
    mask = df.index >= date
    if not mask.any():
        return None
    return float(df.loc[mask, "Close"].iloc[0])


def _price_on_or_before(df: pd.DataFrame, date: pd.Timestamp) -> float | None:
    if df is None or df.empty or "Close" not in df.columns:
        return None
    mask = df.index <= date
    if not mask.any():
        return None
    return float(df.loc[mask, "Close"].iloc[-1])


def _resolve_book_values(
    book_values: BookValuesInput,
    as_of_date: pd.Timestamp,
) -> Mapping[str, float | None] | None:
    if callable(book_values):
        return book_values(as_of_date)
    return book_values


def run_backtest_simple(
    data_dfs: dict[str, pd.DataFrame],
    start: str,
    end: str,
    weights: tuple[float, float, float],
    top_n: int = DEFAULT_TOP_N,
    initial_cash: float = 1_000_000.0,
    fee_rate: float = 0.0005,
    momentum_definition: str = "90d",
    reversal_filter_params=None,
    evaluation_start: str | None = None,
    evaluation_end: str | None = None,
    book_values: BookValuesInput = None,
    roe_values: dict[str, float | None] | None = None,
    industry_map: dict[str, str] | None = None,
    weight_size: float = 0.0,
    weight_evebit: float = 0.0,
    weight_divy: float = 0.0,
    market_caps: dict[str, float | None] | None = None,
    ev_ebit_values: dict[str, float | None] | None = None,
    dividend_yields: dict[str, float | None] | None = None,
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
    realized_pnl: dict[str, float] = {}
    records: list[tuple[pd.Timestamp, float]] = []
    scored = pd.DataFrame()

    trading_days = _all_trading_days(data_dfs)
    trading_days = trading_days[
        (trading_days >= pd.Timestamp(start))
        & (trading_days <= pd.Timestamp(end))
    ]
    exec_date_set = set(exec_dates)

    def mark_equity(mark_date: pd.Timestamp) -> float:
        equity = cash
        for sym, (shares, _) in holdings.items():
            px = _price_on_or_before(data_dfs.get(sym), mark_date)
            if px is not None:
                equity += shares * px
        return equity

    for current_date in trading_days:
        if current_date in exec_date_set:
            # Score using data strictly BEFORE the execution date
            window_dfs = {}
            for sym, df in data_dfs.items():
                if df is None or df.empty:
                    continue
                sliced = df.loc[df.index < current_date]
                if len(sliced) >= lookback:
                    window_dfs[sym] = sliced

            if window_dfs:
                try:
                    effective_book_values = _resolve_book_values(book_values, current_date)
                    if momentum_definition != "90d":
                        from src.research.research_scoring import score_research_universe
                        scored = score_research_universe(
                            window_dfs, top_n=top_n,
                            weight_mom=w_mom, weight_vol=w_vol, weight_rev=w_rev,
                            weight_val=w_val, weight_qual=w_qual, book_values=effective_book_values, roe_values=roe_values,
                            momentum_definition=momentum_definition,
                            weight_size=weight_size, weight_evebit=weight_evebit, weight_divy=weight_divy,
                            market_caps=market_caps, ev_ebit_values=ev_ebit_values, dividend_yields=dividend_yields,
                        )
                    else:
                        scored = score_universe(
                            window_dfs, top_n=top_n,
                            weight_mom=w_mom, weight_vol=w_vol, weight_rev=w_rev,
                            weight_val=w_val, weight_qual=w_qual, book_values=effective_book_values, roe_values=roe_values,
                            weight_size=weight_size, weight_evebit=weight_evebit, weight_divy=weight_divy,
                            market_caps=market_caps, ev_ebit_values=ev_ebit_values, dividend_yields=dividend_yields,
                            industry_map=industry_map,
                        )
                except ValueError:
                    scored = pd.DataFrame()

                if not scored.empty and reversal_filter_params is not None:
                    from src.research.reversal_filter import apply_reversal_filter
                    result = apply_reversal_filter(scored, window_dfs, reversal_filter_params)
                    scored = result["filtered_scores"]

                if not scored.empty:
                    picks = scored[scored["is_top_n"]]["symbol"].tolist()

                    prices = {
                        sym: px
                        for sym in set(picks) | set(holdings.keys())
                        if (px := _price_on_or_after(data_dfs.get(sym), current_date)) is not None
                    }

                    # Sell current priced holdings before rebuilding equal-weight targets.
                    for sym in list(holdings.keys()):
                        if sym not in prices:
                            continue
                        shares, cost_basis = holdings.pop(sym)
                        proceeds = shares * prices[sym] * (1 - fee_rate)
                        cash += proceeds
                        realized_pnl[sym] = realized_pnl.get(sym, 0.0) + proceeds - cost_basis

                    if picks and prices:
                        budget = cash * 0.95 / len(picks)
                        for sym in picks:
                            px = prices.get(sym)
                            if px is None or px <= 0:
                                continue
                            shares = int(budget / px / 100) * 100
                            if shares <= 0:
                                continue
                            cost = shares * px * (1 + fee_rate)
                            cash -= cost
                            if sym in holdings:
                                old_shares, old_cost = holdings[sym]
                                holdings[sym] = (old_shares + shares, old_cost + cost)
                            else:
                                holdings[sym] = (shares, cost)

        records.append((current_date, mark_equity(current_date)))

    if not records:
        return {
            "return_pct": 0.0, "sharpe": 0.0, "drawdown": 0.0,
            "symbol_returns": [], "scores": scored,
        }

    # Slice to evaluation window
    eval_start = pd.Timestamp(evaluation_start) if evaluation_start else records[0][0]
    eval_end = pd.Timestamp(evaluation_end) if evaluation_end else records[-1][0]
    eval_records = [(d, v) for d, v in records if eval_start <= d <= eval_end]
    if not eval_records:
        eval_records = records

    vals = pd.Series([v for _, v in eval_records])
    return_base = vals.iloc[0] if evaluation_start or evaluation_end else initial_cash
    total_return = (vals.iloc[-1] / return_base - 1) * 100 if return_base > 0 else 0.0

    daily_returns = vals.pct_change().dropna()
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        sharpe = float(daily_returns.mean() / daily_returns.std() * np.sqrt(252))
    else:
        sharpe = 0.0

    drawdown = float((vals / vals.cummax() - 1).min()) * 100
    symbol_returns = []
    mark_date = eval_records[-1][0]
    for sym in sorted(set(realized_pnl) | set(holdings)):
        pnl = realized_pnl.get(sym, 0.0)
        if sym in holdings:
            shares, cost_basis = holdings[sym]
            px = _price_on_or_before(data_dfs.get(sym), mark_date)
            if px is not None:
                pnl += shares * px - cost_basis
        symbol_returns.append({
            "symbol": sym,
            "return_pct": round((pnl / initial_cash) * 100.0, 4) if initial_cash > 0 else 0.0,
        })

    return {
        "return_pct": round(total_return, 4),
        "sharpe": round(sharpe, 4),
        "drawdown": round(drawdown, 4),
        "symbol_returns": symbol_returns,
        "scores": scored,
    }
