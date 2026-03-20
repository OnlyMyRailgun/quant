# Unified Scoring Core and Experiment Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shared multi-factor scoring core plus minimal experiment artifact storage so paper-trading and research runs can produce auditable, reusable outputs from the same ranking logic.

**Architecture:** Introduce a pure pandas-based scoring module that computes factor values, z-scores, composite scores, and ranks from a symbol-to-DataFrame mapping. Add lightweight research artifact and registry helpers that persist scoring outputs and metadata under a predictable directory, then update the paper-trading path to consume the shared scorer instead of duplicating factor math.

**Tech Stack:** Python, pandas, pathlib, json, pytest

---

## File Structure

### New files

- `src/scoring/__init__.py`
  - Package marker for shared scoring utilities.
- `src/scoring/multi_factor.py`
  - Pure scoring logic for momentum, volatility, mean reversion, z-score normalization, and ranking.
- `src/research/__init__.py`
  - Package marker for research helpers.
- `src/research/artifacts.py`
  - Artifact directory management and file-writing helpers.
- `src/research/registry.py`
  - Append-only experiment registry helpers.
- `tests/scoring/test_multi_factor.py`
  - Unit tests for deterministic ranking, factor math, and edge cases.
- `tests/research/test_artifacts.py`
  - Tests for artifact writing and registry behavior.

### Modified files

- `src/paper/bot.py`
  - Replace inline scoring math with calls to shared scoring module and artifact helpers.
- `README.md`
  - Document the new shared scoring path and where artifacts live.

## Task 1: Create Shared Scoring Tests

**Files:**
- Create: `tests/scoring/test_multi_factor.py`
- Create: `src/scoring/__init__.py`
- Create: `src/scoring/multi_factor.py`

- [ ] **Step 1: Write the failing tests**

```python
import pandas as pd

from src.scoring.multi_factor import score_universe


def make_df(closes):
    dates = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"Close": closes}, index=dates)


def test_score_universe_ranks_symbols_by_total_score():
    data = {
        "AAA.T": make_df([100 + i for i in range(100)]),
        "BBB.T": make_df([100] * 80 + [95] * 20),
        "CCC.T": make_df([100] * 100),
    }

    result = score_universe(data, top_n=2, weight_mom=1.0, weight_vol=1.0, weight_rev=1.0)

    assert list(result["symbol"]) == ["AAA.T", "CCC.T", "BBB.T"]
    assert list(result["rank"]) == [1, 2, 3]


def test_score_universe_skips_symbols_with_insufficient_history():
    data = {
        "AAA.T": make_df([100 + i for i in range(100)]),
        "BBB.T": make_df([100 + i for i in range(10)]),
    }

    result = score_universe(data)

    assert list(result["symbol"]) == ["AAA.T"]


def test_score_universe_handles_constant_cross_section_without_nan_scores():
    base = make_df([100] * 100)
    data = {"AAA.T": base.copy(), "BBB.T": base.copy()}

    result = score_universe(data)

    assert result["total_score"].tolist() == [0.0, 0.0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/scoring/test_multi_factor.py -v`
Expected: FAIL because `src.scoring.multi_factor` does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

```python
from __future__ import annotations

import statistics

import pandas as pd


def score_universe(data_dfs, top_n=3, weight_mom=1.0, weight_vol=1.0, weight_rev=1.0):
    ...
```

Implement:

- close-price validation
- minimum history filtering
- momentum, volatility, and mean reversion calculations
- cross-sectional z-scores with zero-std fallback
- total score and rank generation

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scoring/test_multi_factor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/scoring/test_multi_factor.py src/scoring/__init__.py src/scoring/multi_factor.py
git commit -m "feat: add shared multi-factor scoring core"
```

## Task 2: Add Artifact and Registry Tests

**Files:**
- Create: `tests/research/test_artifacts.py`
- Create: `src/research/__init__.py`
- Create: `src/research/artifacts.py`
- Create: `src/research/registry.py`

- [ ] **Step 1: Write the failing tests**

```python
import json
from pathlib import Path

import pandas as pd

from src.research.artifacts import write_scoring_run
from src.research.registry import append_run_record


def test_write_scoring_run_creates_metadata_and_scores(tmp_path: Path):
    scores = pd.DataFrame(
        [{"symbol": "AAA.T", "total_score": 1.23, "rank": 1}]
    )

    paths = write_scoring_run(
        base_dir=tmp_path,
        run_name="paper_signal",
        metadata={"weight_mom": 1.0},
        scores=scores,
        summary={"winner_count": 1},
    )

    assert paths["metadata"].exists()
    assert paths["scores"].exists()
    assert paths["summary"].exists()


