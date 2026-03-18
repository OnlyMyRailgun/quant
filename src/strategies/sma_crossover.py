import backtrader as bt

class SmaCross(bt.Strategy):
    """A simple moving average crossover strategy for testing."""
    params = dict(
        pfast=10,   # period for the fast moving average
        pslow=30,   # period for the slow moving average
        stake=0.95  # fraction of available cash to use per trade
    )

    def __init__(self):
        sma1 = bt.ind.SMA(period=self.p.pfast)
        sma2 = bt.ind.SMA(period=self.p.pslow)
        self.crossover = bt.ind.CrossOver(sma1, sma2)

    def next(self):
        if not self.position:
            if self.crossover > 0:
                # Calculate how many whole shares we can afford with stake% of cash
                available_cash = self.broker.get_cash() * self.p.stake
                price = self.data.close[0]
                size = int(available_cash / price)
                if size > 0:
                    self.buy(size=size)
        elif self.crossover < 0:
            self.close()
