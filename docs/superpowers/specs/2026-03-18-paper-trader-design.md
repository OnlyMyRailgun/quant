# Live Paper Trading & Feedback Loop System

## Objective
To build a "Live Signal Generator" that runs daily via Cron, connected to a local SQLite database that tracks virtual portfolio cash and positions. It also establishes the **Implementation Shortfall Feedback Loop** to measure real market transaction slippage and feed it automatically back into the engine's backtesting friction models.

## The Feedback Loop Design (How it works without API)

When you run a Backtest, Backtrader assumes it filled your execution at Yahoo Finance's exact `Close` or `Open` price (e.g., ¥2500).
In the real world, you might buy it manually on your phone the next morning at ¥2510. That ¥10 difference is the **Implementation Shortfall (Slippage)**.

1. **Signal Generation (Daily Cron)**
   The bot reads all data up to *today*. If it's a rebalance day, it registers a `PENDING` order in `paper_trade.db` with the `theoretical_price` (today's close).
   
2. **Execution Recording (The Real World Hook)**
   You run a command like: `python3 src/paper/bot.py fill 7203.T 2510`.
   This marks the order `FILLED` at your *actual* phone price.

3. **The Anti-Fragile Feedback Loop**
   The system calculates the gap: `(2510 - 2500) / 2500 = 0.4% slippage`.
   It automatically updates `.data_cache/friction.json` with the new historical average slippage rate.
   The next time you run `src/main.py` or `src/optimize.py` to evaluate your factor weights, the system **automatically drops the naive 0.05% slippage assumption and replaces it with your real 0.4% penalty**, radically altering your strategy's projected profitability to match your pure reality!

## Database Schema (SQLite)

**Table: `portfolio`**
- `symbol` (TEXT) PRIMARY KEY
- `shares` (INTEGER)
- `avg_price` (REAL)

**Table: `orders`**
- `id` (INTEGER) PRIMARY KEY
- `date` (TEXT)
- `symbol` (TEXT)
- `action` (TEXT) BUY/SELL
- `target_shares` (INTEGER)
- `theoretical_price` (REAL)
- `actual_price` (REAL) nullable
- `slippage_pct` (REAL) nullable
- `status` (TEXT) PENDING/FILLED/CANCELED

**Table: `cash`**
- `balance` (REAL)

## Architecture Changes
1. **`src/paper/bot.py`**: The CLI entry point mimicking the daily Cron execution.
2. **`src/paper/db.py`**: SQLite CRUD operations.
3. **`src/engine/commission.py`**: Will be refactored to read default slippage from `friction.json` if it exists, dynamically responding to the paper trader's outcomes.
