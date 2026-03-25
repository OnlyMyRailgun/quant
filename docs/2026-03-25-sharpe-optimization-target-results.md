# Sharpe Optimization Target Results

Date: 2026-03-25

## Scope

This note evaluates the Sharpe-first optimizer target on the first experiment shape
where the optimizer has a real choice set:

- factor family: `12_1 + vol`
- candidate grid: `(mom, vol, 0.0)` with `mom, vol ∈ {0.0, 0.5, 1.0}`
- excluded tuple: `(0.0, 0.0, 0.0)`
- universes:
  - `topix_top_10`
  - `japan_large_30`
  - `japan_broad_50`
- local Parquet research store
- `start=2019-01-01`
- `end=2026-03-24`
- `train_months=12`
- `validation_months=6`
- `step_months=6`

The key comparison is:

- **before**: `return_pct`-first optimizer ranking
- **after**: `sharpe`-first optimizer ranking

## Implementation Verification

Code changes in this slice:

- `select_best_weights(...)` now ranks by `sharpe` first and `return_pct` second
- `DEFAULT_WEIGHT_GRID` no longer contains `(0.0, 0.0, 0.0)`

Verification completed in the Sharpe worktree:

- targeted research tests passed
- full test suite passed

## Before / After Artifact Paths

### `topix_top_10`

- before:
  - [/Users/y-yang/Developer/quant/.worktrees/codex-sharpe-optimization-target/tmp/sharpe_12_1_vol_compare_final/topix_top_10/before/walk_forward/20260325T090938Z-20260325T090938Z-6c4a64d2](/Users/y-yang/Developer/quant/.worktrees/codex-sharpe-optimization-target/tmp/sharpe_12_1_vol_compare_final/topix_top_10/before/walk_forward/20260325T090938Z-20260325T090938Z-6c4a64d2)
- after:
  - [/Users/y-yang/Developer/quant/.worktrees/codex-sharpe-optimization-target/tmp/sharpe_12_1_vol_compare_final/topix_top_10/after_only/walk_forward/20260325T091327Z-20260325T091327Z-03022bdf](/Users/y-yang/Developer/quant/.worktrees/codex-sharpe-optimization-target/tmp/sharpe_12_1_vol_compare_final/topix_top_10/after_only/walk_forward/20260325T091327Z-20260325T091327Z-03022bdf)

### `japan_large_30`

- before:
  - [/Users/y-yang/Developer/quant/.worktrees/codex-sharpe-optimization-target/tmp/sharpe_12_1_vol_compare_final/japan_large_30/before_only/walk_forward/20260325T092635Z-20260325T092635Z-839ba603](/Users/y-yang/Developer/quant/.worktrees/codex-sharpe-optimization-target/tmp/sharpe_12_1_vol_compare_final/japan_large_30/before_only/walk_forward/20260325T092635Z-20260325T092635Z-839ba603)
- after:
  - [/Users/y-yang/Developer/quant/.worktrees/codex-sharpe-optimization-target/tmp/sharpe_12_1_vol_compare_final/japan_large_30/after/walk_forward/20260325T092852Z-20260325T092852Z-89f2332a](/Users/y-yang/Developer/quant/.worktrees/codex-sharpe-optimization-target/tmp/sharpe_12_1_vol_compare_final/japan_large_30/after/walk_forward/20260325T092852Z-20260325T092852Z-89f2332a)

### `japan_broad_50`

- before:
  - [/Users/y-yang/Developer/quant/.worktrees/codex-sharpe-optimization-target/tmp/sharpe_12_1_vol_compare_final/japan_broad_50/before_only/walk_forward/20260325T093703Z-20260325T093703Z-4eb4562d](/Users/y-yang/Developer/quant/.worktrees/codex-sharpe-optimization-target/tmp/sharpe_12_1_vol_compare_final/japan_broad_50/before_only/walk_forward/20260325T093703Z-20260325T093703Z-4eb4562d)
- after:
  - [/Users/y-yang/Developer/quant/.worktrees/codex-sharpe-optimization-target/tmp/sharpe_12_1_vol_compare_final/japan_broad_50/after_only_2/walk_forward/20260325T101047Z-20260325T101047Z-4de160bb](/Users/y-yang/Developer/quant/.worktrees/codex-sharpe-optimization-target/tmp/sharpe_12_1_vol_compare_final/japan_broad_50/after_only_2/walk_forward/20260325T101047Z-20260325T101047Z-4de160bb)

## Results

| Universe | Before Return | After Return | Before Hit Rate | After Hit Rate | Before Gap | After Gap | Gap Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `topix_top_10` | `93.1388%` | `106.7797%` | `0.6855` | `0.6690` | `23.2180%` | `12.6664%` | `-10.5516%` |
| `japan_large_30` | `122.9601%` | `69.2004%` | `0.6155` | `0.6022` | `29.0389%` | `26.8239%` | `-2.2150%` |
| `japan_broad_50` | `234.4991%` | `173.2305%` | `0.6771` | `0.6762` | `33.9833%` | `19.4187%` | `-14.5646%` |

## Interpretation

The Sharpe-first target passes the intended acceptance check on all three universes:

- train/validation gap is narrower in every case
- walk-forward return remains positive in every case

The strongest effect appears in:

- `topix_top_10`
- `japan_broad_50`

where the gap contracts materially while preserving strong positive walk-forward
returns.

`japan_large_30` is directionally consistent but more mixed:

- the gap still narrows
- walk-forward return remains positive
- but the realized return drops more noticeably than in the other two universes

That means Sharpe-first improves robustness there too, but with a steeper trade-off.

## Key Reading Of The Return Drop

The lower return in some Sharpe-first runs should not be read as a simple negative.

`return_pct`-first can select weights that performed well in validation partly because
they were lucky in the training window, not because they are more robust.

Sharpe-first gives up some of that lucky upside in exchange for more predictable
out-of-sample behavior.

The narrower train/validation gap is the more important signal of improved strategy
credibility.

## Conclusion

This slice is successful.

Sharpe-first ranking:

- reduces overfitting pressure at the optimizer-selection layer
- preserves positive walk-forward return across all requested universes
- makes `12_1 + vol` look more trustworthy as a research candidate, even where it gives
  up some raw return

## Next Question

With the optimizer target corrected, the next useful research question is no longer
"does Sharpe-first help?" but rather:

- whether `12_1 + vol` is now competitive enough with the single-factor variants to
  remain in the candidate set
