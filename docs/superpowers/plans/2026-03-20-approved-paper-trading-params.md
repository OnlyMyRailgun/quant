# Approved Paper-Trading Params Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe parameter-selection flow that can choose the best validated walk-forward candidate, promote it to an approved paper-trading parameter set, and let the paper trader load that approved set by default.

**Architecture:** Keep research outputs and live usage separate. Walk-forward artifacts remain immutable experiment outputs, while a small approval layer reads comparable run summaries, selects a candidate under explicit rules, and writes a stable approved-params file that the paper trader consumes. This keeps paper trading from blindly following the newest run while still allowing deterministic automation.

**Tech Stack:** Python, pandas, pathlib, json, pytest

---

## File Structure

### New files

- `src/research/approved_params.py`
  - Candidate selection, approved-params persistence, and loading helpers for paper trading.
- `tests/research/test_approved_params.py`
  - Unit tests for selecting the best validated run, approving a chosen parameter row, and loading it back for paper trading.

### Modified files

- `src/research/artifacts.py`
  - Extend walk-forward metadata/summary payloads if needed so run comparison is explicit and machine-readable.
- `src/research/walk_forward.py`
  - Persist summary fields that make run ranking and approval decisions deterministic.
- `src/optimize.py`
  - Optionally expose or print the candidate-best summary for operator visibility.
- `src/paper/bot.py`
  - Load approved parameters by default, with fallback to existing defaults when no approval exists.
- `tests/research/test_walk_forward.py`
  - Add coverage for any new summary fields emitted by walk-forward runs.
- `tests/scoring/test_multi_factor.py`
  - Add paper-signal tests proving approved params override defaults when present.
- `README.md`
  - Update milestone status if the approved-parameter path materially changes completion state.

## Task 1: Add Approved-Params Selection Tests

**Files:**
- Create: `tests/research/test_approved_params.py`
- Create: `src/research/approved_params.py`

- [ ] **Step 1: Write the failing tests**

```python
import json
from pathlib import Path

import pandas as pd

from src.research.approved_params import (
    load_approved_paper_trading_params,
    select_best_walk_forward_run,
)


def test_select_best_walk_forward_run_chooses_highest_qualified_summary():
    runs = [
        {
            "run_id": "wf-1",
            "summary": {
                "window_count": 4,
                "baseline_return_pct": 2.0,
                "walk_forward_return_pct": 3.0,
            },
        },
        {
            "run_id": "wf-2",
            "summary": {
                "window_count": 4,
                "baseline_return_pct": 1.5,
                "walk_forward_return_pct": 5.0,
            },
        },
    ]

    best = select_best_walk_forward_run(runs, min_window_count=3)

    assert best["run_id"] == "wf-2"
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/research/test_approved_params.py -v`
Expected: FAIL because `src.research.approved_params` does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Implement helpers for:

- filtering candidate walk-forward runs by minimum validation-window count
- ranking candidates by explicit summary metrics
- returning the best qualified run

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/research/test_approved_params.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/research/test_approved_params.py src/research/approved_params.py
git commit -m "feat: add approved parameter selection helpers"
```

## Task 2: Add Approval Persistence Tests

**Files:**
- Modify: `tests/research/test_approved_params.py`
- Modify: `src/research/approved_params.py`

- [ ] **Step 1: Write the failing tests**

Add a test that approves one row from a walk-forward weights file and writes a stable paper-trading params file.

```python
def test_approve_walk_forward_params_writes_stable_paper_trading_file(tmp_path: Path):
    ...
    approved = approve_walk_forward_params(...)
    assert approved["weights"] == {"mom": 0.5, "vol": 1.0, "rev": 0.5}
    assert (tmp_path / "paper_trade_params.json").exists()
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/research/test_approved_params.py -v`
Expected: FAIL because approval persistence does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Implement:

- writing an approved params JSON file under `.research_artifacts/`
- recording source run id, rebalance date, and chosen weights
- loading the approved params JSON back for consumers

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/research/test_approved_params.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/research/test_approved_params.py src/research/approved_params.py
git commit -m "feat: persist approved paper-trading parameters"
```

## Task 3: Extend Walk-Forward Outputs for Comparison

**Files:**
- Modify: `src/research/walk_forward.py`
- Modify: `src/research/artifacts.py`
- Modify: `tests/research/test_walk_forward.py`

- [ ] **Step 1: Write the failing tests**

Add assertions covering any new summary fields needed for candidate comparison, such as active return.

```python
assert result["summary"] == {
    "window_count": 2,
    "baseline_return_pct": 2.2,
    "walk_forward_return_pct": 4.0,
    "active_return_pct": 1.8,
}
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/research/test_walk_forward.py -v`
Expected: FAIL because the new summary fields are not present yet.

- [ ] **Step 3: Write the minimal implementation**

Update walk-forward summary generation so it emits the metrics used by approval ranking, keeping artifact output machine-readable and deterministic.

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/research/test_walk_forward.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/research/walk_forward.py src/research/artifacts.py tests/research/test_walk_forward.py
git commit -m "feat: add walk-forward comparison summary fields"
```

## Task 4: Wire Approved Params into Paper Trading

**Files:**
- Modify: `src/paper/bot.py`
- Modify: `tests/scoring/test_multi_factor.py`
- Modify: `tests/research/test_approved_params.py`

- [ ] **Step 1: Write the failing tests**

Add coverage proving paper signals use approved parameters when available and fall back to defaults otherwise.

```python
def test_calculate_current_signals_uses_approved_params_when_available(tmp_path: Path):
    ...
    winners = calculate_current_signals(data, top_n=2, artifact_dir=tmp_path)
    assert ...
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/scoring/test_multi_factor.py tests/research/test_approved_params.py -v`
Expected: FAIL because `src/paper/bot.py` does not read approved params yet.

- [ ] **Step 3: Write the minimal implementation**

Update `src/paper/bot.py` so that:

- it loads approved paper-trading params from `.research_artifacts/paper_trade_params.json` by default
- explicit function arguments can still override when intentionally provided
- missing approved params cleanly fall back to the current default weights
- artifact metadata reflects the actual weights used

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/scoring/test_multi_factor.py tests/research/test_approved_params.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/paper/bot.py tests/scoring/test_multi_factor.py tests/research/test_approved_params.py
git commit -m "feat: load approved params in paper trader"
```

## Task 5: Document the Approval Flow

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write the documentation changes**

Add:

- the difference between walk-forward artifacts and approved paper-trading params
- where the approved params file lives
- what still remains before Milestone 4 is complete

- [ ] **Step 2: Review for clarity**

Check:

- milestone wording matches actual code state
- file paths match implementation
- README does not imply paper trading automatically follows the newest run

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: explain approved paper-trading params flow"
```

## Task 6: Run Verification

**Files:**
- No additional files unless failures are found.

- [ ] **Step 1: Run focused test suites**

Run: `pytest tests/research/test_approved_params.py tests/research/test_walk_forward.py tests/scoring/test_multi_factor.py -v`
Expected: PASS

- [ ] **Step 2: Run the broader suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 3: Run a manual smoke flow**

Run:

```bash
uv run python -m src.optimize
```

Then verify an approval helper can promote a candidate run and the paper-trading path can consume the resulting approved params file.

- [ ] **Step 4: Summarize follow-up work**

Capture any intentionally deferred items:

- more sophisticated approval constraints
- explicit CLI commands for approve/revoke flows
- backtest-side consumption of approved params
