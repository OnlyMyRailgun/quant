# Quant Backtest Scaffold - Visual Charting (MVP)

## Objective
To provide an end-to-end, visually intuitive experience of what a quantitative trading system does by connecting the existing data fetcher, customized friction model (commission/slippage), simple strategy, and a new execution script that generates a visual chart of the trades and portfolio equity curve.

## Approach: CLI Report + Visual Charting (Option 2)

This approach focuses on rapid feedback and intuitive understanding by leveraging `matplotlib` and `backtrader`'s native plotting capabilities to show exactly when trades occur and how account value changes over time.

### System Architecture Changes

1.  **Dependencies Update**
    *   Add `matplotlib` to `requirements.txt` to enable the plotting backend.

2.  **Runner Execution Script (`src/main.py`)**
    *   Create a new entry point script.
    *   **Data Fetching**: Hook into `src.data.yfinance_loader` to fetch an example Japanese stock (e.g., Toyota `7203.T`) or a familiar US stock (e.g., Apple `AAPL`) from `2023-01-01` to `2024-01-01`.
    *   **Engine Execution**: Pass the fetched data to `src.engine.runner.run_backtest`.
    *   **Reporting**: Print out a clear, human-readable terminal report summarizing Initial Capital, Final Capital, Total Return (%), Max Drawdown, and Sharpe Ratio.
    *   **Charting**: Invoke `cerebro.plot()` (via the returned object from the runner) to render the visual chart upon completion.

### Expected Behavior

*   When the user runs `python src/main.py`, they should see data downloading briefly.
*   A clean text block will output in the terminal detailing the backtest metrics.
*   A window will automatically open displaying the Backtrader interactive chart:
    *   Top panel: Portfolio value curve (Equity).
    *   Middle panel: Price data with the SMA lines and red/green triangle markers indicating sell/buy signals.
    *   Bottom panel(s): Volume.

### Constraints / Future-Proofing

*   We continue to use the hardcoded `1,000,000` capital and `0.001` (0.1%) commission rate established in the scaffold.
*   The charting functionality might fail in purely headless environments (like standard CI pipelines), so the plotting call should ideally accept an argument or be easily disableable if running in headless mode in the future. For this interactive local testing MVP, it will default to showing.
