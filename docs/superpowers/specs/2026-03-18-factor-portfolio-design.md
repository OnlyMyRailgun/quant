# Factor-Based Portfolio Strategy Design

## Objective
To evolve the system from single-asset threshold trading (e.g., "buy if SMA crosses") to a true institutional quantitative framework. This requires implementing a **Cross-Sectional Factor Engine** that ranks stocks periodically and rebalances the portfolio to own only the top-scoring components.

## Architecture

We will create a new strategy class: `src/strategies/momentum_factor.py` (which serves as our first factor base template).

### 1. The Factor: Cross-Sectional Momentum
Instead of absolute prices, the strategy evaluates the momentum factor of every stock in the trading universe.
* **Metric:** 90-day return percentage `(Current Price - Price 90 days ago) / Price 90 days ago`.
* **Selection:** At the end of every month, rank all active stocks. Pick the **Top N** (e.g., Top 3 out of the TOPIX 10 universe).

### 2. Time-Series Schedulers (Monthly Rebalance)
A traditional `Backtrader` strategy evaluates indicators every single day (`next()` method). Institutional portfolios only rebalance weekly or monthly to avoid horrific transaction costs (friction).
* We will use Backtrader's `timer` or explicitly track the month in the `next()` loop to execute logic *only* on the first trading day of a new month.

### 3. Portfolio Allocation & Execution
Once the Top N stocks are identified:
* **Target Weights:** 1 / N of available capital for each selected stock (Equal Weighting).
* **Sell Process:** The system must scan the current portfolio. If we own a stock that has fallen out of the Top N, we issue a `close()` order to liquidate it completely.
* **Buy/Adjust Process:** For stocks inside the new Top N, we calculate the target monetary value (`broker.get_value() / N`) and execute `order_target_value()` to gracefully buy the necessary shares or re-adjust existing holdings if they drifted.

## Trade-offs and Constraints

* **Order of Execution Danger:** Selling and buying on the same tick can lead to margin errors if cash hasn't settled. Backtrader's `cheat_on_close` or specific order sequences might be needed. For MVP, we will issue all rebalance orders simultaneously and let Backtrader's broker resolve them, assuming standard cash accounts.
* **Slippage Impact:** Monthly rebalancing with 10 stocks is safe. With 100+ stocks, rebalancing 30 names at once incurs heavy slippage relative to capital. We keep the friction models active to simulate this realistically.
* **Whipsaws:** A stock might flip between #3 and #4 rank multiple months in a row, costing us commission each time without gaining trend. A future version might require a "buffer" (e.g., only sell if it drops below #5). We will ignore this optimization for the MVP.

## Next Implementation Steps
1. Create `src/strategies/momentum_factor.py`.
2. Implement custom `next()` logic that checks for month-over-month rollovers.
3. Calculate ranks across `self.datas`.
4. Fire `order_target_percent(data, target=1.0/N)` on Top N stocks and `order_target_percent(data, target=0.0)` on the rest.
5. Update `src/main.py` entry point to accept a `--strategy momentum` flag to hot-swap between strategies.
