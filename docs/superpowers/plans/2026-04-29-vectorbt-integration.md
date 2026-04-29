# Vectorbt Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Backtrader with vectorbt as the backtesting engine, using `--engine vectorbt|backtrader` flag for gradual migration.

**Architecture:** A pure-function `build_orders()` converts scorer output to target-percentage orders. `run_backtest_vectorbt()` iterates rebalance dates, scores per-date with warmup windows, calls `build_orders()`, and simulates via `vbt.Portfolio.from_orders()`. The existing `evaluate_weight_tuple()` dispatches to the vectorbt path when `engine="vectorbt"`.

**Tech Stack:** Python 3.12, vectorbt, pandas, numpy

---

## File Map

| File | Role |
|------|------|
| `engine/order_builder.py` (NEW) | Pure function: period_scores → target% orders |
| `engine/vectorbt_runner.py` (NEW) | Orchestrator: scoring loop + vbt.Portfolio + metrics |
| `tests/engine/test_order_builder.py` (NEW) | Unit tests for order_builder |
| `tests/engine/test_vectorbt_runner.py` (NEW) | Unit tests for vectorbt_runner |
| `engine/runner.py` (MODIFY) | Add engine dispatch |
| `src/optimize.py` (MODIFY) | `--engine` flag, vectorbt path in evaluate_weight_tuple |
| `src/main.py` (MODIFY) | `--engine` flag |
| `pyproject.toml` (MODIFY) | Add vectorbt dependency |
| `scripts/verify_engine_parity.py` (NEW) | Compare backtrader vs vectorbt output |

---

### Task 1: Add vectorbt dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add vectorbt to pyproject.toml**

Add `"vectorbt>=0.7.0"` to the dependencies list in `pyproject.toml`.

- [ ] **Step 2: Install**

Run: `uv sync`
Expected: vectorbt and its transitive deps installed.

- [ ] **Step 3: Verify import**

Run: `uv run python -c "import vectorbt; print(vectorbt.__version__)"`
Expected: prints version number without error.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add vectorbt dependency"
```

---

### Task 2: `engine/order_builder.py` — TDD

**Files:**
- Create: `src/engine/order_builder.py`
- Test: `tests/engine/test_order_builder.py`

- [ ] **Step 1: Write failing test — basic three-stock, single-period**

```python
# tests/engine/test_order_builder.py
from __future__ import annotations

import pandas as pd
import numpy as np
from src.engine.order_builder import build_orders


def make_scored(symbols, scores, is_top_n_flags):
    """Minimal scored DataFrame matching scorer output shape."""
    return pd.DataFrame({
        "symbol": symbols,
        "total_score": scores,
        "rank": range(1, len(symbols) + 1),
        "is_top_n": is_top_n_flags,
        "price": [100.0] * len(symbols),
    })


def test_build_orders_single_period():
    """First rebalance: all positions start from 0, so we get target% for top-N."""
    period_scores = {
        pd.Timestamp("2024-01-31"): make_scored(
            ["A.T", "B.T", "C.T"],
            [3.0, 2.0, 1.0],
            [True, True, False],
        ),
    }
    orders = build_orders(
        period_scores=period_scores,
        top_n=2,
        commission_rate=0.001,
        slippage_pct=0.0005,
    )

    assert len(orders) == 2  # only top-2 get orders
    assert list(orders["symbol"]) == ["A.T", "B.T"]
    # Target weight: 0.95 / 2 = 0.475
    expected_weight = 0.95 / 2
    assert orders.iloc[0]["size"] == expected_weight
    assert orders.iloc[1]["size"] == expected_weight


def test_build_orders_empty_input():
    """Empty period_scores → empty orders DataFrame."""
    orders = build_orders({}, top_n=3, commission_rate=0.001, slippage_pct=0.0005)
    assert orders.empty
    assert list(orders.columns) == ["symbol", "date", "size", "price", "fees"]


