import backtrader as bt
import pandas as pd
from typing import Type, Dict, Any
from src.engine.commission import JapanStockCommission, load_live_slippage

def run_backtest(data_dfs: dict[str, pd.DataFrame], strategy_class, initial_cash=1000000.0, commission=0.001, slippage=None) -> Dict[str, Any]:
    """
    Sets up and runs a short backtest using Backtrader.
    
    Args:
        data_dfs: Dict mapping symbol names to historical stock DataFrames.
        strategy_class: The Backtrader strategy class to use.
        initial_cash: Starting capital.
        commission: Commission rate, defaults to 0.1% (real JP approx).
        slippage: Slippage percentage. If None, auto-loads from paper trader feedback loop
                  (friction.json), falling back to 0.05% if no live data exists.
    """
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
        "total_return": strat.analyzers.returns.get_analysis().get('rtot', 0.0)
    }
    
    return {"metrics": metrics, "cerebro": cerebro}
