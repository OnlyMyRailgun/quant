# Platform Foundation Next Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the next unfinished research-platform slice by adding reproducible named universes, a lightweight historical data-validation layer, and roadmap documentation that matches the implemented system.

**Architecture:** This plan follows `docs/superpowers/specs/2026-03-20-platform-foundation-next-slice-design.md`, which is explicitly a follow-on slice after the already-implemented shared-scoring/artifact foundation. Work is split into parallel-safe foundations first: universe registry and data validation. CLI and artifact wiring happens only after the universe registry is in place, and README updates happen last after code and tests are green.

**Tech Stack:** Python, pandas, pytest, argparse, existing research artifact helpers

---

## File Structure

### Existing files to modify

- `src/data/universe.py`
  Responsibility: named and reproducible universe definitions.
- `src/data/bulk_loader.py`
  Responsibility: cache-backed universe loading and validation integration.
- `src/optimize.py`
  Responsibility: walk-forward CLI universe selection and artifact metadata inputs.
- `src/main.py`
  Responsibility: backtest CLI universe selection.
- `src/research/artifacts.py`
  Responsibility: experiment metadata persistence.
- `README.md`
  Responsibility: roadmap state, milestone completion notes, and next-step guidance.
- `tests/data/test_universe.py`
  Responsibility: regression coverage for named universe definitions.
- `tests/data/test_bulk_loader.py`
  Responsibility: regression coverage for cache loading and validation behavior.
- `tests/research/test_artifacts.py`
  Responsibility: regression coverage for persisted experiment metadata.
- `tests/research/test_backtest_defaults.py`
  Responsibility: CLI and approved-parameter smoke coverage.
- `tests/research/test_walk_forward.py`
  Responsibility: walk-forward CLI and summary regression coverage.

### New files to create

- `src/research/data_validation.py`
  Responsibility: deterministic validation helpers for historical price frames.
- `tests/research/test_data_validation.py`
  Responsibility: unit tests for validation summaries and failure cases.

### Parallel Boundaries

- Task 1 and Task 2 are the only parallel-safe tasks.
- Task 3 depends on Task 1.
- Task 4 should happen only after Tasks 1-3 are green.

## Task 1: Add Reproducible Named Universe Selection

**Files:**
- Modify: `src/data/universe.py`
- Modify: `tests/data/test_universe.py`

- [ ] **Step 1: Write the failing universe-registry tests**

Add tests that cover:

- listing available universe names
- resolving a named universe into a stable ordered symbol list
- rejecting unknown universe names
- preserving `get_topix_top_10()` compatibility

- [ ] **Step 2: Run the targeted tests to verify RED**

Run: `pytest tests/data/test_universe.py -q`
Expected: FAIL because named-universe helpers do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Implement in `src/data/universe.py`:

- a named universe registry
- `list_universe_names()`
- `get_universe(name: str) -> list[str]`
- compatibility helper `get_topix_top_10()` that delegates to the named registry

- [ ] **Step 4: Run the targeted tests to verify GREEN**

Run: `pytest tests/data/test_universe.py -q`
Expected: PASS.

- [ ] **Step 5: Run adjacent regression coverage**

Run: `pytest tests/scoring/test_multi_factor.py -q`
Expected: PASS.

## Task 2: Add Lightweight Historical Data Validation

**Files:**
- Create: `src/research/data_validation.py`
- Modify: `src/data/bulk_loader.py`
- Create: `tests/research/test_data_validation.py`
- Modify: `tests/data/test_bulk_loader.py`

- [ ] **Step 1: Write the failing validation tests**

Add tests that cover:

- validation summary for a clean price frame
- invalid result for duplicate timestamps
- invalid result for missing `Close`
- invalid result for non-positive or non-finite closes
- loader behavior skipping invalid symbols with a structured reason

- [ ] **Step 2: Run the targeted tests to verify RED**

Run: `pytest tests/research/test_data_validation.py tests/data/test_bulk_loader.py -q`
Expected: FAIL because the validation module and loader integration do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Implement `src/research/data_validation.py` so it returns a deterministic validation result with:

- `is_valid`
- `issues`
- `row_count`
- `start`
- `end`

Integration contract:

- invalid symbols are skipped
- each skipped symbol emits a clear reason
- valid symbols continue through the loader path

- [ ] **Step 4: Run the targeted tests to verify GREEN**

Run: `pytest tests/research/test_data_validation.py tests/data/test_bulk_loader.py -q`
Expected: PASS.

- [ ] **Step 5: Run adjacent regression coverage**

Run: `pytest tests/scoring/test_multi_factor.py tests/research/test_approved_params.py -q`
Expected: PASS.

## Task 3: Thread Universe Selection Into CLI and Artifacts

**Files:**
- Modify: `src/main.py`
- Modify: `src/optimize.py`
- Modify: `src/research/artifacts.py`
- Modify: `tests/research/test_backtest_defaults.py`
- Modify: `tests/research/test_walk_forward.py`
- Modify: `tests/research/test_artifacts.py`

- [ ] **Step 1: Write the failing integration tests**

Add tests that cover:

- backtest CLI defaulting to the named Topix-10 universe without changing current behavior
- optional explicit universe selection in CLI paths
- persisted artifact metadata including `universe_name` and `universe_symbols`

- [ ] **Step 2: Run the targeted tests to verify RED**

Run: `pytest tests/research/test_backtest_defaults.py tests/research/test_walk_forward.py tests/research/test_artifacts.py -q`
Expected: FAIL because CLI wiring and metadata fields do not exist yet.

- [ ] **Step 3: Write the minimal integration implementation**

Implement:

- explicit universe selection in `src/main.py` and `src/optimize.py`
- unchanged defaults for existing paths
- artifact metadata fields:
  - `universe_name`
  - `universe_symbols`

- [ ] **Step 4: Run the targeted tests to verify GREEN**

Run: `pytest tests/research/test_backtest_defaults.py tests/research/test_walk_forward.py tests/research/test_artifacts.py -q`
Expected: PASS.

- [ ] **Step 5: Run adjacent regression coverage**

Run: `pytest tests/scoring/test_multi_factor.py tests/research/test_approved_params.py -q`
Expected: PASS.

## Task 4: Sync README With Actual Milestone State

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update milestone statuses and completion notes**

Revise `README.md` so it reflects the current codebase reality using implemented evidence from code and tests:

- Milestone 3 should no longer say `not started`
- Milestone X should list approval flow and benchmark output as completed
- Milestone 7 should describe which prerequisites are already in place versus what remains

- [ ] **Step 2: Document the new foundation slice**

Add concise notes for:

- explicit universe selection and reproducibility
- basic data validation layer
- any new CLI flag or artifact metadata field introduced by Tasks 1-3

- [ ] **Step 3: Run README-adjacent regression coverage**

Run: `pytest tests/research/test_backtest_defaults.py tests/research/test_walk_forward.py -q`
Expected: PASS.

## Final Verification

- [ ] **Step 1: Run the complete regression set**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 2: Review git status**

Run: `git status --short`
Expected: only intended changes remain.

- [ ] **Step 3: Prepare branch completion**

Use `superpowers:finishing-a-development-branch` after implementation is complete and verification is green.

## Notes for Execution

- Do not weaken current defaults just to expose a new universe-selection API.
- Follow TDD strictly: every production change must be preceded by a failing test.
- Keep factor math and portfolio behavior unchanged in this slice.
- Treat README updates as the final integration pass after code and tests are green.