def test_build_orders_top_n_exceeds_available():
    """When top_n > available symbols, use all available with adjusted weight."""
    period_scores = {
        pd.Timestamp("2024-01-31"): make_scored(
            ["A.T", "B.T"],
            [2.0, 1.0],
            [True, True],
        ),
    }
    orders = build_orders(
        period_scores=period_scores,
        top_n=5,  # more than available
        commission_rate=0.001,
        slippage_pct=0.0005,
    )
    assert len(orders) == 2
    # Adjusted: 0.95 / 2 = 0.475
    assert orders.iloc[0]["size"] == 0.475
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/engine/test_order_builder.py -v`
Expected: `ModuleNotFoundError: No module named 'src.engine.order_builder'`

- [ ] **Step 3: Implement `build_orders()`**

```python
# src/engine/order_builder.py
from __future__ import annotations

import pandas as pd


def build_orders(
    period_scores: dict[pd.Timestamp, pd.DataFrame],
    top_n: int,
    commission_rate: float,
    slippage_pct: float,
) -> pd.DataFrame:
    """Convert per-date scorer outputs into target-percentage orders for vectorbt.

    Returns:
        DataFrame columns: [symbol, date, size, price, fees]
        - size: target percentage of portfolio (e.g. 0.3167 = 31.67%)
        - price: execution price with slippage baked in
        - fees: pre-computed commission
    """
    columns = ["symbol", "date", "size", "price", "fees"]
    if not period_scores:
        return pd.DataFrame(columns=columns)

    rows = []
    for date, scored in sorted(period_scores.items()):
        if scored.empty:
            continue
        top = scored[scored["is_top_n"]].copy()
        n = min(len(top), top_n)
        if n == 0:
            continue
        target_weight = 0.95 / n
        for _, row in top.head(n).iterrows():
            price = float(row["price"])
            adj_price = price * (1.0 - slippage_pct)
            rows.append({
                "symbol": row["symbol"],
                "date": date,
                "size": target_weight,
                "price": adj_price,
                "fees": abs(target_weight) * adj_price * commission_rate,
            })

    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/engine/test_order_builder.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/engine/order_builder.py tests/engine/test_order_builder.py
git commit -m "feat: add build_orders — scored_df to vectorbt target% orders"
```

---

### Task 3: `engine/order_builder.py` — multi-period test

**Files:**
- Modify: `tests/engine/test_order_builder.py`

- [ ] **Step 1: Write failing test — multi-period with symbol changes**

```python
def test_build_orders_multi_period():
    """Two periods with changing top-N: orders express up-to-date target weights."""
    period_scores = {
        pd.Timestamp("2024-01-31"): make_scored(
            ["A.T", "B.T", "C.T"],
            [3.0, 2.0, 1.0],
            [True, True, False],
        ),
        pd.Timestamp("2024-02-28"): make_scored(
            ["A.T", "B.T", "C.T"],
            [1.0, 3.0, 2.0],
            [False, True, True],  # A.T out, C.T in
        ),
    }
    orders = build_orders(
        period_scores=period_scores,
        top_n=2,
        commission_rate=0.001,
        slippage_pct=0.0,
    )

    assert len(orders) == 4  # 2 per period
    jan = orders[orders["date"] == pd.Timestamp("2024-01-31")]
    feb = orders[orders["date"] == pd.Timestamp("2024-02-28")]
    assert set(jan["symbol"]) == {"A.T", "B.T"}
    assert set(feb["symbol"]) == {"B.T", "C.T"}
    # Slippage=0 → price unchanged
    assert jan.iloc[0]["price"] == 100.0


def test_build_orders_slippage_applied():
    """Slippage reduces fill price for BUY-like target orders."""
    period_scores = {
        pd.Timestamp("2024-01-31"): make_scored(
            ["A.T"], [1.0], [True],
        ),
    }
    orders = build_orders(
        period_scores=period_scores,
        top_n=1,
        commission_rate=0.0,
        slippage_pct=0.01,  # 1% slippage
    )
    assert orders.iloc[0]["price"] == 99.0  # 100 * (1 - 0.01)
