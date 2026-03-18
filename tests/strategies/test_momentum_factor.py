import backtrader as bt
from src.strategies.momentum_factor import CrossSectionalMomentum

def test_momentum_strategy_init():
    cerebro = bt.Cerebro()
    cerebro.addstrategy(CrossSectionalMomentum, lookback=10, top_n=2)
    # Just asserting it adds to cerebro without failure
    assert len(cerebro.strats) == 1
