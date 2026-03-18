# Quant Backtest Sandbox MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a robust, event-driven backtesting scaffold using Python and Backtrader, incorporating realistic transaction costs (fees, slippage) to provide a safe sandbox for quantitative research before touching real money.

**Architecture:** A modular Python backend using `backtrader` as the core event-driven engine. It fetches mock/historical data via `yfinance` (MVP phase), applies custom commission schemes modeling real-world frictions, and outputs standardized performance metrics (Sharpe, max drawdown). This serves as Stage 1 of the larger 8-layer SaaS trading architecture.

**Tech Stack:** Python 3.10+, `backtrader`, `pandas`, `yfinance`.

---

### Task 1: Setup Project Structure and Dependencies

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`

- [ ] **Step 1: Define dependencies in requirements.txt**

```text
backtrader==1.9.78.123
pandas>=2.0.0
yfinance>=0.2.0
pytest>=7.0.0
```

- [ ] **Step 2: Define pytest configuration in pytest.ini**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 3: Install dependencies locally (optional confirmation step)**

Run: `pip install -r requirements.txt`
Expected: Successful installation.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt pytest.ini
git commit -m "chore: setup initial dependencies for backtest MVP"
```

---

### Task 2: Data Engineering - Historical Data Fetcher

**Files:**
- Create: `src/data/yfinance_loader.py`
- Create: `tests/data/test_yfinance_loader.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
import pandas as pd
from src.data.yfinance_loader import fetch_daily_data

def test_fetch_daily_data_returns_dataframe():
    # Use a well-known ticker like '7203.T' (Toyota) or 'AAPL'
    df = fetch_daily_data("AAPL", start_date="2023-01-01", end_date="2023-01-10")
    
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    # Backtrader expects specific column names
    expected_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    for col in expected_cols:
        assert col in df.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_yfinance_loader.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.data'"

- [ ] **Step 3: Write minimal implementation**

```python
import yfinance as yf
import pandas as pd

def fetch_daily_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetches daily historical data from Yahoo Finance."""
    data = yf.download(ticker, start=start_date, end=end_date, progress=False)
    
    # Handle yfinance multi-index columns if they exist
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
        
    return data
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/data/test_yfinance_loader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/data/yfinance_loader.py tests/data/test_yfinance_loader.py
git commit -m "feat: add yfinance historical data loader"
```

---

### Task 3: Realistic Friction Modeling (Commission & Tax)

**Files:**
- Create: `src/engine/commission.py`
- Create: `tests/engine/test_commission.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from src.engine.commission import JapanStockCommission

def test_japan_stock_commission():
    # Set a fixed commission rate, e.g., 0.1% for Interactive Brokers / Rakuten
    comm_model = JapanStockCommission(commission_rate=0.001)
    
    # price=1000, size=100 -> value = 100,000. Commission = 100
    fee = comm_model._getcommission(size=100, price=1000, pseudoexecprice=1000)
    
    assert fee == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/engine/test_commission.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [ ] **Step 3: Write minimal implementation**

```python
import backtrader as bt

class JapanStockCommission(bt.CommInfoBase):
    """
    Custom Commission model simulating Japanese Stock Trading friction.
    Assumes percentage-based commission.
    """
    params = (
        ('commission', 0.001), # 0.1% default
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_PERC),
    )

    def _getcommission(self, size, price, pseudoexecprice):
        """calculate commission"""
        return abs(size) * price * self.p.commission
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/engine/test_commission.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/engine/commission.py tests/engine/test_commission.py
git commit -m "feat: add percentage-based commission model"
```

---

### Task 4: Base Strategy Template (SMA Run)

**Files:**
- Create: `src/strategies/sma_crossover.py`
- Create: `tests/strategies/test_sma_crossover.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
import backtrader as bt
from src.strategies.sma_crossover import SmaCross

def test_sma_crossover_strategy_init():
    cerebro = bt.Cerebro()
    cerebro.addstrategy(SmaCross, pfast=10, pslow=30)
    # Just verifying it can be instantiated without crashing
    assert len(cerebro.strats) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/strategies/test_sma_crossover.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
import backtrader as bt

class SmaCross(bt.Strategy):
    """A simple moving average crossover strategy for testing."""
    params = dict(
        pfast=10,  # period for the fast moving average
        pslow=30   # period for the slow moving average
    )

    def __init__(self):
        sma1 = bt.ind.SMA(period=self.p.pfast)
        sma2 = bt.ind.SMA(period=self.p.pslow)
        self.crossover = bt.ind.CrossOver(sma1, sma2)

    def next(self):
        if not self.position:
            if self.crossover > 0:
                self.buy()
        elif self.crossover < 0:
            self.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/strategies/test_sma_crossover.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/strategies/sma_crossover.py tests/strategies/test_sma_crossover.py
git commit -m "feat: add basic SMA crossover strategy template"
```

---

### Task 5: Core Backtest Runner

**Files:**
- Create: `src/engine/runner.py`
- Create: `tests/engine/test_runner.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
import pandas as pd
from src.engine.runner import run_backtest
from src.strategies.sma_crossover import SmaCross

def test_run_backtest_execution():
    # Create fake price data
    dates = pd.date_range("2023-01-01", periods=50)
    data = pd.DataFrame({
        'Open': range(100, 150),
        'High': range(101, 151),
        'Low': range(99, 149),
        'Close': range(100, 150),
        'Volume': [1000] * 50
    }, index=dates)
    
    # Run backtest
    results = run_backtest(data, SmaCross, initial_cash=1000000.0)
    
    # Verify results dict contains metrics
    assert "metrics" in results
    assert "final_value" in results["metrics"]
    assert results["metrics"]["final_value"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/engine/test_runner.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
import backtrader as bt
import pandas as pd
from typing import Type, Dict, Any
from src.engine.commission import JapanStockCommission

def run_backtest(data_df: pd.DataFrame, strategy_class: Type[bt.Strategy], initial_cash: float = 1000000.0) -> Dict[str, Any]:
    cerebro = bt.Cerebro()
    
    # Add Strategy
    cerebro.addstrategy(strategy_class)
    
    # Add Data
    data = bt.feeds.PandasData(dataname=data_df)
    cerebro.adddata(data)
    
    # Set Cash & Broker Frictions
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.addcommissioninfo(JapanStockCommission())
    # Add simple slippage: 0.05%
    cerebro.broker.set_slippage_perc(0.0005)
    
    # Analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    
    # Run
    strats = cerebro.run()
    strat = strats[0]
    
    metrics = {
        "final_value": cerebro.broker.getvalue(),
        "sharpe": strat.analyzers.sharpe.get_analysis().get('sharperatio', 0.0),
        "max_drawdown": strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0.0),
        "total_return": strat.analyzers.returns.get_analysis().get('rtot', 0.0)
    }
    
    return {"metrics": metrics, "cerebro": cerebro}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/engine/test_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/engine/runner.py tests/engine/test_runner.py
git commit -m "feat: implement main backtest engine runner"
```