```

- [ ] **Step 2: Run test — expect PASS**

Run: `pytest tests/engine/test_order_builder.py -v`
Expected: 5 PASS (3 from Task 2 + 2 new)

- [ ] **Step 3: Commit**

```bash
git add tests/engine/test_order_builder.py
git commit -m "test: add multi-period and slippage tests for build_orders"
```

---

### Task 4: `engine/vectorbt_runner.py` — TDD

**Files:**
- Create: `src/engine/vectorbt_runner.py`
- Test: `tests/engine/test_vectorbt_runner.py`

- [ ] **Step 1: Write failing test — smoke test with synthetic data**

```python
# tests/engine/test_vectorbt_runner.py
from __future__ import annotations

import pandas as pd
import numpy as np
from src.engine.vectorbt_runner import run_backtest_vectorbt


def make_price_df(symbols, n_days, seed=42):
    """Build data_dfs with random walk prices for testing."""
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    result = {}
    for sym in symbols:
        returns = np.random.randn(n_days) * 0.01
        close = 1000.0 * np.exp(np.cumsum(returns))
        result[sym] = pd.DataFrame({"Close": close}, index=dates)
    return result


def test_run_backtest_vectorbt_returns_metrics_dict():
    """Smoke test: vectorbt runner produces expected output shape."""
    data_dfs = make_price_df(["A.T", "B.T", "C.T"], n_days=120)

    result = run_backtest_vectorbt(
        data_dfs=data_dfs,
        start="2024-03-01",
        end="2024-06-30",
        weights=(1.0, 0.0, 0.0),
        top_n=2,
        initial_cash=1_000_000.0,
        commission_rate=0.001,
        slippage_pct=0.0005,
        momentum_definition="90d",
    )

    assert "return_pct" in result
    assert "sharpe" in result
    assert "drawdown" in result
    assert "symbol_returns" in result
    assert "scores" in result
    assert isinstance(result["sharpe"], float)
    assert isinstance(result["return_pct"], float)


def test_run_backtest_vectorbt_respects_evaluation_window():
    """evaluation_start/end slice metrics from the correct sub-period."""
    data_dfs = make_price_df(["A.T", "B.T", "C.T"], n_days=200)

    result_full = run_backtest_vectorbt(
        data_dfs=data_dfs,
        start="2024-01-01",
        end="2024-09-30",
        weights=(1.0, 0.0, 0.0),
        top_n=2,
        momentum_definition="90d",
    )
    result_sub = run_backtest_vectorbt(
        data_dfs=data_dfs,
        start="2024-01-01",
        end="2024-09-30",
        evaluation_start="2024-04-01",
        evaluation_end="2024-06-30",
        weights=(1.0, 0.0, 0.0),
        top_n=2,
        momentum_definition="90d",
    )

    # Sub-window return should differ from full-window
    assert result_full["return_pct"] != result_sub["return_pct"]
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/engine/test_vectorbt_runner.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `run_backtest_vectorbt()`**

