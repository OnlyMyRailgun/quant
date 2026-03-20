# Milestone 3 Explainable Stock Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add scorer-native explainability, persisted rebalance evidence, and lightweight winner/near-miss comparison reporting for Milestone 3.

**Architecture:** Extend the shared multi-factor scorer so explainability columns are generated at the same point as ranking. Then persist that richer ranked universe in scoring artifacts and add a thin read/report layer that explains winners, near-misses, and symbol-vs-symbol score deltas without reimplementing factor math.

**Tech Stack:** Python, pandas, pytest, existing research artifact helpers, existing paper-trading signal path

---

## File Structure

### Existing files to modify

- `src/scoring/multi_factor.py`
  Responsibility: canonical multi-factor ranking and explainability columns.
- `src/paper/bot.py`
  Responsibility: signal generation, artifact writing integration, and any small reporting entry point reused by paper signals.
- `src/research/artifacts.py`
  Responsibility: metadata/summary payload generation for saved scoring runs.
- `tests/scoring/test_multi_factor.py`
  Responsibility: scorer and paper-signal explainability regression coverage.
- `tests/research/test_artifacts.py`
  Responsibility: artifact persistence and summary shape regression coverage.

### New files to create

- `src/research/explain.py`
  Responsibility: thin helpers for near-miss extraction and stock-vs-stock comparison from an already-scored DataFrame or saved scoring artifact.
- `tests/research/test_explain.py`
  Responsibility: regression coverage for winner/near-miss reporting and symbol-vs-symbol explanation helpers.

### Boundaries

- Keep factor math in `src/scoring/multi_factor.py` only.
- `src/research/explain.py` may read and compare saved evidence, but must not recompute scores independently.
- Preserve existing output columns and behavior; only add columns and helper read/report functions.

## Task 1: Add Scorer-Native Explainability Columns

**Files:**
- Modify: `src/scoring/multi_factor.py`
- Modify: `tests/scoring/test_multi_factor.py`

- [ ] **Step 1: Write the failing scorer explainability tests**

Add tests in `tests/scoring/test_multi_factor.py` covering:

- contribution columns exist in ranked output
- each contribution equals weight times its z-score
- `total_score` equals the sum of contribution columns
- ranking order remains unchanged for the existing fixture universe

- [ ] **Step 2: Run scorer tests to verify RED**

Run: `pytest tests/scoring/test_multi_factor.py -q`
Expected: FAIL because contribution columns are missing from scorer output.

- [ ] **Step 3: Write the minimal scorer implementation**

Update `src/scoring/multi_factor.py` so `score_universe()` adds:

- `mom_contribution`
- `vol_contribution`
- `rev_contribution`

Populate them directly from the weighted z-score formula before sorting. Preserve existing columns, existing ranking order, and current top-N behavior.

- [ ] **Step 4: Run scorer tests to verify GREEN**

Run: `pytest tests/scoring/test_multi_factor.py -q`
Expected: PASS.

- [ ] **Step 5: Run adjacent parity coverage**

Run: `pytest tests/strategies/test_multi_factor_parity.py -q`
Expected: PASS, confirming the richer scorer output does not break strategy/paper parity expectations.

- [ ] **Step 6: Commit phase 1**

```bash
git add src/scoring/multi_factor.py tests/scoring/test_multi_factor.py
git commit -m "feat(scoring): add explainable factor contributions"
```

## Task 2: Persist Winners and Near-Misses in Scoring Artifacts

**Files:**
- Modify: `src/research/artifacts.py`
- Modify: `src/paper/bot.py`
- Modify: `tests/research/test_artifacts.py`
- Modify: `tests/scoring/test_multi_factor.py`

- [ ] **Step 1: Write the failing artifact tests**

Add tests covering:

- saved `scores.csv` includes contribution columns
- artifact metadata or summary includes selected winners in ranked order
- artifact metadata or summary includes the next three near-miss symbols after the winners
- paper signal artifact output remains deterministic under fixed inputs

- [ ] **Step 2: Run artifact-focused tests to verify RED**

