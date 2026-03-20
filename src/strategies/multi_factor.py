import math
import statistics
import backtrader as bt
import pandas as pd

from src.scoring.multi_factor import score_universe

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

    def _collect_visible_history(self) -> dict[str, pd.DataFrame]:
        history = {}
        for data in self.datas:
            closes = list(data.close.get(size=len(data)))
            datetimes = [
                bt.num2date(value).replace(tzinfo=None)
                for value in data.datetime.get(size=len(data))
            ]
            if not closes or not datetimes:
                continue

            history[data._name] = pd.DataFrame(
                {"Close": closes},
                index=pd.DatetimeIndex(datetimes),
            )

        return history

    def _score_visible_universe(self) -> pd.DataFrame:
        return score_universe(
            self._collect_visible_history(),
            top_n=self.p.top_n,
            weight_mom=self.p.weight_mom,
            weight_vol=self.p.weight_vol,
            weight_rev=self.p.weight_rev,
            lookback_mom=self.p.lookback_mom,
            lookback_vol=self.p.lookback_vol,
            lookback_rev=self.p.lookback_rev,
        )

    def rebalance(self):
        ranked = self._score_visible_universe()
        if ranked.empty:
            return

        data_by_symbol = {data._name: data for data in self.datas}
        top_symbols = ranked.head(self.p.top_n)["symbol"].tolist()
        top_symbol_set = set(top_symbols)
        top_stocks = [data_by_symbol[symbol] for symbol in top_symbols if symbol in data_by_symbol]
        
        # 5. Liquidate losers
        for d in self.datas:
            pos = self.getposition(d)
            if pos.size > 0 and d._name not in top_symbol_set:
                self.close(data=d)
                
        # 6. Reallocate to winners
        if top_stocks:
            target_weight = 0.95 / len(top_stocks)
            for d in top_stocks:
                self.order_target_percent(data=d, target=target_weight)
