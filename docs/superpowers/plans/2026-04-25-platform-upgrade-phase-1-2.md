# Platform Upgrade Phase 1+2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 1 — run OOS holdout validation of the `12_1 mom-only` signal (zero code changes). Phase 2 — integrate alphalens-reloaded for factor quality analysis.

**Architecture:** Phase 1 uses the existing `optimize.py` and `main.py` CLIs with specific parameters. Phase 2 adds a pure adapter layer (`research/factor_analysis.py`) that converts the existing scorer DataFrame output to alphalens-compatible format, plus a CLI entry point. No existing code is modified.

**Tech Stack:** Python 3.12, pandas, alphalens-reloaded, existing project code

---

## Phase 1: OOS Validation (Zero Code Changes)

Phase 1 is purely operational — run existing CLIs to verify the signal holds on unseen data.

### Task 1.1: Sync local data for the research universe

**Files:** None (operational)

- [ ] **Step 1: Sync local data store**

```bash
python -m src.main --sync-local --universe-name japan_large_30 --start 2019-01-01 --end 2026-04-25 --local-store-root .
```

Expected: downloads and validates Parquet files for all 30 symbols into `.data_store/raw/`. Output should show each symbol's sync progress with validation status.

- [ ] **Step 2: Verify data store state**

```bash
ls .data_store/raw/ | wc -l
```

Expected: 30 (or close to it — some symbols may not be available on Yahoo Finance)

- [ ] **Step 3: Commit the checkpoint**

```bash
git add -A && git commit -m "chore: sync local data store for japan_large_30 2019-2026"
```

### Task 1.2: Run walk-forward optimization on research period

**Files:** None (operational)

Run walk-forward optimization with `12_1 mom-only` (weight_mom=1.0, weight_vol=0.0, weight_rev=0.0).

> **NOTE:** The weight grid search uses product({0.0, 0.5, 1.0}, repeat=3). For `12_1 mom-only` we care about `(1.0, 0.0, 0.0)` and `(1.0, 0.5, 0.0)`. The grid search will evaluate all 26 tuples automatically.

- [ ] **Step 1: Run walk-forward optimization**

```bash
python -m src.optimize \
  --start 2019-01-01 \
  --end 2024-12-31 \
  --universe-name japan_large_30 \
  --momentum-definition 12_1 \
  --train-months 12 \
  --validation-months 6 \
  --step-months 6 \
  --use-local-store \
  --local-store-root . \
  --local-warmup-bars 300
```

Expected: outputs per-window weight selection and aggregate summary. Records artifacts under `.research_artifacts/walk_forward/<timestamp>-<uuid>/`.

Note the artifact directory path printed at the end — this is needed for Task 1.3.

- [ ] **Step 2: Record the result**

Note:
- The most frequently selected weight tuple across windows
- Walk-forward return total %
- TOPX benchmark return total %
- Walk-forward excess vs TOPX %
- Average window hit rate

- [ ] **Step 3: Commit artifacts**

```bash
git add .research_artifacts/walk_forward/
git commit -m "research: OOS Phase 1 walk-forward 12_1 mom-only 2019-2024"
```

### Task 1.3: Run OOS holdout backtest

**Files:** None (operational)

Take the best weight tuple from the walk-forward result (expected: `(1.0, 0.0, 0.0)` for mom-only) and run it on the holdout period.

- [ ] **Step 1: Approve the selected weights**

```bash
python -m src.research.approve approve --run-id <run-id-from-task-1.2>
```

This writes the approved weights to `.research_artifacts/paper_trade_params.json`.

- [ ] **Step 2: Run OOS backtest with approved weights**

```bash
python -m src.main \
  --universe \
  --universe-name japan_large_30 \
  --strategy multi \
  --start 2025-01-01 \
  --end 2026-04-25 \
  --use-local-store \
  --local-store-root . \
  --local-warmup-bars 300 \
  --no-plot
```

Expected: console output showing final portfolio value, Sharpe ratio, max drawdown, total return %. If approved params exist, `main.py` loads them automatically.

- [ ] **Step 3: Review OOS results against success criteria**

