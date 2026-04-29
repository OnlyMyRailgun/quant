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
    # 2. Generate execution dates (month-start = BMS)
    #    Score using data available at the END of the prior month,
    #    then execute at the first trading day of the new month.
    #    This matches real-world: you score after market close on the
    #    last day of month N, then trade on the first day of month N+1.
    # ------------------------------------------------------------------
    exec_dates = pd.date_range(start, end, freq="BMS")

    # ------------------------------------------------------------------
    # 3. Per-date scoring loop
    # ------------------------------------------------------------------
    period_scores: dict[pd.Timestamp, pd.DataFrame] = {}

    for exec_date in exec_dates:
        # a. Score using data strictly BEFORE the execution date
        period_data: dict[str, pd.DataFrame] = {}
        for sym, df in data_dfs.items():
            sliced = df.loc[df.index < exec_date]
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

        period_scores[exec_date] = scored

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
    # 4b. Fill actual execution prices from the BMS date
    #     build_orders() leaves price=NaN; we look up the real close
    #     at each order's execution date from the data. This prevents
    #     using the scoring-date close (look-ahead bias).
    # ------------------------------------------------------------------
    for idx, o in orders.iterrows():
        sym = o["symbol"]
        exec_date = o["date"]
        df = data_dfs.get(sym)
        if df is not None and "Close" in df.columns:
            mask = df.index >= exec_date
            if mask.any():
                orders.at[idx, "price"] = float(df.loc[mask, "Close"].iloc[0])

    # Drop any orders that still have NaN price (symbol not in data)
    orders = orders.dropna(subset=["price"])

    if orders.empty:
        return {
            "return_pct": 0.0, "sharpe": 0.0, "drawdown": 0.0,
            "symbol_returns": {}, "scores": pd.DataFrame(),
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

    for _, o in orders.iterrows():
        sym = o["symbol"]
        date = o["date"]
        if sym in size.columns and date in size.index:
            size.loc[date, sym] = o["size"]
            price.loc[date, sym] = o["price"]

    # ------------------------------------------------------------------
    # 6. Run vectorbt portfolio simulation
    #    For target-percentage orders, pass commission as scalar rate
    #    (absolute fees per order would be near-zero decimals that
    #     vectorbt can't interpret correctly)
    # ------------------------------------------------------------------
    portfolio = vbt.Portfolio.from_orders(
        close=close_prices[order_symbols],
        size=size,
        size_type="targetpercent",
        price=price,
        fees=commission_rate,
        freq="D",
        cash_sharing=True,
        init_cash=initial_cash,
        group_by=True,
        call_seq="auto",
    )

    # ------------------------------------------------------------------
    # 7. Slice returns to evaluation window (if specified)
    # ------------------------------------------------------------------
    # Use portfolio.total_return() for correct compound return.
    # Do NOT use portfolio.returns().sum() which gives arithmetic (not
    # geometric) return.
    # ------------------------------------------------------------------
    eval_start = evaluation_start or start
    eval_end = evaluation_end or end

    # Compute total return over the evaluation window by slicing value
    portfolio_value = portfolio.value()
    if isinstance(portfolio_value, pd.DataFrame):
        portfolio_value = portfolio_value.iloc[:, 0]

    window_values = portfolio_value.loc[eval_start:eval_end]
    if window_values.empty or len(window_values) < 2:
        return_pct = 0.0
    else:
        start_val = float(window_values.iloc[0])
        end_val = float(window_values.iloc[-1])
        if start_val > 0:
            return_pct = round(((end_val / start_val) - 1.0) * 100, 4)
        else:
            return_pct = 0.0

    # ------------------------------------------------------------------
    # 8. Compute Sharpe manually to match Backtrader formula:
    #    mean(daily_returns) / std(ddof=0) * sqrt(252)
    # ------------------------------------------------------------------
    daily_returns = portfolio.returns().dropna()
    if len(daily_returns) > 1 and daily_returns.std(ddof=0) > 0:
        sharpe = float(daily_returns.mean() / daily_returns.std(ddof=0) * np.sqrt(252))
    else:
        sharpe = 0.0

    # ------------------------------------------------------------------
    # 9. Extract drawdown from portfolio stats
    # ------------------------------------------------------------------
    stats = portfolio.stats()
    drawdown = float(stats.get("Max Drawdown [%]", 0.0) or 0.0)

    # ------------------------------------------------------------------
    # 10. Symbol-level returns (from positions records)
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
    # 11. Return metrics dict
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
