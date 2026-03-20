# Walk-Forward Decision Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the one-shot optimizer with a reusable walk-forward workflow that selects weights from prior data only, saves per-period weight artifacts, and compares walk-forward performance against a static baseline.

**Architecture:** Split the current `src/optimize.py` script into a reusable research layer plus a thin CLI entry point. A new walk-forward module will own date-window slicing, parameter-grid evaluation, per-window result assembly, and artifact persistence, while the existing optimizer entry point becomes orchestration around those reusable functions. Tests should focus on deterministic offline fixtures so the milestone can run without live network access.

**Tech Stack:** Python, pandas, pathlib, json, backtrader, pytest

---

## File Structure

### New files

- `src/research/walk_forward.py`
  - Reusable window slicing, parameter search orchestration, summary helpers, and artifact-writing entry points for walk-forward runs.
- `tests/research/test_walk_forward.py`
  - Offline unit and regression coverage for window generation, best-parameter selection, artifact shape, and baseline comparison outputs.

### Modified files

- `src/optimize.py`
  - Reduce to CLI-oriented orchestration that calls reusable research functions instead of embedding all logic inline.
- `src/research/artifacts.py`
  - Add helper(s) for writing walk-forward weight artifacts and summary payloads in the same artifact tree used by paper-signal runs.
- `README.md`
  - Document the new walk-forward workflow, output location, and milestone progress once implementation lands.

## Task 1: Add Offline Walk-Forward Window Tests

**Files:**
- Create: `tests/research/test_walk_forward.py`
- Create: `src/research/walk_forward.py`

- [ ] **Step 1: Write the failing tests**

```python
import pandas as pd

from src.research.walk_forward import build_walk_forward_windows


def test_build_walk_forward_windows_returns_rolling_train_and_validation_ranges():
    windows = build_walk_forward_windows(
        start="2021-01-01",
        end="2021-12-31",
        train_months=6,
        validation_months=3,
        step_months=3,
    )

    assert windows == [
        {
            "train_start": "2021-01-01",
            "train_end": "2021-06-30",
            "validation_start": "2021-07-01",
            "validation_end": "2021-09-30",
        },
        {
            "train_start": "2021-04-01",
            "train_end": "2021-09-30",
            "validation_start": "2021-10-01",
            "validation_end": "2021-12-31",
        },
    ]


def test_build_walk_forward_windows_returns_empty_when_range_is_too_short():
    windows = build_walk_forward_windows(
        start="2021-01-01",
        end="2021-06-30",
        train_months=6,
        validation_months=3,
        step_months=3,
    )

    assert windows == []
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/research/test_walk_forward.py -v`
Expected: FAIL because `src.research.walk_forward` does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

```python
def build_walk_forward_windows(start, end, train_months, validation_months, step_months):
    ...
```

Implement:

- calendar-based rolling train and validation windows
- deterministic inclusive date boundaries
- empty output when no full validation window fits

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/research/test_walk_forward.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/research/test_walk_forward.py src/research/walk_forward.py
git commit -m "feat: add walk-forward window builder"
```

## Task 2: Extract Reusable Single-Window Optimization

**Files:**
- Modify: `src/optimize.py`
- Modify: `tests/research/test_walk_forward.py`
- Modify: `src/research/walk_forward.py`

- [ ] **Step 1: Write the failing tests**

Add tests that exercise a pure helper such as `select_best_weights` using a stub evaluator.

```python
from src.research.walk_forward import select_best_weights


def test_select_best_weights_picks_highest_scoring_weight_tuple():
    leaderboard = select_best_weights(
        weight_grid=[(0.0, 0.0, 1.0), (1.0, 0.5, 0.0), (1.0, 1.0, 1.0)],
        evaluate=lambda weights: {
            (0.0, 0.0, 1.0): {"return_pct": 1.0, "sharpe": 0.1},
            (1.0, 0.5, 0.0): {"return_pct": 4.0, "sharpe": 0.2},
            (1.0, 1.0, 1.0): {"return_pct": 3.0, "sharpe": 0.5},
        }[weights],
    )

    assert leaderboard["best"]["weights"] == {"mom": 1.0, "vol": 0.5, "rev": 0.0}
    assert leaderboard["rows"][0]["return_pct"] == 4.0
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/research/test_walk_forward.py -v`
Expected: FAIL because the selection helper does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Implement helpers in `src/research/walk_forward.py` for:

- generating the weight grid
- evaluating each tuple through an injected callable
- sorting the leaderboard deterministically
- returning both the leaderboard rows and the winning weight set

Refactor `src/optimize.py` so the current IS/OOS CLI uses those helpers instead of embedding leaderboard logic inline.

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/research/test_walk_forward.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/optimize.py src/research/walk_forward.py tests/research/test_walk_forward.py
git commit -m "refactor: extract reusable weight selection helpers"
```