def test_append_run_record_writes_jsonl_entry(tmp_path: Path):
    registry_path = tmp_path / "registry.jsonl"

    append_run_record(
        registry_path,
        {"run_id": "run-123", "kind": "paper_signal"},
    )

    lines = registry_path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["run_id"] == "run-123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/research/test_artifacts.py -v`
Expected: FAIL because artifact modules do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

```python
def write_scoring_run(base_dir, run_name, metadata, scores, summary):
    ...


def append_run_record(registry_path, record):
    ...
```

Implement:

- timestamped run directory creation
- JSON metadata writing
- CSV score table writing
- summary JSON writing
- append-only JSONL registry behavior

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/research/test_artifacts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/research/test_artifacts.py src/research/__init__.py src/research/artifacts.py src/research/registry.py
git commit -m "feat: add research artifact and registry helpers"
```

## Task 3: Integrate Shared Scoring into Paper Trading

**Files:**
- Modify: `src/paper/bot.py`
- Modify: `tests/scoring/test_multi_factor.py`

- [ ] **Step 1: Write the failing integration test**

Add a test that imports the paper-trading helper and confirms the winners match the shared scoring core for the same dataset.

```python
from src.paper.bot import calculate_current_signals
from src.scoring.multi_factor import score_universe


def test_paper_signal_generation_matches_shared_scoring():
    data = {
        "AAA.T": make_df([100 + i for i in range(100)]),
        "BBB.T": make_df([100] * 100),
        "CCC.T": make_df([120] * 80 + [100] * 20),
    }

    shared = score_universe(data, top_n=2)
    winners = calculate_current_signals(data, top_n=2)

    assert winners["symbol"].tolist() == shared.head(2)["symbol"].tolist()
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/scoring/test_multi_factor.py -v`
Expected: FAIL because `calculate_current_signals` still uses duplicated inline logic.

- [ ] **Step 3: Update the paper-trading path**

Refactor `src/paper/bot.py` so that:

- `calculate_current_signals` calls `score_universe`
- it keeps returning the top `N` winners
- it preserves current caller expectations
- it prepares metadata that can later be written as artifacts

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/scoring/test_multi_factor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/paper/bot.py tests/scoring/test_multi_factor.py
git commit -m "refactor: route paper signals through shared scoring core"
```

## Task 4: Persist Artifacts for Paper Signal Runs

**Files:**
- Modify: `src/paper/bot.py`
- Modify: `tests/research/test_artifacts.py`

- [ ] **Step 1: Write the failing test**

Add a test that verifies a paper signal run can persist metadata and ranking artifacts when given an artifact directory.

```python
def test_paper_signal_run_can_write_artifacts(tmp_path: Path):
    ...
    result = generate_or_save_signal_artifacts(...)
    assert result["scores"].exists()
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/research/test_artifacts.py -v`
Expected: FAIL because paper signal flow does not write artifacts yet.

- [ ] **Step 3: Implement artifact persistence**

Update `src/paper/bot.py` to:

- optionally write scoring artifacts under `.research_artifacts/`
- append a registry entry for the run
- include enough metadata to reconstruct weights and universe

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/research/test_artifacts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/paper/bot.py tests/research/test_artifacts.py
git commit -m "feat: persist paper signal scoring artifacts"
```

## Task 5: Document the New Foundation Layer

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write the documentation changes**

Add:

- where shared scoring logic lives
- where artifacts are written
- what trust problem this solves

- [ ] **Step 2: Review the document for clarity**

Check:

- wording stays consistent with the Research Platform Foundation milestone
- paths and filenames match the implementation

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document shared scoring and research artifacts"
```

## Task 6: Run End-to-End Verification

**Files:**
- No code changes required unless failures are found.

- [ ] **Step 1: Run focused test suites**

Run: `pytest tests/scoring/test_multi_factor.py tests/research/test_artifacts.py -v`
Expected: PASS

- [ ] **Step 2: Run the broader suite**

Run: `pytest -q`
Expected: PASS or only pre-existing unrelated failures

- [ ] **Step 3: Run a manual paper signal smoke test**

Run:

```bash
python3 src/paper/bot.py generate
```

Expected:

- current winners are printed
- pending orders are staged
- scoring artifacts are written if enabled by implementation

- [ ] **Step 4: Summarize follow-up work**

Capture any intentionally deferred items:

- Backtrader parity adapter
- benchmark reporting
- data validation layer

