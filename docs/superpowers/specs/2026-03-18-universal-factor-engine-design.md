# Universal Multi-Factor Strategy Design

## Objective
To build a single, unified "Scoring Engine" that calculates multiple alpha factors for every stock in the universe. By adjusting the weight of each factor dynamically, this single strategy can simulate pure Momentum, pure Volatility, pure Mean Reversion, or any hybrid combination.

## Architectural Insight (The "Weighted Score" Method)

Instead of hardcoding `cross_sectional_momentum.py` and `low_volatility.py` as entirely separate trading strategies, we implement a **Universal Factor Engine**.

**The calculation per stock at the end of each month:**
1. Calculate Factor A score (e.g. 90-day momentum).
2. Calculate Factor B score (e.g. 20-day volatility -> invert it so lower is better).
3. Calculate Factor C score (e.g. 20-day mean reversion distance).
4. **Normalize** these scores (so a 1% daily volatility can be mathematically added to a 15% 90-day return). *For MVP, we will use simple Z-scores (Standardization: `(x - mean) / std`) across the cross-section of stocks.*
5. **Weighted Sum Integration:**
   `Total Score = (Weight_Mom * Z_Mom) + (Weight_Vol * Z_Vol) + (Weight_Rev * Z_Rev)`
6. Rank all stocks by `Total Score`.
7. Execute monthly rebalance (Buy Top N equal weighted, sell losers).

## Backtrader Implementation Strategy

We will replace the existing `CrossSectionalMomentum` with a generalized `MultiFactorStrategy` in `src/strategies/multi_factor.py`.

### Parameters (Flexible Weights):
```python
params = dict(
    lookback_mom=90,
    lookback_vol=20,
    lookback_rev=20,
    weight_mom=1.0,  # 1.0 means 100% Momentum
    weight_vol=0.0,  # 0.0 means ignore Volatility
    weight_rev=0.0,  # 0.0 means ignore Mean Reversion
    top_n=3,
)
```

### 1. Indicators Instantiation (`__init__`)
For each data feed (stock):
* `self.inds[d]['momentum'] = bt.ind.RateOfChange(d.close, period=p.lookback_mom)`
* `self.inds[d]['volatility'] = bt.ind.StdDev(bt.ind.RateOfChange(d.close, period=1), period=p.lookback_vol)`
* `self.inds[d]['reversion'] = (d.close - bt.ind.SMA(d.close, period=p.lookback_rev)) / bt.ind.SMA(d.close, period=p.lookback_rev)` *(Negative is better for buying the dip)*

### 2. Cross-Sectional Z-Score Normalization (`rebalance`)
Because Momentum might be a number like `0.15` (15%) and Volatility might be `0.02` (2%), adding them directly gives Volatility no voting power.
We will calculate the Mean and StdDev of each factor *across all 10 valid stocks* on rebalance day, and convert raw values to **Z-Scores** (how many standard deviations above/below average).

*   `Z_Mom` = `(Mom - Mean_Mom) / Std_Mom`
*   `Z_Vol` = `-(Vol - Mean_Vol) / Std_Vol` *(Negative because we want LOW volatility)*
*   `Z_Rev` = `-(Rev - Mean_Rev) / Std_Rev` *(Negative because we want the ones furthest below their average)*

Then multiply by weights, sort, and execute standard rebalancing mechanism built in previous phase.

## MVP Scope Constraints
* Basic Python standard library `math` and `statistics` functions will be used for Z-scores inside `rebalance`.
* For edge cases (e.g., standard deviation across stocks is 0), default Z-score to 0.
