# Research 12-1 Momentum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a research-only `12-1` momentum option to the real walk-forward producer path so we can compare it against the current `90d` momentum definition without changing production strategy behavior.

**Architecture:** Introduce a research scorer seam that preserves the existing score-table shape while allowing an alternative momentum definition. Thread that seam through optimize and walk-forward only, record the selected definition in artifacts, and keep the default `90d` path unchanged. Validate with TDD at the scorer, optimize, and artifact layers.

**Tech Stack:** Python, pandas, pytest, Backtrader-backed research pipeline

---

## File Map

**Create:**

- `src/research/research_scoring.py`
  Responsibility: research-only scorer entry point with selectable momentum definition and output shape compatible with existing diagnostics.
- `tests/research/test_research_scoring.py`
  Responsibility: unit tests for `12-1` momentum calculation, shape compatibility, and insufficient-history handling.

**Modify:**

- `src/optimize.py`
  Responsibility: add the research-only momentum-definition seam to walk-forward optimization without changing default behavior.
- `src/research/walk_forward.py`
  Responsibility: use the requested research scorer during rebalance-aligned diagnostics when an override is active.
- `src/research/artifacts.py`
  Responsibility: persist research metadata cleanly if needed by the optimize call site.
- `tests/research/test_walk_forward.py`
  Responsibility: integration tests for scorer selection, validation-score propagation, diagnostics compatibility, and default behavior preservation.

## Task 1: Add the Research Scorer Module

**Files:**

- Create: `src/research/research_scoring.py`
- Test: `tests/research/test_research_scoring.py`

- [ ] **Step 1: Write the failing scorer tests**

```python
def test_score_research_universe_supports_12_1_momentum_definition():
    ...


def test_score_research_universe_skips_symbols_without_12_1_history():
    ...


def test_score_research_universe_preserves_multi_factor_score_shape():
    ...
```

- [ ] **Step 2: Run the scorer tests to verify RED**

Run:

```bash
uv run pytest -q tests/research/test_research_scoring.py
```

Expected:

- FAIL because `src/research/research_scoring.py` does not exist yet

- [ ] **Step 3: Write the minimal research scorer**

Implement `src/research/research_scoring.py` with:

- a public scorer such as `score_research_universe(...)`
- `momentum_definition: Literal["90d", "12_1"] = "90d"`
- internal helper for current `90d` momentum
- internal helper for classic `12-1` momentum using a `252`-day lookback and `21`-day skip
- the same score-table columns returned by the shared scorer
- no dependency on strategy classes

- [ ] **Step 4: Re-run the scorer tests to verify GREEN**

Run:

```bash
uv run pytest -q tests/research/test_research_scoring.py
```

Expected:

- PASS

- [ ] **Step 5: Commit the scorer slice**

```bash
git add src/research/research_scoring.py tests/research/test_research_scoring.py
git commit -m "feat(research): add configurable research scorer"
```

## Task 2: Thread the Research Scorer Through Optimize

**Files:**

- Modify: `src/optimize.py`
- Test: `tests/research/test_walk_forward.py`

- [ ] **Step 1: Write the failing optimize integration tests**

Add tests covering:

- default optimize path still uses `90d`
- an explicit `momentum_definition="12_1"` override selects the research scorer
- validation metrics `scores` reflect the requested momentum definition

Example shape:

```python
def test_run_walk_forward_optimization_defaults_to_90d_momentum(...):
    ...


def test_run_walk_forward_optimization_accepts_12_1_momentum_override(...):
    ...
```

- [ ] **Step 2: Run the targeted optimize tests to verify RED**

Run:

```bash
uv run pytest -q tests/research/test_walk_forward.py -k "12_1 or momentum_definition"
```

Expected:

- FAIL because the seam is not threaded yet

- [ ] **Step 3: Implement the optimize seam**

Update `src/optimize.py` so that:

- `evaluate_weight_tuple(...)` can accept a research-only `momentum_definition`
- `run_walk_forward_optimization(...)` can accept and forward the same option
- default behavior remains `90d`
- no strategy-class defaults are changed

- [ ] **Step 4: Re-run the targeted optimize tests to verify GREEN**

Run:

```bash
uv run pytest -q tests/research/test_walk_forward.py -k "12_1 or momentum_definition"
```

Expected:

- PASS