Check:
- Sharpe > 0? (target > 0.5)
- Total return % > TOPIX return % over same period? (excess return > 0)
- Max drawdown < 30%?

- [ ] **Step 4: Run benchmark backtest for comparison**

```bash
python -m src.main \
  --ticker 1306.T \
  --strategy multi \
  --start 2025-01-01 \
  --end 2026-04-25 \
  --use-local-store \
  --local-store-root . \
  --local-warmup-bars 300 \
  --no-plot
```

Compares TOPIX ETF buy-and-hold vs strategy. Record the difference.

- [ ] **Step 5: Commit OOS results**

```bash
git add .research_artifacts/
git commit -m "research: OOS holdout results 2025-01 to 2026-04"
```

### Gate Check: Phase 1 Pass/Fail

**If ALL criteria pass:**
- holdout Sharpe > 0 (target > 0.5)
- excess return vs TOPIX > 0
- max drawdown < 30%

→ Proceed to Phase 2.

**If ANY criterion fails:** Stop. Report findings. Do NOT proceed to Phase 2 until the root cause is understood and the spec is updated.

---

## Phase 2: alphalens-reloaded Integration

Add factor quality analysis as a pure incremental layer on top of the existing scorer. Zero modifications to existing code.

### File Map

```
src/research/factor_analysis.py  (NEW) — adapter: scorer output → alphalens format
tests/research/test_factor_analysis.py  (NEW) — unit tests
pyproject.toml  (MODIFY) — add alphalens-reloaded dependency
```

### Task 2.1: Add alphalens-reloaded dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add alphalens-reloaded to pyproject.toml**

Add `"alphalens-reloaded>=0.4.0"` to the dependencies list in `pyproject.toml`.

- [ ] **Step 2: Install the dependency**

```bash
uv sync
```

Expected: alphalens-reloaded and its dependencies installed.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add alphalens-reloaded dependency"
```

### Task 2.2: Write alphalens adapter (TDD)

**Files:**
- Create: `src/research/factor_analysis.py`
- Test: `tests/research/test_factor_analysis.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/research/test_factor_analysis.py
from __future__ import annotations

import pandas as pd
import numpy as np
from src.research.factor_analysis import build_alphalens_factor_data


def test_build_alphalens_factor_data_basic():
    """A single-period scorer output produces valid alphalens factor input."""
    scored = pd.DataFrame({
        "symbol": ["7203.T", "8306.T", "9432.T"],
        "price": [2800.0, 1500.0, 3200.0],
        "mom_raw": [0.05, -0.02, 0.10],
        "vol_raw": [0.015, 0.020, 0.012],
        "rev_raw": [-0.01, 0.03, -0.02],
        "mom_z": [0.5, -1.0, 1.0],
        "vol_z": [-0.3, -1.2, 0.8],
        "rev_z": [0.2, -0.8, 0.6],
        "mom_contribution": [0.5, -1.0, 1.0],
        "vol_contribution": [-0.3, -1.2, 0.8],
        "rev_contribution": [0.2, -0.8, 0.6],
        "total_score": [0.4, -3.0, 2.4],
        "rank": [2, 3, 1],
        "is_top_n": [True, False, True],
    })
    date = pd.Timestamp("2024-01-31")

    factor_data = build_alphalens_factor_data(
        scored=scored,
        date=date,
        factor_name="total_score",
    )

    # factor_data is a MultiIndex (date, asset) Series of factor values
    assert isinstance(factor_data.index, pd.MultiIndex)
    assert factor_data.index.names == ["date", "asset"]
    assert date in factor_data.index.get_level_values("date")
    assert len(factor_data) == 3
    assert factor_data.loc[(date, "7203.T")] == 0.4
    assert factor_data.loc[(date, "8306.T")] == -3.0


