# Research 12-1 Momentum Design

Date: 2026-03-21

## Goal

Add a research-only path that allows walk-forward experiments to use classic `12-1` momentum instead of the current `90`-day momentum, without changing the production strategy path, paper trading defaults, or live execution behavior.

## Why This Slice Comes First

The current investigation now supports three specific conclusions:

1. the repaired diagnostics path no longer supports the existing `90`-day momentum definition as the best momentum baseline
2. classic `12-1` momentum has better repaired cross-sectional IC than the current `90`-day definition on the more important `japan_large_30` and `japan_broad_50` universes
3. the optimizer currently still overfits on training-window `return_pct`, but changing that objective at the same time would introduce a second moving variable

Because of that, the cleanest next slice is:

- keep the current optimizer target unchanged
- change only the research momentum definition
- measure whether the real walk-forward research path improves

## Non-Goals

This slice explicitly does **not** do the following:

- does not modify [/Users/y-yang/Developer/quant/src/strategies/multi_factor.py](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py)
- does not modify paper-trading defaults in [/Users/y-yang/Developer/quant/src/paper/bot.py](/Users/y-yang/Developer/quant/src/paper/bot.py)
- does not change the production shared scorer default in [/Users/y-yang/Developer/quant/src/scoring/multi_factor.py](/Users/y-yang/Developer/quant/src/scoring/multi_factor.py)
- does not change walk-forward weight selection away from training-window `return_pct`
- does not introduce new factor families such as value
- does not attempt to solve `mom + vol` combination logic in this slice

## Research Question

Using the real walk-forward producer path, does a research-only `12-1` momentum definition outperform the current `90`-day momentum definition when everything else is held constant?

Held constant:

- date range
- universe
- walk-forward windowing
- `top_n` resolution
- optimizer target
- transaction / backtest mechanics

Changed:

- only the momentum definition used by the research scorer

## Proposed Approach

### Option A: Replace the shared scorer default globally

This would be the shortest code path, but it is too risky for this slice.

Why rejected:

- it changes strategy parity behavior
- it changes paper-trading and live signal generation
- it makes the research result harder to isolate

### Option B: Add a research-only scorer entry point and thread it through optimize

This is the recommended option.

Why:

- isolates the behavior to research / walk-forward only
- leaves production-path strategy code untouched
- lets the optimizer and diagnostics use the same alternative scorer
- creates a clean seam for later factor experiments

### Option C: Keep using ad-hoc notebooks/scripts only

This is too weak for the next stage.

Why rejected:

- results are harder to reproduce
- the main walk-forward producer path remains unable to test the candidate factor under its real selection loop
- later follow-up work would need to repeat the same scaffolding

## Design

### 1. Add a research-only alternative scorer

Create a new scorer module under research or scoring that computes the same score table shape as the shared multi-factor scorer, but supports:

- `momentum_definition="90d"` or `"12_1"`
- existing `vol` and `rev` columns when needed
- the same ranking output shape used by diagnostics and walk-forward artifacts

For this slice, the critical requirement is that the research scorer returns the same structural columns:

- `symbol`
- `price`
- `mom_raw`
- `vol_raw`
- `rev_raw`
- `mom_z`
- `vol_z`
- `rev_z`
- contributions
- `total_score`
- `rank`
- `is_top_n`

This keeps the diagnostics and artifact path reusable.

### 2. Thread the research scorer into optimize / walk-forward only

Add a research-only configuration seam to the optimize path so that walk-forward experiments can choose the momentum definition without changing the production strategy class.

The seam should support:

- default behavior unchanged: current `90d` research path remains the default
- optional research override: `momentum_definition="12_1"`

The override must affect:

- training-window scoring used during weight selection
- validation-window scoring returned in `scores`
- rebalance-aligned factor diagnostics inside walk-forward

The override must **not** affect:

- strategy class defaults
- main CLI trading path
- paper bot signal generation

### 3. Preserve current production path behavior

Current production behavior must remain unchanged when the new research-only option is not used.

That means:

- existing tests for strategy parity should still pass
- existing optimize behavior should still use `90d` momentum unless explicitly told otherwise
- the new scorer option is additive, not a silent replacement

### 4. Validate with a narrow first experiment set

This slice should only validate the simplest decisive experiment:

- current `90d mom-only`
- research-only `12-1 mom-only`

on the real walk-forward producer path.

Success for this slice is not “beat TOPIX.”

Success is:

- the new option runs through the real walk-forward path
- it produces valid diagnostics and artifacts
- it improves the momentum baseline relative to the old `90d` version in a reproducible way

## Output Contract

The resulting research run should still produce the normal walk-forward artifacts:

- `metadata.json`
- `weights.csv`
- `summary.json`
- `factor_diagnostics.csv`

The metadata should record the research momentum definition used, for example:

```json
{
  "momentum_definition": "12_1"
}
```

This must be explicit so later artifact readers can distinguish:

- legacy `90d` runs
- research-only `12-1` runs

## Testing Strategy

### Unit Tests

Add focused tests for the research scorer:

- `12-1` momentum computes the expected lagged return
- insufficient history omits the symbol cleanly
- the new scorer preserves the expected score table shape

### Optimize / Walk-Forward Integration Tests

Add tests that prove:

- optimize can select the research scorer without changing default behavior
- validation `scores` use the requested momentum definition
- walk-forward diagnostics still work on the resulting score table
- artifact metadata records the selected momentum definition

### Regression Guard

Keep an explicit regression test proving:

- default optimize path still uses the current `90d` setup when no override is provided

## Acceptance Criteria

This slice is complete when:

1. a research-only `12-1` momentum option exists
2. the option is threaded through the real walk-forward producer path
3. default production-path behavior is unchanged
4. walk-forward runs with the new option produce complete diagnostics artifacts
5. a direct `90d mom-only` vs `12-1 mom-only` comparison can be run reproducibly on the main research path

## Expected Next Slice After This One

If `12-1` improves the real walk-forward momentum baseline, the next slice should be:

- change optimizer selection away from pure `return_pct`

If it does not, then the current momentum redesign hypothesis needs to be revisited before changing the optimizer target.
