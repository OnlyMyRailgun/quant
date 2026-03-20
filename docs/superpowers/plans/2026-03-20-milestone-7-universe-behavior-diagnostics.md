# Milestone 7 Universe Behavior Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add lightweight larger-universe participation diagnostics so walk-forward research can show how much of the requested universe actually participated in each validation window.

**Architecture:** Extend the existing `src.optimize -> src.research.walk_forward -> artifact summary` path with additive validation-window participation metrics. Keep this slice narrow: no new loader return shape, no second reporting subsystem, and no changes to factor math or portfolio construction. Participation metrics are enabled only when the original requested universe symbols are explicitly available.

**Tech Stack:** Python, pandas, pytest, existing walk-forward research pipeline and artifact helpers

---

## File Structure

### Existing files to modify

- `src/optimize.py`
  Responsibility: gather validation-window participation counts from the requested universe plus sliced loaded data, pass those counts through validation metrics, and print the compact CLI summary.
- `src/research/walk_forward.py`
  Responsibility: persist additive per-window participation fields into walk-forward rows and aggregate summary-level participation diagnostics when present.
- `tests/research/test_walk_forward.py`
  Responsibility: regression coverage for walk-forward row shape, summary payloads, and optimizer CLI output.
- `tests/research/test_artifacts.py`
  Responsibility: artifact summary persistence coverage for new participation fields.

### Existing files to inspect but not necessarily modify

- `src/research/artifacts.py`
  Responsibility: persists summary payloads unchanged; likely no code change needed if the summary remains JSON-serializable.

### Boundaries

- Do not change `fetch_universe()` return shape.
- Do not infer `requested_symbol_count` from `data_dfs.keys()` when `universe_symbols` is unavailable.
- Do not add training-window participation metrics.
- Do not add symbol-level skip reasons to artifacts or CLI.

## Task 1: Add Participation Aggregation Helpers in Walk-Forward Research

**Files:**
- Modify: `src/research/walk_forward.py`
- Modify: `tests/research/test_walk_forward.py`

- [ ] **Step 1: Write the failing summary-helper tests**

Add dedicated focused tests in `tests/research/test_walk_forward.py` covering:

- summary aggregation of `avg_loaded_symbol_count`
- summary aggregation of `avg_skipped_symbol_count`
- summary aggregation of `avg_coverage_ratio`
- summary aggregation of `min_loaded_symbol_count`
- summary aggregation of `min_coverage_ratio`
- omission of these summary keys when no window supplies explicit participation fields

- [ ] **Step 2: Run the targeted tests to verify RED**

Run: `uv run pytest -q tests/research/test_walk_forward.py::test_run_walk_forward_experiment_aggregates_universe_participation_summary tests/research/test_walk_forward.py::test_run_walk_forward_experiment_omits_universe_participation_summary_when_not_provided`
Expected: FAIL because participation fields do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Update `src/research/walk_forward.py` to add a small helper that:

- reads explicit per-window participation values only when present
- aggregates summary metrics using plain Python `int` and `float`
- omits participation summary keys entirely when no windows provided them

Implementation constraints:

- `coverage_ratio` values are expected to already be rounded to 4 decimals by the caller
- keep existing return, benchmark, and portfolio-diagnostics aggregation unchanged

- [ ] **Step 4: Run the targeted tests to verify GREEN**

Run: `uv run pytest -q tests/research/test_walk_forward.py::test_run_walk_forward_experiment_aggregates_universe_participation_summary tests/research/test_walk_forward.py::test_run_walk_forward_experiment_omits_universe_participation_summary_when_not_provided`
Expected: PASS.

## Task 2: Thread Per-Window Participation Fields Through Walk-Forward Rows

**Files:**
- Modify: `src/research/walk_forward.py`
- Modify: `tests/research/test_walk_forward.py`

- [ ] **Step 1: Write the failing row-shape tests**

Add dedicated focused tests in `tests/research/test_walk_forward.py` so a walk-forward run with explicit participation metrics asserts:

- each row includes `requested_symbol_count`
- each row includes `loaded_symbol_count`
- each row includes `skipped_symbol_count`
- each row includes `coverage_ratio`

Also add a regression test asserting these row columns are omitted when the validation evaluator does not provide them.

- [ ] **Step 2: Run the targeted tests to verify RED**

Run: `uv run pytest -q tests/research/test_walk_forward.py::test_run_walk_forward_experiment_persists_universe_participation_fields tests/research/test_walk_forward.py::test_run_walk_forward_experiment_omits_universe_participation_columns_when_not_provided`
Expected: FAIL because the row fields are not yet persisted.

- [ ] **Step 3: Write the minimal implementation**

Update `run_walk_forward_experiment()` so it:

- copies the four participation fields from `validation_metrics` into each row when present
- does not synthesize placeholder `None` values when they are absent
- continues to work for existing callers that return only return/sharpe/symbol diagnostics

- [ ] **Step 4: Run the targeted tests to verify GREEN**

Run: `uv run pytest -q tests/research/test_walk_forward.py::test_run_walk_forward_experiment_persists_universe_participation_fields tests/research/test_walk_forward.py::test_run_walk_forward_experiment_omits_universe_participation_columns_when_not_provided`
Expected: PASS.

- [ ] **Step 5: Run adjacent walk-forward regression coverage**

Run: `uv run pytest -q tests/research/test_walk_forward.py`
Expected: PASS.

## Task 3: Compute Validation-Window Participation in the Optimizer Path

**Files:**
- Modify: `src/optimize.py`
- Modify: `tests/research/test_walk_forward.py`

- [ ] **Step 1: Write the failing optimizer contract tests**

Extend `tests/research/test_walk_forward.py` to cover:

- `run_walk_forward_optimization()` passes explicit participation fields through validation metrics when `universe_symbols` is provided
- `run_walk_forward_optimization()` counts symbols against the full requested universe even when:
  - a requested symbol never appears in `data_dfs`
  - a requested symbol exists in `data_dfs` but has an empty validation-window slice
- the summary contains participation aggregates for the offline smoke path when `universe_symbols` is provided
- the optimizer omits participation diagnostics entirely when `universe_symbols` is omitted

- [ ] **Step 2: Run the targeted tests to verify RED**

Run: `uv run pytest -q tests/research/test_walk_forward.py::test_run_walk_forward_optimization_computes_partial_universe_coverage tests/research/test_walk_forward.py::test_run_walk_forward_optimization_smoke_test_with_offline_stubbed_evaluator tests/research/test_walk_forward.py::test_run_walk_forward_optimization_omits_universe_participation_without_universe_symbols`
Expected: FAIL because `src.optimize` does not yet compute or pass participation metrics.

- [ ] **Step 3: Write the minimal implementation**

In `src/optimize.py`:

- add a small helper that computes validation-window participation from:
  - the explicit `universe_symbols` input
  - the already-loaded `data_dfs`
  - the validation start/end dates
- define:
  - `requested_symbol_count = len(universe_symbols)`
  - `loaded_symbol_count = count of requested symbols whose frame exists in data_dfs and yields a non-empty validation slice`
  - `skipped_symbol_count = requested - loaded`
  - `coverage_ratio = round(loaded / requested, 4)` or `0.0` when requested is `0`
- attach those fields to the validation evaluator result only
- do not compute these fields during training-window evaluation
- do not infer the denominator from `data_dfs.keys()` when `universe_symbols` is missing

- [ ] **Step 4: Run the targeted tests to verify GREEN**

Run: `uv run pytest -q tests/research/test_walk_forward.py::test_run_walk_forward_optimization_computes_partial_universe_coverage tests/research/test_walk_forward.py::test_run_walk_forward_optimization_smoke_test_with_offline_stubbed_evaluator tests/research/test_walk_forward.py::test_run_walk_forward_optimization_omits_universe_participation_without_universe_symbols`
Expected: PASS.

## Task 4: Surface Compact Participation Diagnostics in CLI Output

**Files:**
- Modify: `src/optimize.py`
- Modify: `tests/research/test_walk_forward.py`

- [ ] **Step 1: Write the failing CLI-output tests**

Extend `tests/research/test_walk_forward.py::test_run_walk_forward_optimization_prints_one_shot_comparison` to assert the output includes:

- `Average loaded symbols`
- `Average skipped symbols`
- `Average coverage ratio`
- `Minimum coverage ratio`

Assert representative numeric values too, for example:

- `Average loaded symbols        : 28.0000`
- `Minimum coverage ratio       : 0.5600`

Add a companion test asserting this section is omitted when participation keys are absent from the summary.

- [ ] **Step 2: Run the targeted tests to verify RED**

Run: `uv run pytest -q tests/research/test_walk_forward.py::test_run_walk_forward_optimization_prints_one_shot_comparison tests/research/test_walk_forward.py::test_run_walk_forward_optimization_skips_universe_participation_section_when_absent`
Expected: FAIL because the CLI section does not yet exist.

- [ ] **Step 3: Write the minimal implementation**

Update `src/optimize.py` so the optimizer summary:

- prints the four compact participation lines only when the summary contains participation keys
- leaves the current weights table and existing return/benchmark/portfolio-diagnostics output intact

- [ ] **Step 4: Run the targeted tests to verify GREEN**

Run: `uv run pytest -q tests/research/test_walk_forward.py::test_run_walk_forward_optimization_prints_one_shot_comparison tests/research/test_walk_forward.py::test_run_walk_forward_optimization_skips_universe_participation_section_when_absent`
Expected: PASS.

## Task 5: Verify Artifact Persistence for Participation Diagnostics

**Files:**
- Modify: `tests/research/test_artifacts.py`

- [ ] **Step 1: Extend the artifact regression test**

Extend `tests/research/test_artifacts.py::test_write_walk_forward_run_persists_diagnostics_in_summary` to also cover:

- summary JSON preserves `avg_loaded_symbol_count`
- summary JSON preserves `avg_skipped_symbol_count`
- summary JSON preserves `avg_coverage_ratio`
- summary JSON preserves `min_loaded_symbol_count`
- summary JSON preserves `min_coverage_ratio`

- [ ] **Step 2: Run the targeted regression test**

Run: `uv run pytest -q tests/research/test_artifacts.py::test_write_walk_forward_run_persists_diagnostics_in_summary`
Expected: PASS once the fixture summary includes the new fields, unless serialization unexpectedly breaks.

- [ ] **Step 3: Keep production artifact code unchanged unless needed**

Because `src/research/artifacts.py` already writes summaries unchanged, prefer:

- updating the test fixture summary payload to include the new fields
- leaving production artifact code untouched unless a real serialization issue appears

- [ ] **Step 4: Run adjacent artifact regression coverage**

Run: `uv run pytest -q tests/research/test_artifacts.py tests/research/test_approved_params.py tests/research/test_approve_cli.py`
Expected: PASS.

## Final Verification

- [ ] **Step 1: Run the larger-universe diagnostics regression set**

Run: `uv run pytest -q tests/research/test_walk_forward.py tests/research/test_artifacts.py`
Expected: PASS.

- [ ] **Step 2: Run the full regression suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 3: Review git status**

Run: `git status --short`
Expected: only intended changes remain.

- [ ] **Step 4: Commit the implementation**

```bash
git add src/optimize.py src/research/walk_forward.py tests/research/test_walk_forward.py tests/research/test_artifacts.py
git commit -m "feat(research): add universe behavior diagnostics"
```