def test_build_alphalens_factor_data_single_factor():
    """Can extract a specific raw factor (e.g. mom_raw) instead of total_score."""
    scored = pd.DataFrame({
        "symbol": ["7203.T", "8306.T"],
        "price": [2800.0, 1500.0],
        "mom_raw": [0.05, -0.02],
        "vol_raw": [0.015, 0.020],
        "rev_raw": [-0.01, 0.03],
        "mom_z": [0.5, -1.0],
        "vol_z": [-0.3, -1.2],
        "rev_z": [0.2, -0.8],
        "mom_contribution": [0.5, -1.0],
        "vol_contribution": [-0.3, -1.2],
        "rev_contribution": [0.2, -0.8],
        "total_score": [0.4, -3.0],
        "rank": [1, 2],
        "is_top_n": [True, False],
    })
    date = pd.Timestamp("2024-01-31")

    factor_data = build_alphalens_factor_data(
        scored=scored,
        date=date,
        factor_name="mom_raw",
    )

    assert factor_data.loc[(date, "7203.T")] == 0.05
    assert factor_data.loc[(date, "8306.T")] == -0.02


def test_build_alphalens_factor_data_missing_column_raises():
    """A non-existent factor_name raises KeyError with a clear message."""
    scored = pd.DataFrame({
        "symbol": ["7203.T"],
        "price": [2800.0],
        "total_score": [0.5],
    })
    date = pd.Timestamp("2024-01-31")

    try:
        build_alphalens_factor_data(scored, date, factor_name="nonexistent")
    except KeyError as exc:
        assert "nonexistent" in str(exc)
    else:
        raise AssertionError("Expected KeyError")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/research/test_factor_analysis.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.research.factor_analysis'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/research/factor_analysis.py
from __future__ import annotations

import pandas as pd


def build_alphalens_factor_data(
    scored: pd.DataFrame,
    date: pd.Timestamp,
    factor_name: str = "total_score",
) -> pd.Series:
    """
    Convert a single-period scorer output to alphalens-compatible factor data.

    Args:
        scored: DataFrame from score_universe() or score_research_universe().
                Must contain 'symbol' column and the requested factor_name column.
        date: The date for which these scores were computed.
        factor_name: Column name to use as the factor value for alphalens.

    Returns:
        pd.Series with MultiIndex (date, asset) and factor values.
        Suitable as the ``factor`` argument to alphalens.
    """
    if factor_name not in scored.columns:
        raise KeyError(
            f"Factor column '{factor_name}' not found in scored DataFrame. "
            f"Available columns: {list(scored.columns)}"
        )

    factor_series = scored.set_index("symbol")[factor_name]
    factor_series.index.name = "asset"
    arrays = [
        pd.Index([date] * len(factor_series), name="date"),
        factor_series.index,
    ]
    multi_index = pd.MultiIndex.from_arrays(arrays, names=["date", "asset"])
    return pd.Series(factor_series.values, index=multi_index, name="factor")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/research/test_factor_analysis.py -v
```

Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/research/factor_analysis.py tests/research/test_factor_analysis.py
git commit -m "feat: add alphalens factor data adapter"
```

### Task 2.3: Write multi-period alphalens builder (TDD)

**Files:**
- Modify: `src/research/factor_analysis.py`
- Modify: `tests/research/test_factor_analysis.py`

alphalens needs multi-period factor data (a history of cross-sectional scores, not just one date). Add a function that accepts a dict of `{date: scored_df}`.

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/research/test_factor_analysis.py

def test_build_multi_period_factor_data():
    """Multiple periods are concatenated into one MultiIndex Series."""
    scored_jan = pd.DataFrame({
        "symbol": ["7203.T", "8306.T"],
        "price": [2800.0, 1500.0],
        "total_score": [0.5, -1.0],
    })
    scored_feb = pd.DataFrame({
        "symbol": ["7203.T", "8306.T"],
        "price": [2850.0, 1480.0],
        "total_score": [0.3, -0.5],
    })
    period_scores = {
        pd.Timestamp("2024-01-31"): scored_jan,
        pd.Timestamp("2024-02-28"): scored_feb,
    }

    result = build_multi_period_factor_data(
        period_scores,
        factor_name="total_score",
    )

    assert isinstance(result.index, pd.MultiIndex)
    assert len(result) == 4
    assert result.loc[(pd.Timestamp("2024-01-31"), "7203.T")] == 0.5
    assert result.loc[(pd.Timestamp("2024-02-28"), "8306.T")] == -0.5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/research/test_factor_analysis.py::test_build_multi_period_factor_data -v
