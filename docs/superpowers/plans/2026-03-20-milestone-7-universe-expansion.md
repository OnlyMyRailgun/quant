# Milestone 7 Universe Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the named universe registry so Milestone 7 can run larger configured universes without changing strategy code.

**Architecture:** Keep the implementation intentionally narrow: add a few larger static named universes in `src/data/universe.py`, preserve the existing API and CLI behavior, and update tests plus README so the new capability is explicit and verified. This slice does not change factor math, loaders, or portfolio logic.

**Tech Stack:** Python, pytest, existing CLI and universe registry helpers

---

## File Structure

### Existing files to modify

- `src/data/universe.py`
  Responsibility: named universe definitions and lookup helpers.
- `tests/data/test_universe.py`
  Responsibility: deterministic coverage for registry order, lookup, and compatibility.
- `README.md`
  Responsibility: milestone status and current capability summary.

## Task 1: Expand the Named Universe Registry

**Files:**
- Modify: `src/data/universe.py`
- Modify: `tests/data/test_universe.py`

- [ ] **Step 1: Write the failing tests**

Add tests covering:

- additional named universes are listed in stable order
- each larger universe resolves to a deterministic ordered symbol list
- the existing `topix_top_10` compatibility path still works unchanged

- [ ] **Step 2: Run the targeted tests to verify RED**

Run: `uv run pytest -q tests/data/test_universe.py`
Expected: FAIL because the new universe names and sizes do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Implement 2 larger curated Japanese equity universes in `src/data/universe.py` while preserving:

- `list_universe_names()`
- `get_universe(name: str)`
- `get_topix_top_10()`

- [ ] **Step 4: Run the targeted tests to verify GREEN**

Run: `uv run pytest -q tests/data/test_universe.py`
Expected: PASS.

## Task 2: Sync Roadmap Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update Milestone 7 status wording**

Revise README so it reflects that the project now includes broader configured universes, while keeping larger-universe behavior analysis and lifecycle states as future work.

- [ ] **Step 2: Run adjacent regression coverage**

Run: `uv run pytest -q tests/data/test_universe.py tests/research/test_backtest_defaults.py`
Expected: PASS.

## Final Verification

- [ ] **Step 1: Run the full regression suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 2: Review git status**

Run: `git status --short`
Expected: only intended changes remain.
