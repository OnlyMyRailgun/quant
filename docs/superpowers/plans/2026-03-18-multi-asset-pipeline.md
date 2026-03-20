# Multi-Asset Data Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a performant, caching data pipeline (`bulk_loader`) capable of fetching and locally storing historical Parquet files for multiple stock symbols reliably.

**Tech Stack:** Python 3.10+, `pandas`, `yfinance`, `pyarrow` (for Parquet).

---

### Task 1: Add Parquet Dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Write the minimal implementation**
Modify `requirements.txt` to include `pyarrow` underneath `matplotlib`.
```text
pyarrow>=14.0.0
```

- [ ] **Step 2: Run to verify**
Run: `pip install -r requirements.txt && python3 -c "import pyarrow"`
Expected: PASS with no output.

- [ ] **Step 3: Commit**
Commit message: "chore: add pyarrow for parquet caching support"

---

### Task 2: Create Universe Definition

**Files:**
- Create: `src/data/universe.py`
- Test: `tests/data/test_universe.py`

- [ ] **Step 1: Write failing test**
Create `tests/data/test_universe.py` asserting `get_topix_top_10()` returns exactly 10 valid `.T` suffixed Japanese stock symbols (e.g., '7203.T').

- [ ] **Step 2: Write minimal implementation**
Create `src/data/universe.py`:
```python
def get_topix_top_10() -> list[str]:
    """Returns a hardcoded list of the top 10 TOPIX components by market cap (approximate).
    Suffix '.T' is required for Yahoo Finance Japanese stocks."""
    return [
        "7203.T",  # Toyota
        "6758.T",  # Sony
        "8306.T",  # Mitsubishi UFJ
        "6861.T",  # Keyence
        "9984.T",  # SoftBank Group
        "9432.T",  # NTT
        "8035.T",  # Tokyo Electron
        "8316.T",  # SMFG
        "6098.T",  # Recruit
        "7974.T",  # Nintendo
    ]
```

- [ ] **Step 3: Run to verify**
Run: `pytest tests/data/test_universe.py`

- [ ] **Step 4: Commit**
Commit message: "feat: add static universe provider for topix top 10"

---

### Task 3: Implement Bulk Loader Cache System

**Files:**
- Create: `src/data/bulk_loader.py`
- Modify: `tests/data/test_yfinance_loader.py` -> rename/expand into `tests/data/test_data_pipeline.py` or create anew. We'll create `tests/data/test_bulk_loader.py` and mock `yfinance_loader` behavior.

- [ ] **Step 1: Implement the loader logic**
Create `src/data/bulk_loader.py`:
```python
import os
import time
import pandas as pd
from pathlib import Path
from src.data.yfinance_loader import fetch_daily_data

CACHE_DIR = Path(".data_cache")

def _get_cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol}.parquet"

def fetch_universe(symbols: list[str], start_date: str, end_date: str) -> dict[str, pd.DataFrame]:
    """
    Fetches daily data for multiple symbols.
    Checks local parquet cache first. If MISS, delegates to yfinance_loader and caches.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    
    for symbol in symbols:
        cache_file = _get_cache_path(symbol)
        
        # Extremely simplified cache check: If file exists, we assume it contains our data.
        # A production system would check the existing date range inside the parquet file.
        if cache_file.exists():
            print(f"[CACHE HIT] Loading {symbol} from disk...")
            df = pd.read_parquet(cache_file)
            results[symbol] = df
        else:
            print(f"[CACHE MISS] Downloading {symbol} from Yahoo Finance...")
            df = fetch_daily_data(symbol, start_date, end_date)
            
            if not df.empty:
                df.to_parquet(cache_file)
                results[symbol] = df
            
            # Anti-ban delay
            time.sleep(0.5)

    return results
```

- [ ] **Step 2: Add test to .gitignore**
Modify `.gitignore` to include `.data_cache/`.

- [ ] **Step 3: Write test**
Create `tests/data/test_bulk_loader.py`. Use a mock object or real small fetching test with a `tmp_path` to verify the parachute writes to disk and reads back.

- [ ] **Step 4: Run to verify**
Run: `pytest tests/data/test_bulk_loader.py`

- [ ] **Step 5: Commit**
Commit message: "feat: implement bulk fetcher with parquet local caching"

---

### Task 4: Integrate Pipeline into Main

**Files:**
- Modify: `src/main.py`
- Modify: `src/engine/runner.py`

- [ ] **Step 1: Engine change**
Modify `run_backtest` to accept `data_dfs: dict[str, pd.DataFrame]` instead of a single `data_df`. Loop over the dict items:
```python
for symbol, df in data_dfs.items():
    cerebro.adddata(bt.feeds.PandasData(dataname=df, dataname=symbol), name=symbol)
```
Change parameter name to `data_dfs_dict`. Ensure `SmaCross` remains functional on the first symbol by default (Backtrader treats `self.data` as `self.datas[0]`), avoiding breaking the single-stock MVP.

- [ ] **Step 2: Main script change**
Modify `main.py` to import `get_topix_top_10` and `fetch_universe`.
Instead of `ticker` argument (or defaulting to universe if not provided), pass the top 10 array to `fetch_universe`.
Pass the resulting dictionary to `run_backtest`.

- [ ] **Step 3: Run to verify**
Run the system against the whole universe.
`python3 src/main.py --no-plot`

- [ ] **Step 4: Commit**
Commit message: "feat: integrate bulk data pipeline into core runner and main"
