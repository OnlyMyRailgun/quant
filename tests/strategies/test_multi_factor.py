import backtrader as bt
from src.strategies.multi_factor import UniversalMultiFactor

def test_multi_factor_strategy_init():
    cerebro = bt.Cerebro()
    cerebro.addstrategy(UniversalMultiFactor, lookback_mom=10, lookback_vol=5, top_n=2)
    
    assert len(cerebro.strats) == 1
