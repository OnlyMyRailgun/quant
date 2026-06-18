import backtrader as bt
import pandas as pd
from typing import Type, Dict, Any
from src.engine.commission import JapanStockCommission, load_live_slippage

def run_backtest(
    data_dfs: dict[str, pd.DataFrame],
    strategy_class,
    initial_cash=1000000.0,
    commission=0.001,
    slippage=None,
    engine="backtrader",
    momentum_definition="90d",
    reversal_filter_params=None,
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
    """
    if engine == "simple":
        from src.engine.simple_runner import run_backtest_simple

        params = getattr(strategy_class, "params", None)
        top_n = getattr(params, "top_n", 3) if params is not None else 3
        weight_mom = getattr(params, "weight_mom", 1.0) if params is not None else 1.0
        weight_vol = getattr(params, "weight_vol", 1.0) if params is not None else 1.0
        weight_rev = getattr(params, "weight_rev", 1.0) if params is not None else 1.0

        earliest = min(df.index.min() for df in data_dfs.values() if not df.empty)
        latest = max(df.index.max() for df in data_dfs.values() if not df.empty)

        result = run_backtest_simple(
            data_dfs=data_dfs,
            start=earliest.strftime("%Y-%m-%d"),
            end=latest.strftime("%Y-%m-%d"),
            weights=(weight_mom, weight_vol, weight_rev),
            top_n=top_n,
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

        params = getattr(strategy_class, "params", None)
        top_n = getattr(params, "top_n", 3) if params is not None else 3
        weight_mom = getattr(params, "weight_mom", 1.0) if params is not None else 1.0
        weight_vol = getattr(params, "weight_vol", 1.0) if params is not None else 1.0
        weight_rev = getattr(params, "weight_rev", 1.0) if params is not None else 1.0

        earliest = min(
            df.index.min() for df in data_dfs.values() if not df.empty
        )
        latest = max(
            df.index.max() for df in data_dfs.values() if not df.empty
        )
        start = earliest.strftime("%Y-%m-%d")
        end = latest.strftime("%Y-%m-%d")

        effective_slippage = slippage if slippage is not None else 0.0

        result = run_backtest_vectorbt(
            data_dfs=data_dfs,
            start=start,
            end=end,
            weights=(weight_mom, weight_vol, weight_rev),
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
    cerebro.addstrategy(strategy_class)
    
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