## Task 3: Add Walk-Forward Artifact Tests

**Files:**
- Modify: `src/research/artifacts.py`
- Modify: `tests/research/test_walk_forward.py`

- [ ] **Step 1: Write the failing tests**

Add a test for a helper such as `write_walk_forward_run`.

```python
import json
from pathlib import Path

import pandas as pd

from src.research.artifacts import write_walk_forward_run


def test_write_walk_forward_run_persists_weights_and_summary(tmp_path: Path):
    weights = pd.DataFrame(
        [
            {
                "rebalance_date": "2021-07-01",
                "weight_mom": 1.0,
                "weight_vol": 0.5,
                "weight_rev": 0.0,
            }
        ]
    )

    paths = write_walk_forward_run(
        base_dir=tmp_path,
        metadata={"train_months": 6, "validation_months": 3},
        weights=weights,
        summary={"window_count": 1, "baseline_return_pct": 2.5, "walk_forward_return_pct": 3.1},
    )

    assert paths["metadata"].exists()
    assert paths["weights"].exists()
    assert paths["summary"].exists()
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/research/test_walk_forward.py -v`
Expected: FAIL because walk-forward artifact helpers do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Add artifact support in `src/research/artifacts.py` for:

- walk-forward metadata JSON
- per-rebalance weight CSV
- summary JSON
- append-only registry entries that match the existing artifact layout

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/research/test_walk_forward.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/research/artifacts.py tests/research/test_walk_forward.py
git commit -m "feat: add walk-forward artifact persistence"
```

## Task 4: Implement End-to-End Walk-Forward Runner

**Files:**
- Modify: `src/research/walk_forward.py`
- Modify: `src/optimize.py`
- Modify: `tests/research/test_walk_forward.py`

- [ ] **Step 1: Write the failing tests**

Add a regression-style test for `run_walk_forward_experiment` using deterministic synthetic price data and a fake evaluator seam where necessary.

```python
def test_run_walk_forward_experiment_returns_rebalance_weights_and_summary():
    result = run_walk_forward_experiment(
        data_dfs=make_symbol_dfs(),
        start="2021-01-01",
        end="2021-12-31",
        train_months=6,
        validation_months=3,
        step_months=3,
    )

    assert result["weights"]["rebalance_date"].tolist() == ["2021-07-01", "2021-10-01"]
    assert {"baseline_return_pct", "walk_forward_return_pct"} <= set(result["summary"])
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/research/test_walk_forward.py -v`
Expected: FAIL because the end-to-end runner does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Implement `run_walk_forward_experiment` so it:

- builds rolling windows
- optimizes weights on each training slice
- evaluates the winning weights on the matching validation slice
- evaluates a static baseline on the same validation slice
- records one row per rebalance date with chosen weights and metrics
- optionally persists artifacts through `src/research/artifacts.py`

Keep `src/optimize.py` as the CLI wrapper that prints a human-readable summary and delegates the real work to the reusable research module.

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/research/test_walk_forward.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/optimize.py src/research/walk_forward.py tests/research/test_walk_forward.py
git commit -m "feat: add walk-forward optimization runner"
```

## Task 5: Document the New Workflow

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write the documentation changes**

Add:

- how to run the walk-forward optimizer
- where validated weight artifacts are written
- how the walk-forward summary compares against the static baseline
- which remaining Milestone 4 step depends on these artifacts

- [ ] **Step 2: Review for consistency**

Check:

- milestone status wording stays accurate
- artifact paths match the implementation
- README language stays aligned with the trust-focused roadmap

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add walk-forward workflow usage"
```

## Task 6: Run Verification

**Files:**
- No additional files unless failures are found.

- [ ] **Step 1: Run focused test suites**

Run: `pytest tests/research/test_walk_forward.py tests/research/test_artifacts.py tests/scoring/test_multi_factor.py -v`
Expected: PASS

- [ ] **Step 2: Run the broader suite**

Run: `pytest -q`
Expected: PASS or only pre-existing unrelated failures

- [ ] **Step 3: Run the manual optimizer smoke test**

Run: `uv run python -m src.optimize`
Expected:

- walk-forward summary is printed
- baseline and walk-forward comparison metrics are shown
- weight artifacts are written under `.research_artifacts/`

- [ ] **Step 4: Summarize follow-up work**

Capture any intentionally deferred items:

- loading validated parameters into the paper trader
- benchmark expansion beyond the static default weight baseline
- backtest strategy parity refactor onto the shared scorer
