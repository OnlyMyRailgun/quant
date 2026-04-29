from __future__ import annotations

import numpy as np
import pandas as pd

from src.engine.order_builder import build_orders
from src.scoring.multi_factor import (
    score_universe,
    DEFAULT_LOOKBACK_MOM,
    DEFAULT_LOOKBACK_VOL,
    DEFAULT_LOOKBACK_REV,
)


def run_backtest_vectorbt(
    data_dfs: dict[str, pd.DataFrame],
    start: str,
    end: str,
    weights: tuple[float, float, float],
    top_n: int = 3,
    initial_cash: float = 1_000_000.0,
    commission_rate: float = 0.001,
    slippage_pct: float = 0.0005,
    momentum_definition: str = "90d",
    reversal_filter_params=None,
    evaluation_start: str | None = None,
    evaluation_end: str | None = None,
) -> dict:
    """Orchestrate per-date scoring, order building, and vectorbt portfolio simulation.

    Parameters
    ----------
    data_dfs : dict[str, pd.DataFrame]
        Mapping of symbol to DataFrame containing at least a 'Close' column.
    start : str
        Backtest start date (YYYY-MM-DD).
    end : str
        Backtest end date (YYYY-MM-DD).
    weights : tuple[float, float, float]
        (weight_mom, weight_vol, weight_rev) for the scoring function.
    top_n : int
        Number of top-ranked stocks to hold.
    initial_cash : float
        Starting portfolio cash.
    commission_rate : float
        Commission rate as a decimal (e.g. 0.001 = 10bp).
    slippage_pct : float
        Slippage as a decimal applied to execution price.
    momentum_definition : str
        "90d" or "12_1".
    reversal_filter_params : optional
        If provided, applied after scoring to filter out reversal-risk stocks.
    evaluation_start : str | None
        Start of evaluation window for computing metrics.
    evaluation_end : str | None
        End of evaluation window for computing metrics.

    Returns
    -------
    dict
        Metrics dict with keys: return_pct, sharpe, drawdown, symbol_returns, scores.
    """
    import vectorbt as vbt

    # ------------------------------------------------------------------
    # 1. Determine lookback days
    # ------------------------------------------------------------------
    if momentum_definition == "12_1":
        lookback_days = 252
    else:
        lookback_days = max(
            DEFAULT_LOOKBACK_MOM, DEFAULT_LOOKBACK_VOL, DEFAULT_LOOKBACK_REV
        )

    weight_mom, weight_vol, weight_rev = weights

    # ------------------------------------------------------------------
    # 2. Generate month-end rebalance dates
    # ------------------------------------------------------------------
    rebalance_dates = pd.date_range(start, end, freq="BME")

    # ------------------------------------------------------------------
    # 3. Per-date scoring loop
    # ------------------------------------------------------------------
    period_scores: dict[pd.Timestamp, pd.DataFrame] = {}

    for date in rebalance_dates:
        # a. Slice data_dfs to only include data up to this date
        period_data: dict[str, pd.DataFrame] = {}
        for sym, df in data_dfs.items():
            sliced = df.loc[df.index <= date]
            if not sliced.empty:
                period_data[sym] = sliced

        # b. Keep only symbols with enough history for the chosen lookback
        eligible: dict[str, pd.DataFrame] = {
            sym: df
            for sym, df in period_data.items()
            if len(df) >= lookback_days
        }

        if not eligible:
            continue

        # c. Score using the appropriate scorer
        if momentum_definition == "12_1":
            from src.research.research_scoring import score_research_universe

            scored = score_research_universe(
                eligible,
                top_n=top_n,
                weight_mom=weight_mom,
                weight_vol=weight_vol,
                weight_rev=weight_rev,
                momentum_definition="12_1",
            )
        else:
            scored = score_universe(
                eligible,
                top_n=top_n,
                weight_mom=weight_mom,
                weight_vol=weight_vol,
                weight_rev=weight_rev,
            )

        if scored.empty:
            continue

        # d. Reversal filter (if configured)
        if reversal_filter_params is not None:
            from src.research.reversal_filter import apply_reversal_filter

            filtered_result = apply_reversal_filter(
                scored, eligible, reversal_filter_params
            )
            scored = filtered_result["filtered_scores"]

        period_scores[date] = scored

    # Edge case: no periods scored
    if not period_scores:
        return {
            "return_pct": 0.0,
            "sharpe": 0.0,
            "drawdown": 0.0,
            "symbol_returns": {},
            "scores": pd.DataFrame(),
        }

    # ------------------------------------------------------------------
    # 4. Build orders from scored periods
    # ------------------------------------------------------------------
    orders = build_orders(period_scores, top_n, commission_rate, slippage_pct)

    if orders.empty:
        return {
            "return_pct": 0.0,
            "sharpe": 0.0,
            "drawdown": 0.0,
            "symbol_returns": {},
            "scores": period_scores.get(
                max(period_scores.keys()), pd.DataFrame()
            ),
        }

    # ------------------------------------------------------------------
    # 5. Build close price matrix
    # ------------------------------------------------------------------
    all_symbols: set[str] = set()
    for df in period_scores.values():
        all_symbols.update(df["symbol"].tolist())

    close_prices = pd.DataFrame(
        {
            sym: data_dfs[sym]["Close"]
            for sym in all_symbols
            if sym in data_dfs
        }
    )
    close_prices = close_prices.sort_index()

    if close_prices.empty:
        return {
            "return_pct": 0.0,
            "sharpe": 0.0,
            "drawdown": 0.0,
            "symbol_returns": {},
            "scores": period_scores.get(
                max(period_scores.keys()), pd.DataFrame()
            ),
        }

    # Align order matrices with close price index
    order_symbols = sorted(all_symbols & set(close_prices.columns))
    idx = close_prices.index

    size = pd.DataFrame(np.nan, index=idx, columns=order_symbols)
    price = pd.DataFrame(np.nan, index=idx, columns=order_symbols)
    fees = pd.DataFrame(0.0, index=idx, columns=order_symbols)

    for _, o in orders.iterrows():
        sym = o["symbol"]
        date = o["date"]
        if sym in size.columns and date in size.index:
            size.loc[date, sym] = o["size"]
            price.loc[date, sym] = o["price"]
            fees.loc[date, sym] = o["fees"]

    # ------------------------------------------------------------------
    # 6. Run vectorbt portfolio simulation
    # ------------------------------------------------------------------
    portfolio = vbt.Portfolio.from_orders(
        close=close_prices[order_symbols],
        size=size,
        size_type="targetpercent",
        price=price,
        fees=fees,
        freq="D",
        cash_sharing=True,
        init_cash=initial_cash,
        group_by=True,
        call_seq="auto",
    )

    # ------------------------------------------------------------------
    # 7. Slice returns to evaluation window (if specified)
    # ------------------------------------------------------------------
    if evaluation_start is not None and evaluation_end is not None:
        eval_returns = portfolio.returns().loc[evaluation_start:evaluation_end]
    else:
        eval_returns = portfolio.returns()

    # ------------------------------------------------------------------
    # 8. Extract metrics
    # ------------------------------------------------------------------
    if eval_returns.empty:
        return_pct = 0.0
    else:
        return_pct = float(eval_returns.sum() * 100)

    stats = portfolio.stats()
    sharpe = float(stats.get("Sharpe Ratio", 0.0) or 0.0)
    drawdown = float(stats.get("Max Drawdown [%]", 0.0) or 0.0)

    # ------------------------------------------------------------------
    # 9. Symbol-level returns (from positions records)
    # ------------------------------------------------------------------
    symbol_returns: dict[str, float] = {}
    try:
        cols = close_prices.columns.tolist()
        for _, record in portfolio.positions.records.iterrows():
            col_idx = record["col"]
            symbol = cols[col_idx]
            ret = record["return"]
            if not pd.isna(ret):
                ret_pct = float(ret) * 100
                if symbol in symbol_returns:
                    symbol_returns[symbol] += ret_pct
                else:
                    symbol_returns[symbol] = ret_pct
    except Exception:  # noqa: BLE001
        symbol_returns = {}

    # ------------------------------------------------------------------
    # 10. Return metrics dict
    # ------------------------------------------------------------------
    return {
        "return_pct": return_pct,
        "sharpe": sharpe,
        "drawdown": drawdown,
        "symbol_returns": symbol_returns,
        "scores": period_scores.get(
            max(period_scores.keys()), pd.DataFrame()
        ),
    }
