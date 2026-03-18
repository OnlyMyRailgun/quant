import pytest
import backtrader as bt
from src.strategies.sma_crossover import SmaCross

def test_sma_crossover_strategy_init():
    cerebro = bt.Cerebro()
    cerebro.addstrategy(SmaCross, pfast=10, pslow=30)
    # Just verifying it can be instantiated without crashing
    assert len(cerebro.strats) == 1