```python
# src/engine/vectorbt_runner.py
from __future__ import annotations

import numpy as np
import pandas as pd
import vectorbt as vbt

from src.engine.order_builder import build_orders
from src.scoring.multi_factor import (
    score_universe,
    DEFAULT_LOOKBACK_MOM,
    DEFAULT_LOOKBACK_VOL,
    DEFAULT_LOOKBACK_REV,
)


def run_backtest_vectorbt(
    data_dfs: dict[str, pd.DataFrame],
    start: str,
    end: str,
    weights: tuple[float, float, float],
    top_n: int = 3,
    initial_cash: float = 1_000_000.0,
    commission_rate: float = 0.001,
    slippage_pct: float = 0.0005,
    momentum_definition: str = "90d",
    reversal_filter_params=None,
    evaluation_start: str | None = None,
    evaluation_end: str | None = None,
) -> dict:
    w_mom, w_vol, w_rev = weights

    # Determine lookback
    if momentum_definition == "12_1":
        lookback = 252
    else:
        lookback = max(DEFAULT_LOOKBACK_MOM, DEFAULT_LOOKBACK_VOL, DEFAULT_LOOKBACK_REV)

    # Generate month-end rebalance dates
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    rebalance_dates = pd.date_range(start_ts, end_ts, freq="ME")

    # Score at each rebalance date with per-date data windows
    period_scores: dict[pd.Timestamp, pd.DataFrame] = {}
    for date in rebalance_dates:
        window_dfs = {}
        for sym, df in data_dfs.items():
            if df is None or df.empty:
                continue
            mask = df.index <= date
            visible = df.loc[mask]
            if len(visible) >= lookback:
                window_dfs[sym] = visible

        if not window_dfs:
            continue

        try:
            if momentum_definition != "90d":
                from src.research.research_scoring import score_research_universe
                scored = score_research_universe(
                    window_dfs, top_n=top_n,
                    weight_mom=w_mom, weight_vol=w_vol, weight_rev=w_rev,
                    momentum_definition=momentum_definition,
                )
            else:
                scored = score_universe(
                    window_dfs, top_n=top_n,
                    weight_mom=w_mom, weight_vol=w_vol, weight_rev=w_rev,
                )
        except ValueError:
            continue

        if scored.empty:
            continue

        if reversal_filter_params is not None:
            from src.research.reversal_filter import apply_reversal_filter
            result = apply_reversal_filter(scored, window_dfs, reversal_filter_params)
            scored = result["filtered_scores"]
            if scored.empty:
                continue

        period_scores[date] = scored

    if not period_scores:
        return {
            "return_pct": 0.0, "sharpe": 0.0, "drawdown": 0.0,
            "symbol_returns": {}, "scores": pd.DataFrame(),
        }

    # Build orders
    orders = build_orders(
        period_scores=period_scores,
        top_n=top_n,
        commission_rate=commission_rate,
        slippage_pct=slippage_pct,
    )
    if orders.empty:
        return {
            "return_pct": 0.0, "sharpe": 0.0, "drawdown": 0.0,
            "symbol_returns": {}, "scores": pd.DataFrame(),
        }

    # Build close price matrix (date × symbol)
    close_series = {}
    for sym in orders["symbol"].unique():
        df = data_dfs.get(sym)
        if df is not None and "Close" in df.columns:
            close_series[sym] = df["Close"]
    if not close_series:
        return {
            "return_pct": 0.0, "sharpe": 0.0, "drawdown": 0.0,
            "symbol_returns": {}, "scores": pd.DataFrame(),
        }
    close_prices = pd.DataFrame(close_series).sort_index()

    # Portfolio simulation
    portfolio = vbt.Portfolio.from_orders(
        close=close_prices,
        size=orders["size"],
        size_type="targetpercent",
        price=orders["price"],
        fees=orders["fees"],
        freq="D",
        cash_sharing=True,
        init_cash=initial_cash,
        group_by=True,
        call_seq="auto",
    )

    # Slice to evaluation window if specified
    eval_start = pd.Timestamp(evaluation_start) if evaluation_start else start_ts
    eval_end = pd.Timestamp(evaluation_end) if evaluation_end else end_ts

    if evaluation_start or evaluation_end:
        sub_returns = portfolio.returns().loc[eval_start:eval_end]
    else:
        sub_returns = portfolio.returns()

    if len(sub_returns.dropna()) < 2:
        return {
            "return_pct": 0.0, "sharpe": 0.0, "drawdown": 0.0,
            "symbol_returns": {}, "scores": pd.DataFrame(),
        }

    # Metrics
    total_return = (portfolio.value().iloc[-1] / initial_cash - 1.0) * 100
    sharpe = float(portfolio.stats().get("Sharpe Ratio", 0.0) or 0.0)
    dd = float(portfolio.stats().get("Max Drawdown", 0.0) or 0.0)
    drawdown_pct = dd * 100

    # symbol_returns from positions
    symbol_returns = {}
    try:
        positions = portfolio.positions
        if positions is not None:
            for sym in orders["symbol"].unique():
                try:
                    pos_returns = positions[sym].returns
                    if pos_returns is not None and len(pos_returns.dropna()) > 0:
                        sym_total = float((1 + pos_returns).prod() - 1) * 100
                        symbol_returns[sym] = sym_total
                except Exception:
                    symbol_returns[sym] = 0.0
    except Exception:
        pass

    # scores from last rebalance date
    last_date = max(period_scores.keys()) if period_scores else None
    scores = period_scores[last_date] if last_date else pd.DataFrame()

    return {
        "return_pct": round(total_return, 4),
        "sharpe": round(sharpe, 4),
        "drawdown": round(drawdown_pct, 4),
        "symbol_returns": symbol_returns,
        "scores": scores,
    }
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/engine/test_vectorbt_runner.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/engine/vectorbt_runner.py tests/engine/test_vectorbt_runner.py
git commit -m "feat: add run_backtest_vectorbt with per-date scoring loop"
```