```

Expected: FAIL with `ImportError: cannot import name 'build_multi_period_factor_data'`

- [ ] **Step 3: Write minimal implementation**

```python
# Append to src/research/factor_analysis.py

def build_multi_period_factor_data(
    period_scores: dict[pd.Timestamp, pd.DataFrame],
    factor_name: str = "total_score",
) -> pd.Series:
    """
    Convert multiple periods of scorer output to alphalens factor data.

    Args:
        period_scores: Mapping from date to scored DataFrame
                       (as returned by score_universe for each period).
        factor_name: Column name to use as the factor value.

    Returns:
        pd.Series with MultiIndex (date, asset) covering all periods.
    """
    pieces = []
    for date, scored in sorted(period_scores.items()):
        if scored.empty:
            continue
        piece = build_alphalens_factor_data(scored, date, factor_name)
        pieces.append(piece)

    if not pieces:
        return pd.Series(
            [],
            index=pd.MultiIndex.from_arrays(
                [pd.Index([], name="date"), pd.Index([], name="asset")]
            ),
            name="factor",
            dtype="float64",
        )

    return pd.concat(pieces)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/research/test_factor_analysis.py -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/research/factor_analysis.py tests/research/test_factor_analysis.py
git commit -m "feat: add multi-period alphalens factor data builder"
```

### Task 2.4: Add price data adapter for alphalens (TDD)

**Files:**
- Modify: `src/research/factor_analysis.py`
- Modify: `tests/research/test_factor_analysis.py`

alphalens also needs forward returns. The standard approach is to pass price DataFrames and let alphalens compute forward returns internally. Add a helper to build the price table from the data dict already used by the scorer.

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/research/test_factor_analysis.py

def test_build_alphalens_price_data():
    """Close prices from data_dfs are pivoted into alphalens price format."""
    dates = pd.date_range("2024-01-01", "2024-01-10", freq="B")
    df_7203 = pd.DataFrame(
        {"Close": np.linspace(2700, 2800, len(dates))},
        index=dates,
    )
    df_8306 = pd.DataFrame(
        {"Close": np.linspace(1500, 1550, len(dates))},
        index=dates,
    )
    data_dfs = {"7203.T": df_7203, "8306.T": df_8306}

    prices = build_alphalens_price_data(data_dfs)

    # prices is a DataFrame with assets as columns, dates as index
    assert isinstance(prices, pd.DataFrame)
    assert list(prices.columns) == ["7203.T", "8306.T"]
    assert prices.index.name == "date"
    assert prices.loc[dates[0], "7203.T"] == 2700.0
    assert prices.loc[dates[-1], "8306.T"] == 1550.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/research/test_factor_analysis.py::test_build_alphalens_price_data -v
```

Expected: FAIL with `ImportError: cannot import name 'build_alphalens_price_data'`

- [ ] **Step 3: Write minimal implementation**

```python
# Append to src/research/factor_analysis.py

def build_alphalens_price_data(
    data_dfs: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Build an alphalens-compatible price table from data_dfs.

    Args:
        data_dfs: Mapping from symbol to DataFrame with a 'Close' column.

    Returns:
        pd.DataFrame with dates as index, symbols as columns, closing prices as values.
    """
    close_series = {}
    for symbol, df in data_dfs.items():
        if df is None or df.empty or "Close" not in df.columns:
            continue
        close_series[symbol] = df["Close"]

    if not close_series:
        return pd.DataFrame()

    prices = pd.DataFrame(close_series)
    prices.index = pd.to_datetime(prices.index)
    prices.index.name = "date"
    return prices.sort_index()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/research/test_factor_analysis.py -v
```

Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/research/factor_analysis.py tests/research/test_factor_analysis.py
git commit -m "feat: add alphalens price data adapter"
```

### Task 2.5: Add CLI entry point

**Files:**
- Modify: `src/research/factor_analysis.py`
- Modify: `tests/research/test_factor_analysis.py`

Add a CLI entry point that loads data, runs the scorer monthly, builds alphalens input, and generates a tear sheet.

- [ ] **Step 1: Write smoke test for CLI pipeline**

```python
# Append to tests/research/test_factor_analysis.py

