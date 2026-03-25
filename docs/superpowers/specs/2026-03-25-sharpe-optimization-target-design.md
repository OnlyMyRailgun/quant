# Sharpe Optimization Target Design

Date: 2026-03-25

## Goal

Reduce walk-forward overfitting by changing walk-forward weight selection to prefer
`sharpe` instead of raw `return_pct` when ranking candidate weight tuples.

This slice is intentionally narrow:

- change only the walk-forward weight-selection target
- remove the all-zero weight tuple from the optimization grid
- compare the effect on the current best research candidates:
  - `12_1 + vol`

## Why This Slice

The current optimizer behavior is already identified as a likely overfitting source.

The evidence is straightforward:

- training windows select by `return_pct`
- `sharpe` is only a secondary tie-breaker
- train/validation gaps have already been observed at materially large levels

That means the optimizer is rewarded for choosing the most fortunate training-window
weight combination, not the most robust one.

This slice directly targets that confirmed failure mode.

## Non-Goals

This slice does not:

- change approved-params selection logic
- change best-run lifecycle or approval governance
- change paper-trading defaults
- change production strategy defaults
- add new factors
- redesign the local Parquet data store

Those are separate concerns and should not be mixed into this change.

## Recommendation

Use a Sharpe-first ordering rule inside walk-forward weight selection and remove the
degenerate `(0.0, 0.0, 0.0)` weight tuple from the search grid.

This is preferred over broader alternatives because:

- it directly addresses the known optimizer failure mode
- it keeps the slice small and easy to verify
- it does not require a new run-governance policy
- it gives a clean before/after comparison for the current factor candidates

## Alternatives Considered

### Option A: Keep `return_pct` primary and only tweak tie-breakers

Rejected.

This does not change the core incentive. The optimizer would still choose the
luckiest training-window result first.

### Option B: Replace the optimizer target with Sharpe-first ordering

Recommended.

This changes the selection objective at the exact point where overfitting is being
introduced while preserving the rest of the research pipeline.

### Option C: Change both optimizer target and approval-governance target together

Rejected for this slice.

That would mix research signal quality with process governance and make it harder to
attribute any improvement.

## Design

### 1. Weight-selection ordering

Current walk-forward weight ranking sorts by:

1. `return_pct`
2. `sharpe`
3. weight values

This slice should change it to:

1. `sharpe`
2. `return_pct`
3. weight values

Why this ordering:

- `sharpe` becomes the primary robustness signal
- `return_pct` still matters as a secondary discriminator
- deterministic weight tie-breaks remain unchanged

### 2. Remove the all-zero tuple

The tuple `(0.0, 0.0, 0.0)` should be removed from the default optimization grid.

Why:

- it is not a meaningful factor portfolio
- it can act like a degenerate “do nothing” candidate
- keeping it in the search space makes optimizer diagnostics noisier

This is a low-cost cleanup that aligns with the intended research objective.

### 3. Preserve current research interfaces

The following should remain unchanged:

- artifact format
- walk-forward metadata shape
- approved params workflow
- local-store loading path
- benchmark comparison reporting

The only user-visible behavioral change in this slice should be which weight tuple is
selected within each training window.

### 4. Verification focus

The right success measure for this slice is not just higher raw return.

Primary verification targets:

- narrower train/validation gap
- more stable validation behavior across windows
- reasonable retention of walk-forward return

For this slice, compare:

- `12_1 + vol`

using the local Parquet research store and the longer synced history now available.

## File Impact

Expected primary files:

- `src/research/walk_forward.py`
  - change leaderboard ordering in `select_best_weights(...)`
- `src/optimize.py`
  - remove `(0.0, 0.0, 0.0)` from the default grid if still present there
- `tests/research/test_walk_forward.py`
  - add regression tests for Sharpe-first selection

No other files should need behavioral changes in this slice unless a small helper is
required for clean testability.

## Testing Strategy

### Unit / integration tests

Add tests proving:

- `select_best_weights(...)` now prefers higher `sharpe` over higher `return_pct`
- tie-breaking still falls back to `return_pct` when Sharpe is equal
- the default weight grid no longer contains `(0.0, 0.0, 0.0)`

### Research comparison

Run before/after comparisons for:

- `12_1 + vol`

Record at minimum:

- training-window selected weights
- walk-forward return
- average validation hit rate
- train/validation gap

Results should be recorded in the investigation document or as a new research note
under `docs/`, not only printed to terminal output.

## Acceptance Criteria

This slice is complete when:

1. walk-forward weight ranking is Sharpe-first
2. the all-zero tuple is removed from the default grid
3. existing tests pass with updated expectations
4. longer-history research reruns for `12_1 + vol` show narrower
   average train/validation gap compared to the `return_pct`-first baseline, with
   walk-forward return remaining positive
5. approved params and paper-trading logic remain unchanged

## Expected Next Slice

After this slice, likely next decisions are:

- whether `12_1 + vol` is still structurally weaker than the single-factor variants
- whether a narrower candidate family around `12_1 + vol` is worth exploring
- whether approval governance should later consume a more risk-aware run-selection signal
