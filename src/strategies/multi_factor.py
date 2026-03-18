import math
import statistics
import backtrader as bt

class UniversalMultiFactor(bt.Strategy):
    """
    Evaluates multiple alphas (Momentum, Volatility, Mean Reversion) for every stock.
    Normalizes the indicators cross-sectionally via Z-Scores on rebalance day.
    Sums the weighted Z-scores into a Total Score per stock.
    Holds the Top N stocks with Equal Weighting.
    """
    params = dict(
        lookback_mom=90,     # Trading days for momentum
        lookback_vol=20,     # Trading days for volatility
        lookback_rev=20,     # Trading days for mean reversion
        weight_mom=1.0,      # Weight of momentum factor
        weight_vol=1.0,      # Weight of low volatility factor (higher score mapped to lower vol)
        weight_rev=1.0,      # Weight of mean reversion factor (higher score mapped to biggest dip)
        top_n=3,             # Top N to hold
    )

    def __init__(self):
        self.month = None
        
        self.inds = {d: {} for d in self.datas}
        
        for d in self.datas:
            # 1. Momentum: Rate of change over lookback
            self.inds[d]['mom'] = bt.ind.RateOfChange(d.close, period=self.p.lookback_mom)
            
            # 2. Volatility: Standard deviation of daily returns
            daily_roc = bt.ind.RateOfChange(d.close, period=1)
            self.inds[d]['vol'] = bt.ind.StdDev(daily_roc, period=self.p.lookback_vol)
            
            # 3. Mean Reversion: Distance from SMA
            sma = bt.ind.SMA(d.close, period=self.p.lookback_rev)
            self.inds[d]['rev'] = (d.close - sma) / sma

    def next(self):
        current_month = self.data.datetime.date(0).month
        if self.month is None:
            self.month = current_month
            return
            
        if current_month != self.month:
            self.month = current_month
            self.rebalance()

    def get_zscores(self, values: list[float], invert: bool = False) -> list[float]:
        """Calculates cross-sectional Z-Scores. Inverts score sign if lower is better."""
        if not values or len(values) < 2:
            return [0.0] * len(values)
            
        mean_val = statistics.mean(values)
        std_val = statistics.stdev(values)
        
        if std_val == 0.0:
            return [0.0] * len(values)
            
        multiplier = -1.0 if invert else 1.0
        return [multiplier * (v - mean_val) / std_val for v in values]

    def rebalance(self):
        valid_stocks = []
        raw_mom = []
        raw_vol = []
        raw_rev = []
        
        # 1. Identify valid universe components for this date
        for d in self.datas:
            mom_v = self.inds[d]['mom'][0]
            vol_v = self.inds[d]['vol'][0]
            rev_v = self.inds[d]['rev'][0]
            
            # Must have all factor metrics available (no NaNs)
            if not (math.isnan(mom_v) or math.isnan(vol_v) or math.isnan(rev_v)):
                valid_stocks.append(d)
                raw_mom.append(mom_v)
                raw_vol.append(vol_v)
                raw_rev.append(rev_v)

        if not valid_stocks:
            return

        # 2. Calculate Cross-Sectional Z-Scores
        # Momentum: Higher is better
        z_mom = self.get_zscores(raw_mom, invert=False)
        # Volatility: Lower is better (we want safe, boring stocks)
        z_vol = self.get_zscores(raw_vol, invert=True)
        # Reversion: Lower is better (stock dumped hard below SMA -> buy the dip)
        z_rev = self.get_zscores(raw_rev, invert=True)

        # 3. Compile Total Scores safely handling dictionary mappings
        total_scores = {}
        for i, d in enumerate(valid_stocks):
            score = (self.p.weight_mom * z_mom[i]) + \
                    (self.p.weight_vol * z_vol[i]) + \
                    (self.p.weight_rev * z_rev[i])
            total_scores[d] = score
            
        # 4. Rank stocks and select Top N
        valid_stocks.sort(key=lambda d: total_scores[d], reverse=True)
        top_stocks = valid_stocks[:self.p.top_n]
        
        # 5. Liquidate losers
        for d in self.datas:
            pos = self.getposition(d)
            if pos.size > 0 and d not in top_stocks:
                self.close(data=d)
                
        # 6. Reallocate to winners
        if top_stocks:
            target_weight = 0.95 / len(top_stocks)
            for d in top_stocks:
                self.order_target_percent(data=d, target=target_weight)