---

### Task 5: Engine dispatch in `engine/runner.py`

**Files:**
- Modify: `src/engine/runner.py:1-56`

- [ ] **Step 1: Add dispatch logic**

In `runner.py`, add import and conditional:

```python
# Add at top of file:
from src.engine.vectorbt_runner import run_backtest_vectorbt

# In run_backtest(), add engine parameter and dispatch:
def run_backtest(data_dfs, strategy_class, initial_cash=1000000.0,
                 commission=0.001, slippage=None, engine="backtrader",
                 momentum_definition="90d", reversal_filter_params=None):
    if engine == "vectorbt":
        from src.strategies.multi_factor import UniversalMultiFactor
        params = getattr(strategy_class, "params", {})
        w_mom = getattr(params, "weight_mom", 1.0)
        w_vol = getattr(params, "weight_vol", 1.0)
        w_rev = getattr(params, "weight_rev", 1.0)
        top_n = getattr(params, "top_n", 3)
        return run_backtest_vectorbt(
            data_dfs=data_dfs,
            start=None,  # runner uses full data range
            end=None,
            weights=(w_mom, w_vol, w_rev),
            top_n=top_n,
            initial_cash=initial_cash,
            commission_rate=commission,
            slippage_pct=slippage or 0.0005,
            momentum_definition=momentum_definition,
            reversal_filter_params=reversal_filter_params,
        )
    # ... existing Backtrader path unchanged
```

- [ ] **Step 2: Verify existing tests pass**

Run: `pytest tests/engine/test_runner.py tests/ -k "runner" -v`
Expected: all existing runner tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/engine/runner.py
git commit -m "feat: add engine dispatch to runner.py"
```

---

### Task 6: `--engine` flag in `src/optimize.py`

**Files:**
- Modify: `src/optimize.py` — `_build_parser()`, `main()`, `run_walk_forward_optimization()`, `evaluate_weight_tuple()`

- [ ] **Step 1: Add engine parameter to `evaluate_weight_tuple()`**

```python
# In evaluate_weight_tuple signature, add:
engine: str = "backtrader",

# Near top of function, after the scoring block (the if/else producing `scores`),
# add vectorbt fast path:
if engine == "vectorbt":
    return run_backtest_vectorbt(
        data_dfs=window_dfs,
        start=start,
        end=end,
        weights=weights,
        top_n=3,
        initial_cash=STARTING_CASH,
        commission_rate=0.001,
        slippage_pct=0.0005,
        momentum_definition=momentum_definition,
        reversal_filter_params=reversal_filter_params,
        evaluation_start=eval_start,
        evaluation_end=eval_end,
    )
