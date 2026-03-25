# Sharpe Optimization Target Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change walk-forward weight selection to Sharpe-first ordering, remove the all-zero weight tuple, and verify the effect on `12_1 mom-only` and `vol-only` across `topix_top_10`, `japan_large_30`, and `japan_broad_50`.

**Architecture:** Keep the slice narrow by changing only the weight-selection ranking logic in the walk-forward engine plus the default optimization grid. Preserve approved-params and paper-trading behavior, and record before/after research results by comparing new Sharpe-first runs against the existing return-first artifacts rather than rerunning the baseline.

**Tech Stack:** Python, pandas, pytest, Backtrader-backed research pipeline, local Parquet research store

---

## File Map

**Create:**

- `docs/2026-03-25-sharpe-optimization-target-results.md`
  Responsibility: persistent before/after research note covering all requested universes and candidate factor runs.

**Modify:**

- `src/research/walk_forward.py`
  Responsibility: change `select_best_weights(...)` ordering to Sharpe-first.
- `src/optimize.py`
  Responsibility: remove `(0.0, 0.0, 0.0)` from the default grid if still present and keep optimize wiring unchanged otherwise.
- `tests/research/test_walk_forward.py`
  Responsibility: regression tests for Sharpe-first selection, return tie-break fallback, and default grid cleanup.

## Task 1: Change the Weight Ranking Logic

**Files:**

- Modify: `src/research/walk_forward.py`
- Test: `tests/research/test_walk_forward.py`

- [ ] **Step 1: Write the failing selection-order tests**

Add tests covering:

- higher `sharpe` beats higher `return_pct`
- equal `sharpe` falls back to higher `return_pct`
- existing deterministic weight-value tie-breaks remain stable

Example shape:

```python
def test_select_best_weights_prefers_higher_sharpe_over_higher_return():
    ...


def test_select_best_weights_uses_return_pct_when_sharpe_is_tied():
    ...
```

- [ ] **Step 2: Run the targeted tests to verify RED**

Run:

```bash
uv run pytest -q tests/research/test_walk_forward.py -k "prefers_higher_sharpe or sharpe_is_tied"
```

Expected:

- FAIL because ordering is still `return_pct` first

- [ ] **Step 3: Implement the minimal ranking change**

Update `select_best_weights(...)` in `src/research/walk_forward.py` so sorting becomes:

1. `sharpe`
2. `return_pct`
3. `weights["mom"]`
4. `weights["vol"]`
5. `weights["rev"]`

- [ ] **Step 4: Re-run the targeted tests to verify GREEN**

Run:

```bash
uv run pytest -q tests/research/test_walk_forward.py -k "prefers_higher_sharpe or sharpe_is_tied"
```

Expected:

- PASS

- [ ] **Step 5: Commit the ranking-change slice**

```bash
git add src/research/walk_forward.py tests/research/test_walk_forward.py
git commit -m "feat(research): rank walk-forward weights by sharpe"
```

## Task 2: Remove the Degenerate All-Zero Weight Tuple

**Files:**

- Modify: `src/optimize.py`
- Test: `tests/research/test_walk_forward.py`

- [ ] **Step 1: Write the failing grid test**

Add a test asserting that `DEFAULT_WEIGHT_GRID` does not contain `(0.0, 0.0, 0.0)`.

Example:

```python
def test_default_weight_grid_excludes_all_zero_tuple():
    assert (0.0, 0.0, 0.0) not in optimize.DEFAULT_WEIGHT_GRID
```

- [ ] **Step 2: Run the targeted grid test to verify RED**

Run:

```bash
uv run pytest -q tests/research/test_walk_forward.py -k "excludes_all_zero_tuple"
```

Expected:

- FAIL because the tuple still exists

- [ ] **Step 3: Implement the minimal grid cleanup**

Update `DEFAULT_WEIGHT_GRID` in `src/optimize.py` so the all-zero tuple is removed while all other current tuples remain available.

- [ ] **Step 4: Re-run the targeted grid test to verify GREEN**

Run:

```bash
uv run pytest -q tests/research/test_walk_forward.py -k "excludes_all_zero_tuple"
```

Expected:

- PASS

- [ ] **Step 5: Commit the grid cleanup**

```bash
git add src/optimize.py tests/research/test_walk_forward.py
git commit -m "fix(research): remove zero weight tuple from optimizer grid"
```

## Task 3: Run Regression Verification

**Files:**

- Modify: `tests/research/test_walk_forward.py` if small expectation updates are needed

- [ ] **Step 1: Run the full targeted research tests**

Run:

```bash
uv run pytest -q tests/research/test_walk_forward.py tests/research/test_research_scoring.py tests/research/test_local_data_integration.py
```

Expected:

- PASS

- [ ] **Step 2: Run the full repository test suite**

Run:

```bash
uv run pytest -q
```

Expected:

- PASS with only existing warnings

- [ ] **Step 3: Commit any test-only follow-ups**

```bash
git add tests/research/test_walk_forward.py
git commit -m "test(research): cover sharpe-first optimizer target"
```

Only commit this step if Task 1/2 did not already include all test updates.

## Task 4: Record Before/After Research Results

**Files:**

- Create: `docs/2026-03-25-sharpe-optimization-target-results.md`

- [ ] **Step 1: Collect the existing return-first baseline artifact paths**

Use the already-generated local-store research results for:

- `12_1 mom-only`
- `vol-only`
- `topix_top_10`
- `japan_large_30`
- `japan_broad_50`

Do not rerun the return-first baseline if the artifacts already exist.

- [ ] **Step 2: Run Sharpe-first comparison experiments**

For each universe:

- `topix_top_10`
- `japan_large_30`
- `japan_broad_50`

Run:

- `12_1 mom-only`
- `vol-only`

using the local Parquet research store and the longer synced history.

- [ ] **Step 3: Write the results note**

Create `docs/2026-03-25-sharpe-optimization-target-results.md` and record at minimum:

- artifact path for the return-first baseline
- artifact path for the Sharpe-first rerun
- walk-forward return before/after
- average validation hit rate before/after
- average train/validation gap before/after
- short conclusion per universe/candidate

- [ ] **Step 4: Verify acceptance criteria**

Check that:

- `12_1 mom-only` and `vol-only` both still have positive walk-forward return
- average train/validation gap is narrower than the return-first baseline

If a candidate fails the criteria, record that explicitly in the results note instead of claiming success.

- [ ] **Step 5: Commit the research note**

```bash
git add docs/2026-03-25-sharpe-optimization-target-results.md
git commit -m "docs(research): record sharpe-first optimizer comparison"
```

## Notes For Execution

- Do not change approved-params or paper-trading logic in this slice.
- Keep the local Parquet store as the default research data source for reruns.
- Prefer updating existing tests over adding redundant new ones.
- The most important behavioral proof is narrower train/validation gap, not maximum raw return.
