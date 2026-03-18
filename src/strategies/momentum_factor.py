import math
import backtrader as bt

class CrossSectionalMomentum(bt.Strategy):
    """
    Evaluates momentum (n-day return) across all provided data feeds.
    Rebalances the portfolio on the first trading day of the month to hold the top N stocks.
    """
    params = dict(
        lookback=90,     # Trading days for momentum calculation (roughly 4-5 months)
        top_n=3,         # Number of stocks to hold in the portfolio
    )

    def __init__(self):
        self.month = None
        self.momentum_indicators = {}
        
        # Instantiate momentum indicator for every stock in the universe
        for d in self.datas:
            # RateOfChange is (Close - Close_N_days_ago) / Close_N_days_ago * 100
            self.momentum_indicators[d] = bt.ind.RateOfChange(d.close, period=self.p.lookback)

    def next(self):
        # We want to rebalance once a month.
        # The easiest approach is to detect when the month changes index.
        current_month = self.data.datetime.date(0).month
        
        if self.month is None:
            self.month = current_month
            return
            
        # If the month has changed, execute our rebalance logic
        if current_month != self.month:
            self.month = current_month
            self.rebalance()

    def rebalance(self):
        """Rank stocks by momentum and adjust portfolio weights."""
        valid_stocks = []
        for d in self.datas:
            # Check if we have enough historical data to generate a valid momentum score
            if len(d) >= self.p.lookback and not math.isnan(self.momentum_indicators[d][0]):
                valid_stocks.append(d)
                
        # Scored and rank (highest momentum first)
        valid_stocks.sort(key=lambda d: self.momentum_indicators[d][0], reverse=True)
        
        # Select our Top N winners
        top_stocks = valid_stocks[:self.p.top_n]
        
        # Execution Phase 1: Liquidate losers (stocks we own that fell out of the Top N)
        for d in self.datas:
            pos = self.getposition(d)
            if pos.size > 0 and d not in top_stocks:
                self.close(data=d)
                
        # Execution Phase 2: Buy/Adjust the winners
        if top_stocks:
            # Target equal weight for all components.
            # We use 0.95 (95% of account) instead of 1.0 to leave a cash buffer for transaction fees.
            target_weight = 0.95 / len(top_stocks)
            for d in top_stocks:
                # order_target_percent automatically calculates the shares needed to reach the target weight
                self.order_target_percent(data=d, target=target_weight)