- [ ] **Step 5: Commit the optimize seam**

```bash
git add src/optimize.py tests/research/test_walk_forward.py
git commit -m "feat(research): add 12-1 momentum override to optimize"
```

## Task 3: Keep Rebalance-Aligned Diagnostics Compatible

**Files:**

- Modify: `src/research/walk_forward.py`
- Test: `tests/research/test_walk_forward.py`

- [ ] **Step 1: Write the failing diagnostics compatibility tests**

Add tests proving:

- rebalance-aligned diagnostics use the requested research scorer when the override is active
- diagnostics still produce `mom_ic` / bucket rows under `12-1`
- default diagnostics still use the current scorer when no override is provided

- [ ] **Step 2: Run the targeted diagnostics tests to verify RED**

Run:

```bash
uv run pytest -q tests/research/test_walk_forward.py -k "rebalance and 12_1"
```

Expected:

- FAIL until walk-forward uses the scorer seam consistently

- [ ] **Step 3: Implement the minimal diagnostics integration**

Update `src/research/walk_forward.py` so that:

- event-level score reconstruction can call the research scorer with the requested momentum definition
- score-table shape remains compatible with existing diagnostics
- no production-path strategy behavior changes

- [ ] **Step 4: Re-run the targeted diagnostics tests to verify GREEN**

Run:

```bash
uv run pytest -q tests/research/test_walk_forward.py -k "rebalance and 12_1"
```

Expected:

- PASS

- [ ] **Step 5: Commit the diagnostics integration**

```bash
git add src/research/walk_forward.py tests/research/test_walk_forward.py
git commit -m "fix(research): support 12-1 momentum in diagnostics"
```

## Task 4: Record the Research Configuration in Artifacts

**Files:**

- Modify: `src/optimize.py`
- Modify: `src/research/artifacts.py`
- Test: `tests/research/test_walk_forward.py`

- [ ] **Step 1: Write the failing metadata test**

Add a test asserting that a `12_1` run records the momentum definition in artifact metadata.

Example:

```python
def test_run_walk_forward_optimization_persists_momentum_definition_metadata(...):
    ...
```

- [ ] **Step 2: Run the metadata test to verify RED**

Run:

```bash
uv run pytest -q tests/research/test_walk_forward.py -k "persists_momentum_definition_metadata"
```

Expected:

- FAIL until metadata is written

- [ ] **Step 3: Implement metadata threading**

Ensure artifact metadata includes:

```json
{
  "momentum_definition": "12_1"
}
```

for override runs, while leaving existing metadata intact.

- [ ] **Step 4: Re-run the metadata test to verify GREEN**

Run:

```bash
uv run pytest -q tests/research/test_walk_forward.py -k "persists_momentum_definition_metadata"
```

Expected:

- PASS

- [ ] **Step 5: Commit the metadata change**

```bash
git add src/optimize.py src/research/artifacts.py tests/research/test_walk_forward.py
git commit -m "feat(research): persist momentum definition metadata"
```

## Task 5: Run the First Real Comparison

**Files:**

- No required code changes unless small research helpers are needed
- Verification target: real walk-forward artifacts

- [ ] **Step 1: Run the current baseline**

Run a `mom-only` walk-forward with the default `90d` momentum definition on the selected universes.

- [ ] **Step 2: Run the `12-1` comparison**

Run the same `mom-only` walk-forward with `momentum_definition="12_1"` on the same universes and same date range.

- [ ] **Step 3: Compare the outputs**

Record at minimum:

- walk-forward return
- excess vs benchmark
- repaired `mom_ic`
- train-validation gap

- [ ] **Step 4: Verify no regressions in the full test suite**

Run:

```bash
uv run pytest -q
```

Expected:

- PASS with only existing warnings

- [ ] **Step 5: Commit the final slice**

```bash
git add src/research/research_scoring.py src/optimize.py src/research/walk_forward.py src/research/artifacts.py tests/research/test_research_scoring.py tests/research/test_walk_forward.py
git commit -m "feat(research): add 12-1 momentum research path"
```

## Notes For Execution

- Keep this slice research-only. Do not modify `src/strategies/multi_factor.py`.
- Keep default `90d` behavior untouched unless an explicit research override is present.
- Do not combine this slice with the optimizer-target change.
- Do not introduce `vol` mixing logic changes yet; that is a later slice.