Run: `pytest tests/research/test_artifacts.py tests/scoring/test_multi_factor.py -q`
Expected: FAIL because winners/near-misses are not yet summarized and contribution columns are not yet asserted in persisted artifacts.

- [ ] **Step 3: Write the minimal artifact implementation**

Update artifact helpers so scoring metadata/summary include compact winner and near-miss payloads derived from the same ranked DataFrame that is written to `scores.csv`.

Implementation constraints:

- default near-miss count to `3`
- do not duplicate the full ranked universe into metadata/summary
- keep `scores.csv` as the canonical detailed evidence store
- ensure `calculate_current_signals()` continues returning top-N winners with legacy aliases intact

- [ ] **Step 4: Run artifact-focused tests to verify GREEN**

Run: `pytest tests/research/test_artifacts.py tests/scoring/test_multi_factor.py -q`
Expected: PASS.

- [ ] **Step 5: Run broader research regression coverage**

Run: `pytest tests/research/test_artifacts.py tests/research/test_approved_params.py tests/research/test_walk_forward.py -q`
Expected: PASS.

- [ ] **Step 6: Commit phase 2**

```bash
git add src/research/artifacts.py src/paper/bot.py tests/research/test_artifacts.py tests/scoring/test_multi_factor.py
git commit -m "feat(research): persist explainable winners and near-misses"
```

## Task 3: Add Lightweight Explainability Reporting Helpers

**Files:**
- Create: `src/research/explain.py`
- Modify: `src/paper/bot.py`
- Create: `tests/research/test_explain.py`
- Modify: `tests/research/test_artifacts.py`

- [ ] **Step 1: Write the failing reporting/helper tests**

Add tests covering:

- extraction of winners and near-misses from a ranked DataFrame
- comparison of two symbols returns per-factor contribution deltas and total score delta
- loading a saved scoring artifact supports the same winner/near-miss and comparison flows

- [ ] **Step 2: Run explainability helper tests to verify RED**

Run: `pytest tests/research/test_explain.py -q`
Expected: FAIL because the helper module does not yet exist.

- [ ] **Step 3: Write the minimal reporting/helper implementation**

Create `src/research/explain.py` with thin helpers such as:

- `build_selection_report(scores: pd.DataFrame, top_n: int, near_miss_count: int = 3)`
- `compare_ranked_symbols(scores: pd.DataFrame, higher_symbol: str, lower_symbol: str)`
- `load_scoring_run_scores(run_dir: Path)`

If helpful, add a small formatting or print helper in `src/paper/bot.py`, but do not add a second scoring path and do not require live data fetches for tests.

- [ ] **Step 4: Run explainability helper tests to verify GREEN**

Run: `pytest tests/research/test_explain.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full milestone-adjacent test set**

Run: `pytest tests/scoring/test_multi_factor.py tests/research/test_artifacts.py tests/research/test_explain.py tests/strategies/test_multi_factor_parity.py -q`
Expected: PASS.

- [ ] **Step 6: Commit phase 3**

```bash
git add src/research/explain.py src/paper/bot.py tests/research/test_explain.py tests/research/test_artifacts.py
git commit -m "feat(research): add stock selection explainability helpers"
```

## Final Verification

- [ ] **Step 1: Run the complete milestone regression set**

Run: `pytest tests/scoring/test_multi_factor.py tests/research/test_artifacts.py tests/research/test_explain.py tests/strategies/test_multi_factor_parity.py tests/research/test_walk_forward.py tests/research/test_approved_params.py -q`
Expected: PASS.

- [ ] **Step 2: Review git status**

Run: `git status --short`
Expected: clean working tree.

- [ ] **Step 3: Prepare branch completion**

Use `superpowers:finishing-a-development-branch` after implementation is complete and verification is green.

## Notes for Execution

- Do not begin implementation on `main`; create an isolated worktree/branch first.
- Follow TDD strictly: every production change must be preceded by a failing test.
- Keep each phase independently shippable and commit immediately after that phase's tests pass.
- If artifact schema changes require minor test fixture expansion, keep changes minimal and deterministic.