def test_run_factor_analysis_smoke(tmp_path, monkeypatch):
    """End-to-end smoke test: generate alphalens tear sheet without error."""
    import os
    from src.research.factor_analysis import run_factor_analysis

    # Build synthetic data for 3 symbols over 6 months
    symbols = ["7203.T", "8306.T", "9432.T"]
    np.random.seed(42)
    data_dfs = {}
    dates = pd.date_range("2024-01-01", "2024-06-30", freq="B")
    for sym in symbols:
        base_price = np.random.uniform(1000, 5000)
        noise = np.random.randn(len(dates)) * 0.02
        returns = np.cumsum(noise)
        close = base_price * np.exp(returns)
        data_dfs[sym] = pd.DataFrame({"Close": close}, index=dates)

    artifact_dir = tmp_path / "factor_analysis"
    artifact_dir.mkdir()

    # Should not raise — runs factor analysis and writes tear sheet
    result = run_factor_analysis(
        data_dfs=data_dfs,
        start=pd.Timestamp("2024-03-01"),
        end=pd.Timestamp("2024-06-30"),
        factor_name="total_score",
        weight_mom=1.0,
        weight_vol=0.0,
        weight_rev=0.0,
        artifact_dir=artifact_dir,
    )

    assert result is not None
    # Check that some output was written
    assert len(list(artifact_dir.iterdir())) > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/research/test_factor_analysis.py::test_run_factor_analysis_smoke -v
```

Expected: FAIL with `ImportError: cannot import name 'run_factor_analysis'`

- [ ] **Step 3: Write minimal implementation**

```python
# Append to src/research/factor_analysis.py

from __future__ import annotations

import pandas as pd
from pathlib import Path


def run_factor_analysis(
    data_dfs: dict[str, pd.DataFrame],
    start: pd.Timestamp,
    end: pd.Timestamp,
    factor_name: str = "total_score",
    weight_mom: float = 1.0,
    weight_vol: float = 1.0,
    weight_rev: float = 1.0,
    artifact_dir: str | Path | None = None,
    lookback_mom: int = 90,
    lookback_vol: int = 20,
    lookback_rev: int = 20,
) -> dict:
    """
    Run factor analysis over a date range and optionally generate alphalens tear sheet.

    Scores the universe at each month-end in the date range, builds alphalens
    multi-period factor data and price data, and if ``artifact_dir`` is provided,
    writes alphalens tear sheet outputs.

    Returns a dict with keys:
        - "factor_data": MultiIndex Series for alphalens
        - "price_data": DataFrame for alphalens
        - "ic_summary": dict with mean_ic, std_ic, ir
    """
    from src.scoring.multi_factor import score_universe

    # Generate month-end dates
    date_range = pd.date_range(start, end, freq="ME")

    period_scores: dict[pd.Timestamp, pd.DataFrame] = {}
    for date in date_range:
        # Slice data to exclude future information
        window_end = date
        window_start = date - pd.DateOffset(days=max(lookback_mom, lookback_vol, lookback_rev) * 2)

        window_dfs = {}
        for symbol, df in data_dfs.items():
            if df is None or df.empty:
                continue
            mask = (df.index <= window_end) & (df.index >= window_start)
            sliced = df.loc[mask]
            if len(sliced) >= max(lookback_mom, lookback_vol, lookback_rev):
                window_dfs[symbol] = sliced

        if not window_dfs:
            continue

        try:
            scored = score_universe(
                data_dfs=window_dfs,
                top_n=10,
                weight_mom=weight_mom,
                weight_vol=weight_vol,
                weight_rev=weight_rev,
                lookback_mom=lookback_mom,
                lookback_vol=lookback_vol,
                lookback_rev=lookback_rev,
            )
        except ValueError:
            continue

        if scored.empty:
            continue

        period_scores[date] = scored

    if not period_scores:
        raise ValueError(
            f"No valid scoring periods found between {start} and {end}"
        )

    factor_data = build_multi_period_factor_data(period_scores, factor_name)
    price_data = build_alphalens_price_data(data_dfs)

    # Compute IC summary without requiring alphalens
    ic_values = []
    for date, scored_df in period_scores.items():
        if factor_name not in scored_df.columns:
            continue
        sub = scored_df[["symbol", factor_name]].dropna()
        if len(sub) < 2:
            continue
        # Spearman rank IC (non-parametric, robust)
        from scipy.stats import spearmanr
        ic = sub[factor_name].corr(sub[factor_name].rank(), method="spearman")
        ic_values.append(ic)

    ic_summary = {}
    if ic_values:
        ic_series = pd.Series(ic_values)
        ic_summary = {
            "mean_ic": float(ic_series.mean()),
            "std_ic": float(ic_series.std()),
            "ir": float(ic_series.mean() / ic_series.std()) if ic_series.std() > 0 else 0.0,
            "ic_count": len(ic_series),
        }

    # Optionally generate alphalens tear sheet
    if artifact_dir is not None:
        artifact_path = Path(artifact_dir)
        artifact_path.mkdir(parents=True, exist_ok=True)
        _write_alphalens_tear_sheet(
            factor_data=factor_data,
            prices=price_data,
            artifact_dir=artifact_path,
        )

    return {
        "factor_data": factor_data,
        "price_data": price_data,
        "ic_summary": ic_summary,
    }


