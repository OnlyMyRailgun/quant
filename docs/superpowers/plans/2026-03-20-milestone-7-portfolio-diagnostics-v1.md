# Milestone 7 Portfolio Diagnostics v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first portfolio-diagnostics layer for walk-forward research so we can explain where performance is coming from before expanding to broader universes.

**Architecture:** Extend the walk-forward research result shape with deterministic window-level diagnostics and summary-level aggregates, persist those diagnostics in research artifacts, and surface a compact operator-facing summary through `src.optimize`. Keep the first slice intentionally narrow: reuse existing scorer and artifact flows, avoid a new reporting subsystem, and prefer simple deterministic metrics over premature analytics complexity.

**Tech Stack:** Python, pandas, pytest, existing walk-forward research pipeline, existing artifact helpers

---

## File Structure

### Existing files to modify

- `src/research/walk_forward.py`
  Responsibility: window construction, evaluation orchestration, and research summary payloads.
- `src/research/artifacts.py`
  Responsibility: persisted metadata, summary, registry entries, and deterministic artifact output.
- `src/optimize.py`
  Responsibility: optimizer CLI, research-run wiring, and operator-facing summary printing.
- `tests/research/test_walk_forward.py`
  Responsibility: regression coverage for walk-forward result shape and optimizer CLI summary output.
- `tests/research/test_artifacts.py`
  Responsibility: artifact schema persistence and deterministic metadata coverage.

### New files to create

- `tests/research/test_diagnostics.py`
  Responsibility: isolated regression coverage for diagnostics helpers and aggregate calculations.

### Boundaries

- Keep diagnostics derived from already-available research outputs; do not create a second scoring or backtest path.
- `src/research/walk_forward.py` owns diagnostics calculation for walk-forward experiments.
- `src/research/artifacts.py` persists diagnostics but must not recalculate them.
- `src/optimize.py` only formats and prints diagnostics already present in the research result.
- This v1 slice should not yet attempt full attribution, plotting, or a separate reporting CLI.

## Task 1: Define Diagnostics Schema and Helper Calculations

**Files:**
- Create: `tests/research/test_diagnostics.py`
- Modify: `src/research/walk_forward.py`

- [ ] **Step 1: Write the failing diagnostics-helper tests**

Add focused tests in `tests/research/test_diagnostics.py` covering:

- window-level hit rate calculation from a simple per-symbol return fixture
- top and bottom contributor extraction with stable ordering
- aggregate summary calculation from multiple window diagnostics
- deterministic handling of empty or missing symbol-level inputs

- [ ] **Step 2: Run diagnostics-helper tests to verify RED**

Run: `pytest tests/research/test_diagnostics.py -q`
Expected: FAIL because diagnostics helpers and schema do not yet exist.

- [ ] **Step 3: Write the minimal diagnostics implementation**

Update `src/research/walk_forward.py` with small, testable helpers for:

- computing a window hit rate
- extracting a compact top/bottom contributor payload
- aggregating window-level diagnostics into summary-level totals or averages

Implementation constraints:

- keep the helper inputs pandas-native and deterministic
- use compact JSON-serializable payloads
- prefer `None` or empty lists over ambiguous sentinel strings

- [ ] **Step 4: Run diagnostics-helper tests to verify GREEN**

Run: `pytest tests/research/test_diagnostics.py -q`
Expected: PASS.

- [ ] **Step 5: Commit phase 1**

```bash
git add src/research/walk_forward.py tests/research/test_diagnostics.py
git commit -m "feat(research): add portfolio diagnostics helpers"
```

## Task 2: Add Window-Level Diagnostics to Walk-Forward Results

**Files:**
- Modify: `src/research/walk_forward.py`
- Modify: `tests/research/test_walk_forward.py`

- [ ] **Step 1: Write the failing walk-forward schema tests**

Extend `tests/research/test_walk_forward.py` to cover:

- each validation window includes `hit_rate`
- each validation window includes compact `top_contributors`
- each validation window includes compact `bottom_contributors`
- diagnostics are preserved alongside existing return and benchmark fields

- [ ] **Step 2: Run walk-forward tests to verify RED**

Run: `pytest tests/research/test_walk_forward.py -q`
Expected: FAIL because diagnostics fields are not yet present in window outputs.

- [ ] **Step 3: Write the minimal window-level implementation**

Update `run_walk_forward_experiment()` so each validation window stores:

- `hit_rate`
- `top_contributors`
- `bottom_contributors`

Use the already-scored or already-evaluated per-symbol research evidence when available. If a full per-symbol path is not yet available in a given branch of the code, keep the field present with deterministic empty payloads instead of inventing fragile approximations.

- [ ] **Step 4: Run walk-forward tests to verify GREEN**

Run: `pytest tests/research/test_walk_forward.py -q`
Expected: PASS.

- [ ] **Step 5: Run adjacent explainability coverage**

Run: `pytest tests/research/test_explain.py tests/scoring/test_multi_factor.py -q`
Expected: PASS, confirming diagnostics additions do not break existing explainability assumptions.

- [ ] **Step 6: Commit phase 2**

```bash
git add src/research/walk_forward.py tests/research/test_walk_forward.py
git commit -m "feat(research): add window diagnostics to walk-forward results"
```

## Task 3: Add Summary-Level Diagnostics Aggregates

**Files:**
- Modify: `src/research/walk_forward.py`
- Modify: `tests/research/test_walk_forward.py`

- [ ] **Step 1: Write the failing summary diagnostics tests**

Extend `tests/research/test_walk_forward.py` to cover summary-level fields such as:

- `avg_hit_rate`
- `top_contributors`
- `bottom_contributors`
- any compact aggregate derived from the existing window diagnostics

The tests should assert stable keys and deterministic ordering, not overfit to incidental formatting.

- [ ] **Step 2: Run targeted summary tests to verify RED**

Run: `pytest tests/research/test_walk_forward.py::test_run_walk_forward_experiment_returns_rebalance_weights_and_summary -q`
Expected: FAIL because summary diagnostics fields are missing.

- [ ] **Step 3: Write the minimal summary implementation**

Update the walk-forward summary payload so it includes compact portfolio diagnostics aggregated across windows. Keep v1 intentionally narrow:

- average hit rate across evaluated windows
- merged top contributors across windows
- merged bottom contributors across windows

Do not add plots, percent-of-total attribution math, or new CLI-only formatting structures in this phase.

- [ ] **Step 4: Run targeted summary tests to verify GREEN**

Run: `pytest tests/research/test_walk_forward.py::test_run_walk_forward_experiment_returns_rebalance_weights_and_summary -q`
Expected: PASS.

- [ ] **Step 5: Run full walk-forward regression coverage**

Run: `pytest tests/research/test_walk_forward.py tests/research/test_diagnostics.py -q`
Expected: PASS.

- [ ] **Step 6: Commit phase 3**

```bash
git add src/research/walk_forward.py tests/research/test_walk_forward.py tests/research/test_diagnostics.py
git commit -m "feat(research): aggregate portfolio diagnostics in summaries"
```

## Task 4: Persist Diagnostics in Research Artifacts

**Files:**
- Modify: `src/research/artifacts.py`
- Modify: `tests/research/test_artifacts.py`

- [ ] **Step 1: Write the failing artifact persistence tests**

Add artifact tests covering:

- diagnostics fields are preserved in saved summary JSON
- deterministic artifact output includes diagnostics when provided
- registry writing still succeeds with diagnostics-enriched summaries

- [ ] **Step 2: Run artifact tests to verify RED**

Run: `pytest tests/research/test_artifacts.py -q`
Expected: FAIL because persisted summaries do not yet assert diagnostics fields.

- [ ] **Step 3: Write the minimal artifact implementation**

Update artifact-writing helpers so diagnostics-rich summary payloads are preserved unchanged. Keep the registry compact; avoid duplicating large contributor lists if a summary already contains them.

- [ ] **Step 4: Run artifact tests to verify GREEN**

Run: `pytest tests/research/test_artifacts.py -q`
Expected: PASS.

- [ ] **Step 5: Run adjacent approval and artifact regression coverage**

Run: `pytest tests/research/test_artifacts.py tests/research/test_approved_params.py tests/research/test_approve_cli.py -q`
Expected: PASS.

- [ ] **Step 6: Commit phase 4**

```bash
git add src/research/artifacts.py tests/research/test_artifacts.py
git commit -m "feat(research): persist portfolio diagnostics in artifacts"
```

## Task 5: Surface Diagnostics in the Optimizer CLI

**Files:**
- Modify: `src/optimize.py`
- Modify: `tests/research/test_walk_forward.py`

- [ ] **Step 1: Write the failing optimizer output tests**

Extend optimizer CLI tests to assert that printed output includes:

- average hit rate
- compact contributor summary headings
- existing benchmark and return comparison lines remain present

- [ ] **Step 2: Run targeted optimizer tests to verify RED**

Run: `pytest tests/research/test_walk_forward.py::test_run_walk_forward_optimization_prints_one_shot_comparison -q`
Expected: FAIL because CLI output does not yet include diagnostics.

- [ ] **Step 3: Write the minimal CLI formatting implementation**

Update `src/optimize.py` so the optimizer summary prints a compact diagnostics section after the return and benchmark summary. Formatting constraints:

- keep the output single-screen friendly
- do not print raw JSON blobs
- truncate contributor lists to a small, deterministic count

- [ ] **Step 4: Run targeted optimizer tests to verify GREEN**

Run: `pytest tests/research/test_walk_forward.py::test_run_walk_forward_optimization_prints_one_shot_comparison -q`
Expected: PASS.

- [ ] **Step 5: Run broader research CLI regression coverage**

Run: `pytest tests/research/test_walk_forward.py tests/research/test_backtest_defaults.py -q`
Expected: PASS.

- [ ] **Step 6: Commit phase 5**

```bash
git add src/optimize.py tests/research/test_walk_forward.py
git commit -m "feat(cli): print portfolio diagnostics in optimize summary"
```

## Final Verification

- [ ] **Step 1: Run the complete milestone-adjacent regression set**

Run: `pytest tests/research/test_diagnostics.py tests/research/test_walk_forward.py tests/research/test_artifacts.py tests/research/test_explain.py tests/scoring/test_multi_factor.py tests/research/test_approved_params.py tests/research/test_approve_cli.py tests/research/test_backtest_defaults.py -q`
Expected: PASS.

- [ ] **Step 2: Review git status**

Run: `git status --short`
Expected: clean working tree.

- [ ] **Step 3: Prepare branch completion**

Use `superpowers:finishing-a-development-branch` after implementation is complete and verification is green.

## Notes for Execution

- Do not begin implementation on `main`; create an isolated worktree or branch first.
- Follow TDD strictly: every production change must be preceded by a failing test.
- Keep diagnostics schema compact and deterministic so it remains approval- and artifact-friendly.
- If contributor-level evidence requires a deeper research-data seam than expected, ship v1 with hit rate plus deterministic placeholder contributor payloads first, then deepen attribution in a follow-up slice.
