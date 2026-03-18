# Quant Backtest Visual Charting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create an executable entry point (`src/main.py`) that wires together the existing data loader, engine, and strategies, runs an end-to-end backtest, and plots the results interactively.

**Architecture:** We will add `matplotlib` to our dependencies context. Then, create a `main.py` script that acts as the entry orchestrator. It uses `yfinance_loader` to fetch absolute dates, invokes the `run_backtest` engine, prints cleanly formatted CLI metrics, and finally calls `cerebro.plot()` to bring up the visual companion chart.

**Tech Stack:** Python 3.10+, `backtrader`, `pandas`, `yfinance`, `matplotlib`.

---

### Task 1: Add Matplotlib Dependency

**Files:**
- Modify: `requirements.txt:1-4`

- [ ] **Step 1: Write the failing test**

*(No test needed for a pure dependency addition, but we verify environment works)*
Run: `python3 -c "import matplotlib"`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 2: Write minimal implementation**

Modify `requirements.txt` to include `matplotlib`:
```text
matplotlib>=3.7.0
```

- [ ] **Step 3: Run to verify**

Run: `pip install -r requirements.txt && python3 -c "import matplotlib"`
Expected: PASS with no output.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add matplotlib for backtrader charting support"
```

---

### Task 2: Implement Main Execution Orchestrator

**Files:**
- Create: `src/main.py`
- Test: (We will rely on an end-to-end integration test run since there are no discrete unit borders for the CLI script)

- [ ] **Step 1: Write the minimal implementation**

Create `src/main.py`:

```python
import argparse
import sys
from src.data.yfinance_loader import fetch_daily_data
from src.strategies.sma_crossover import SmaCross
from src.engine.runner import run_backtest

def main():
    parser = argparse.ArgumentParser(description="Run Quant Backtest and Plot Results")
    parser.add_argument("--ticker", type=str, default="7203.T", help="Ticker symbol (default: Toyota 7203.T)")
    parser.add_argument("--start", type=str, default="2023-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2024-01-01", help="End date (YYYY-MM-DD)")
    parser.add_argument("--no-plot", action="store_true", help="Disable plotting (useful for CI)")
    
    args = parser.parse_args()

    print(f"Fetching data for {args.ticker} from {args.start} to {args.end}...")
    try:
        data_df = fetch_daily_data(args.ticker, args.start, args.end)
        if data_df.empty:
            print("Error: No data fetched. Please check the ticker or date range.")
            sys.exit(1)
    except Exception as e:
        print(f"Failed to fetch data: {e}")
        sys.exit(1)

    print("Running backtest using SmaCross strategy with friction modeling...")
    results = run_backtest(data_df, SmaCross, initial_cash=1000000.0)
    
    metrics = results["metrics"]
    cerebro = results["cerebro"]

    print("\n" + "="*40)
    print("BACKTEST RESULTS")
    print("="*40)
    print(f"Initial Capital : ¥1,000,000.00")
    print(f"Final Capital   : ¥{metrics['final_value']:,.2f}")
    print(f"Total Return    : {metrics['total_return']*100:.2f}%")
    print(f"Max Drawdown    : {metrics['max_drawdown']:.2f}%")
    print(f"Sharpe Ratio    : {metrics['sharpe']:.4f}")
    print("="*40 + "\n")

    if not args.no_plot:
        print("Rendering chart...")
        # Backtrader uses matplotlib under the hood
        # Set style to 'bar' or 'candle' for better visibility if needed, but default is fine.
        cerebro.plot(style='bar')

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run test to verify it works (headless mode)**

Run: `PYTHONPATH=. python3 src/main.py --no-plot`
Expected: Passes without errors, prints the backtest results block showing data fetching, execution, and final value.

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: add main entry point script with cli reporting and charting"
```
