import backtrader as bt
import pandas as pd
from collections.abc import Mapping
from typing import Dict, Any
from src.engine.commission import JapanStockCommission, load_live_slippage


def _strategy_param_names(strategy_class) -> set[str]:
    params = getattr(strategy_class, "params", None)
    if params is None:
        return set()
    if isinstance(params, Mapping):
        return set(params)
    if hasattr(params, "_getkeys"):
        return set(params._getkeys())
    return {
        name
        for name in dir(params)
        if not name.startswith("_")
    }


def _filter_strategy_kwargs(strategy_class, kwargs: dict[str, Any]) -> dict[str, Any]:
    param_names = _strategy_param_names(strategy_class)
    if not param_names:
        return {}
    return {
        key: value
        for key, value in kwargs.items()
        if key in param_names
    }


def _strategy_param_value(
    strategy_class,
    strategy_kwargs: dict[str, Any],
    name: str,
    default,
):
    if name in strategy_kwargs:
        return strategy_kwargs[name]
    params = getattr(strategy_class, "params", None)
    return getattr(params, name, default) if params is not None else default


def _date_bounds(
    data_dfs: dict[str, pd.DataFrame],
    start: str | None,
    end: str | None,
) -> tuple[str, str]:
    if start is not None and end is not None:
        return start, end

    date_indexes = [
        df.index
        for df in data_dfs.values()
        if df is not None and not df.empty and isinstance(df.index, pd.DatetimeIndex)
    ]
    if not date_indexes:
        raise ValueError("run_backtest requires datetime-indexed data or explicit start/end")

    inferred_start = min(index.min() for index in date_indexes).strftime("%Y-%m-%d")
    inferred_end = max(index.max() for index in date_indexes).strftime("%Y-%m-%d")
    return start or inferred_start, end or inferred_end


def _execution_params(strategy_class, strategy_kwargs: dict[str, Any]) -> tuple[int, tuple[float, ...]]:
    top_n = int(_strategy_param_value(strategy_class, strategy_kwargs, "top_n", 3))
    weights = (
        float(_strategy_param_value(strategy_class, strategy_kwargs, "weight_mom", 1.0)),
        float(_strategy_param_value(strategy_class, strategy_kwargs, "weight_vol", 1.0)),
        float(_strategy_param_value(strategy_class, strategy_kwargs, "weight_rev", 1.0)),
        float(_strategy_param_value(strategy_class, strategy_kwargs, "weight_val", 0.0)),
        float(_strategy_param_value(strategy_class, strategy_kwargs, "weight_qual", 0.0)),
    )
    return top_n, weights

def run_backtest(
    data_dfs: dict[str, pd.DataFrame],
    strategy_class,
    initial_cash=1000000.0,
    commission=0.001,
    slippage=None,
    engine="backtrader",
    momentum_definition="90d",
    reversal_filter_params=None,
    start: str | None = None,
    end: str | None = None,
    strategy_kwargs: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Sets up and runs a short backtest using Backtrader or Vectorbt.

    Args:
        data_dfs: Dict mapping symbol names to historical stock DataFrames.
        strategy_class: The Backtrader strategy class to use.
        initial_cash: Starting capital.
        commission: Commission rate, defaults to 0.1% (real JP approx).
        slippage: Slippage percentage. If None, auto-loads from paper trader feedback loop
                  (friction.json), falling back to 0.05% if no live data exists.
        engine: Backtesting engine ("backtrader" or "vectorbt").
        momentum_definition: Momentum definition ("90d" or "12_1").
        reversal_filter_params: Optional reversal filter parameters.
        start: Optional explicit backtest start date for non-Backtrader engines.
        end: Optional explicit backtest end date for non-Backtrader engines.
        strategy_kwargs: Optional strategy parameter overrides.
    """
    strategy_kwargs = dict(strategy_kwargs or {})

    if engine == "simple":
        from src.engine.simple_runner import run_backtest_simple

        top_n, weights = _execution_params(strategy_class, strategy_kwargs)
        start_date, end_date = _date_bounds(data_dfs, start, end)

        result = run_backtest_simple(
            data_dfs=data_dfs,
            start=start_date,
            end=end_date,
            weights=weights,
            top_n=top_n,
            initial_cash=initial_cash,
            momentum_definition=momentum_definition,
            reversal_filter_params=reversal_filter_params,
        )

        metrics = {
            "final_value": initial_cash * (1 + result.get("return_pct", 0.0) / 100.0),
            "sharpe": result.get("sharpe", 0.0),
            "max_drawdown": result.get("drawdown", 0.0),
            "total_return": result.get("return_pct", 0.0) / 100.0,
            "rebalance_count": 0,
            "position_change_count": 0,
            "turnover_ratio": 0.0,
        }
        return {"metrics": metrics, "cerebro": result}

    if engine == "vectorbt":
        from src.engine.vectorbt_runner import run_backtest_vectorbt

        top_n, weights = _execution_params(strategy_class, strategy_kwargs)
        start_date, end_date = _date_bounds(data_dfs, start, end)

        effective_slippage = slippage if slippage is not None else 0.0

        result = run_backtest_vectorbt(
            data_dfs=data_dfs,
            start=start_date,
            end=end_date,
            weights=weights,
            top_n=top_n,
            initial_cash=initial_cash,
            commission_rate=commission,
            slippage_pct=effective_slippage,
            momentum_definition=momentum_definition,
            reversal_filter_params=reversal_filter_params,
        )

        metrics = {
            "final_value": initial_cash
            * (1 + result.get("return_pct", 0.0) / 100.0),
            "sharpe": result.get("sharpe", 0.0),
            "max_drawdown": result.get("drawdown", 0.0),
            "total_return": result.get("return_pct", 0.0) / 100.0,
            "rebalance_count": 0,
            "position_change_count": 0,
            "turnover_ratio": 0.0,
        }
        return {"metrics": metrics, "cerebro": result}

    cerebro = bt.Cerebro()
    
    # Add Strategy
    cerebro.addstrategy(
        strategy_class,
        **_filter_strategy_kwargs(strategy_class, strategy_kwargs),
    )
    
    # Add each symbol's data as a separate feed
    for symbol, df in data_dfs.items():
        data_feed = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data_feed, name=symbol)
    
    # Set Cash & Broker Frictions
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.addcommissioninfo(JapanStockCommission())
    
    # Dynamically load live-calibrated slippage from Paper Trader feedback loop
    effective_slippage = slippage if slippage is not None else load_live_slippage()
    cerebro.broker.set_slippage_perc(effective_slippage)
    
    # Analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    
    # Run
    strats = cerebro.run()
    strat = strats[0]
    
    metrics = {
        "final_value": cerebro.broker.getvalue(),
        "sharpe": strat.analyzers.sharpe.get_analysis().get('sharperatio', 0.0),
        "max_drawdown": strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0.0),
        "total_return": strat.analyzers.returns.get_analysis().get('rtot', 0.0),
        "rebalance_count": getattr(strat, "rebalance_count", 0),
        "position_change_count": getattr(strat, "position_change_count", 0),
        "turnover_ratio": getattr(strat, "turnover_ratio", 0.0),
    }
    
    return {"metrics": metrics, "cerebro": cerebro}
