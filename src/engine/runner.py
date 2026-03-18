import backtrader as bt
import pandas as pd
from typing import Type, Dict, Any
from src.engine.commission import JapanStockCommission

def run_backtest(data_df: pd.DataFrame, strategy_class: Type[bt.Strategy], initial_cash: float = 1000000.0) -> Dict[str, Any]:
    cerebro = bt.Cerebro()
    
    # Add Strategy
    cerebro.addstrategy(strategy_class)
    
    # Add Data
    data = bt.feeds.PandasData(dataname=data_df)
    cerebro.adddata(data)
    
    # Set Cash & Broker Frictions
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.addcommissioninfo(JapanStockCommission())
    # Add simple slippage: 0.05%
    cerebro.broker.set_slippage_perc(0.0005)
    
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