def _write_alphalens_tear_sheet(
    factor_data: pd.Series,
    prices: pd.DataFrame,
    artifact_dir: Path,
) -> None:
    """Write alphalens summary tear sheet to artifact_dir."""
    try:
        import alphalens as al
    except ImportError:
        print("alphalens-reloaded not installed. Skipping tear sheet generation.")
        return

    # Clean and align factor and price data
    factor_data_clean = factor_data.dropna()
    if factor_data_clean.empty:
        print("No valid factor data after dropping NaN values.")
        return

    # Format forward returns for full tear sheet
    forward_returns = al.utils.get_forward_returns_columns(
        periods=[1, 5, 21],
        prices=prices,
    )

    factor_table = al.utils.get_clean_factor_and_forward_returns(
        factor=factor_data_clean,
        prices=prices,
        periods=[1, 5, 21],
    )

    # IC tear sheet
    ic_fig = al.plotting.plot_ic_ts(
        al.performance.factor_information_coefficient(factor_table)
    )
    ic_fig.savefig(str(artifact_dir / "ic_ts.png"), dpi=150, bbox_inches="tight")

    # Quantile returns
    quantile_fig = al.plotting.plot_quantile_returns_bar(
        al.performance.mean_return_by_quantile(factor_table)
    )
    quantile_fig.savefig(str(artifact_dir / "quantile_returns.png"), dpi=150, bbox_inches="tight")

    # IC summary table
    ic_summary = al.performance.mean_information_coefficient(factor_table)
    ic_summary.to_csv(str(artifact_dir / "ic_summary.csv"))

    print(f"Alphalens artifacts written to {artifact_dir}")
    print(f"  - IC time series plot: {artifact_dir / 'ic_ts.png'}")
    print(f"  - Quantile returns plot: {artifact_dir / 'quantile_returns.png'}")
    print(f"  - IC summary CSV: {artifact_dir / 'ic_summary.csv'}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/research/test_factor_analysis.py -v
```

Expected: 6 PASS (note: the smoke test requires scipy for spearmanr; alphalens-reloaded will be used for tear sheet generation in the smoke test — the test verifies the pipeline runs without error and produces output files)

- [ ] **Step 5: Commit**

```bash
git add src/research/factor_analysis.py tests/research/test_factor_analysis.py
git commit -m "feat: add factor analysis CLI pipeline with IC summary"
```

### Task 2.6: Add CLI entry in pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add console_scripts entry point**

```toml
[project.scripts]
quant-factor-analysis = "src.research.factor_analysis:main"
```

Add this to `pyproject.toml` under the `[project.scripts]` section.

Wait — first check if that section already exists.

- [ ] **Step 2: Add the CLI main() function**

```python
# Append to src/research/factor_analysis.py

def main(argv: list[str] | None = None) -> int:
    """CLI entry point for factor analysis."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Run alphalens factor analysis on a universe"
    )
    parser.add_argument(
        "--universe-name",
        default="japan_large_30",
        help="Universe name (default: japan_large_30)",
    )
    parser.add_argument(
        "--start",
        default="2023-01-01",
        help="Start date YYYY-MM-DD",
    )
    parser.add_argument(
        "--end",
        default="2024-12-31",
        help="End date YYYY-MM-DD",
    )
    parser.add_argument(
        "--factor-name",
        default="total_score",
        help="Factor column to analyze (default: total_score)",
    )
    parser.add_argument(
        "--weight-mom", type=float, default=1.0, help="Momentum weight"
    )
    parser.add_argument(
        "--weight-vol", type=float, default=0.0, help="Low-vol weight"
    )
    parser.add_argument(
        "--weight-rev", type=float, default=0.0, help="Mean-reversion weight"
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path(".research_artifacts/factor_analysis"),
        help="Artifact output directory",
    )
    parser.add_argument(
        "--use-local-store",
        action="store_true",
        help="Load data from validated local store",
    )
    parser.add_argument(
        "--local-store-root",
        type=Path,
        default=Path("."),
        help="Root path for local data store",
    )

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)

    # Load data
    if args.use_local_store:
        from src.data import local_store
        from src.data.universe import get_universe

        symbols = get_universe(args.universe_name)
        try:
            data_dfs = local_store.load_local_universe(
                symbols=symbols,
                start=args.start,
                end=args.end,
                local_store_root=args.local_store_root,
            )
        except local_store.LocalDataSyncRequiredError as exc:
            print(f"Local data sync required: {exc}")
            print(
                f"Sync with: python -m src.main --sync-local "
                f"--universe-name {args.universe_name} "
                f"--start {args.start} --end {args.end}"
            )
            return 1
    else:
        from src.data.bulk_loader import fetch_universe
        from src.data.universe import get_universe

        symbols = get_universe(args.universe_name)
        print(f"Fetching data for {len(symbols)} symbols...")
        data_dfs = fetch_universe(symbols, str(args.start), str(args.end))

    try:
        result = run_factor_analysis(
            data_dfs=data_dfs,
            start=start,
            end=end,
            factor_name=args.factor_name,
            weight_mom=args.weight_mom,
            weight_vol=args.weight_vol,
            weight_rev=args.weight_rev,
            artifact_dir=args.artifact_dir,
        )
    except ValueError as exc:
        print(f"Factor analysis failed: {exc}")
        return 1

    ic = result["ic_summary"]
    print(f"Factor analysis complete ({ic.get('ic_count', 0)} periods)")
    print(f"  Mean IC:   {ic.get('mean_ic', 0):.4f}")
    print(f"  Std IC:    {ic.get('std_ic', 0):.4f}")
    print(f"  IR:        {ic.get('ir', 0):.4f}")
    if args.artifact_dir:
        print(f"  Artifacts: {args.artifact_dir}")

    return 0
```

- [ ] **Step 3: Verify the CLI works**

```bash
python -m src.research.factor_analysis --help
```

Expected: prints help text with all arguments listed.

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/research/test_factor_analysis.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/research/factor_analysis.py tests/research/test_factor_analysis.py pyproject.toml
git commit -m "feat: add factor analysis CLI entry point"
```

---

## Self-Review Checklist (completed after writing)

- [x] Spec coverage: Phase 1 has Task 1.1-1.3 covering OOS validation with gate check. Phase 2 has Task 2.1-2.6 covering alphalens dependency, factor data adapter, price data adapter, multi-period builder, CLI pipeline, and CLI entry point.
- [x] Placeholder scan: No TBD/TODO. All steps have concrete code and commands.
- [x] Type consistency: `build_alphalens_factor_data` signature consistent across Task 2.2 and 2.3. `run_factor_analysis` return dict shape consistent across Task 2.5 and 2.6.