```

- [ ] **Step 2: Add engine to `run_walk_forward_optimization()` and pass through closures**

Add `engine="backtrader"` to the signature. Pass `reversal_filter_params=reversal_filter_params, engine=engine` to all `_evaluate_weight_tuple_with_momentum()` and `evaluate_weight_tuple()` calls inside closures.

- [ ] **Step 3: Add CLI args**

```python
parser.add_argument("--engine", choices=["backtrader", "vectorbt"], default="backtrader")
parser.add_argument("--fast", action="store_true", help="Alias for --engine vectorbt")
```

- [ ] **Step 4: Wire in main()**

```python
# In main(), before run_walk_forward_optimization call:
engine = "vectorbt" if args.fast else args.engine
# Pass engine=engine to run_walk_forward_optimization()
```

- [ ] **Step 5: Run existing walk-forward tests**

Run: `pytest tests/research/test_walk_forward.py -v --tb=short`
Expected: all pass (vectorbt path NOT triggered in tests since engine defaults to "backtrader").

- [ ] **Step 6: Commit**

```bash
git add src/optimize.py
git commit -m "feat: add --engine and --fast flags to optimize.py"
```

---

### Task 7: `--engine` flag in `src/main.py`

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Add CLI arg and wiring**

```python
parser.add_argument("--engine", choices=["backtrader", "vectorbt"], default="backtrader")
parser.add_argument("--fast", action="store_true", help="Alias for --engine vectorbt")
```

Pass `engine=engine, momentum_definition=momentum_definition, reversal_filter_params=reversal_filter_params` to `run_backtest()`.

- [ ] **Step 2: Add `--momentum-definition` to main.py if not already present**

Run: `grep "momentum.definition" src/main.py`
If missing, add:
```python
parser.add_argument("--momentum-definition", choices=["90d", "12_1"], default="90d")
```

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: add --engine flag to main.py"
```

---

### Task 8: Parity verification script

**Files:**
- Create: `scripts/verify_engine_parity.py`

- [ ] **Step 1: Write verification script**

```python
#!/usr/bin/env python3
"""Compare backtrader vs vectorbt engine output on a small universe."""
from __future__ import annotations
import sys
import pandas as pd
from src.data.bulk_loader import fetch_universe
from src.optimize import evaluate_weight_tuple

SYMBOLS = ["7203.T", "8306.T", "9432.T"]  # topix_top_10 subset
START, END = "2023-01-01", "2024-01-01"
WEIGHTS = (1.0, 0.0, 0.0)

print("Fetching data...")
data = fetch_universe(SYMBOLS, START, END)

print("Running backtrader...")
bt = evaluate_weight_tuple(data, START, END, WEIGHTS, engine="backtrader")

print("Running vectorbt...")
vbt = evaluate_weight_tuple(data, START, END, WEIGHTS, engine="vectorbt")

print(f"\n{'Metric':<20} {'Backtrader':>12} {'Vectorbt':>12} {'Diff':>10}")
print("-" * 56)
for key in ["return_pct", "sharpe", "drawdown"]:
    b, v = bt[key], vbt[key]
    diff = abs(b - v)
    print(f"{key:<20} {b:>12.4f} {v:>12.4f} {diff:>10.4f}")

return_diff = abs(bt["return_pct"] - vbt["return_pct"])
sharpe_diff = abs(bt["sharpe"] - vbt["sharpe"])

ok = return_diff < 1.0 and sharpe_diff < 0.05
print(f"\nReturn < 1% diff: {'PASS' if return_diff < 1.0 else 'FAIL'} ({return_diff:.4f})")
print(f"Sharpe < 0.05 diff: {'PASS' if sharpe_diff < 0.05 else 'FAIL'} ({sharpe_diff:.4f})")
print(f"OVERALL: {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
```

- [ ] **Step 2: Run verification**

Run: `uv run python scripts/verify_engine_parity.py`
Expected: PASS — both metrics within tolerance.

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_engine_parity.py
git commit -m "feat: add engine parity verification script"
```

---

### Task 9: Full test suite verification

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: all existing 197 tests + new tests pass, zero regressions.

- [ ] **Step 2: Commit any remaining changes**

```bash
git add -A
git commit -m "chore: final test verification for vectorbt integration"
```

---

## Self-Review

- [x] Spec coverage: Task 2-3 → order_builder, Task 4 → vectorbt_runner, Task 5 → engine dispatch, Task 6 → optimize.py, Task 7 → main.py, Task 8 → parity script. All spec components covered.
- [x] Placeholder scan: No TBD/TODO. Every step has concrete code.
- [x] Type consistency: `build_orders` returns DataFrame with columns [symbol, date, size, price, fees] — used consistently in Tasks 2-4. `run_backtest_vectorbt` returns same dict shape as `evaluate_weight_tuple` — used consistently in Tasks 4-6.
