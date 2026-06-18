# Review Follow-up Remediation Design

## Status

Approved by direct user request: evaluate the second pasted review and fix all true, unrepaired issues from both reviews.

## Goal

Repair the true and locally fixable issues that remain after the first professional-review remediation, and document the true issues that require broader research policy, more data, or a larger strategy redesign.

## Current Verified Findings

### Fix Locally

- Walk-forward summaries compound validation-window returns incorrectly by adding percentages.
- Backtrader execution can look ahead because rebalance scoring sees the current close while cheat-on-close fills at the current close.
- Five-factor walk-forward paths drop `qual` weights when converting best weights to validation tuples and artifact rows.
- Vectorbt uses generic `BMS` dates instead of the actual first trading day from the available market data.
- The default research configuration is still too concentrated at `top_n=3`.
- The default optimizer grid allows simultaneous positive 90d/12_1 momentum and 20d mean-reversion weights, mixing contradictory horizons.

### Document or Guard

- Walk-forward optimization on very small samples is still data mining risk; the code can warn and avoid contradictory grids, but cannot create statistical power from insufficient data.
- The named universes are too small for institutional cross-sectional factor claims; true TOPIX500 point-in-time data is outside the local repo.
- P/B remains a weak standalone value proxy, even with point-in-time alignment.
- Long-only performance remains beta-heavy without a hedge/risk model.
- Gold buy-and-hold observations are exploratory and must not be presented as an alpha strategy.

## Design

### Compound Walk-forward Returns

Add a helper that compounds a sequence of return percentages:

`prod(1 + r / 100) - 1`

Use it for walk-forward, baseline, one-shot, and benchmark summary returns. Active/excess returns should be differences between compounded totals.

### Remove Backtrader Look-ahead

Keep cheat-on-close execution for the Backtrader reference path, but make `_collect_visible_history()` exclude the current bar. This makes scoring use information available before the execution close, aligning with the `simple` engine's `df.index < exec_date` behavior.

### Preserve Five-factor Weights

Represent weight tuples consistently:

- `mom`, `vol`, `rev`
- optional `val`
- optional `qual`

Grid and Optuna selection must preserve `qual`; validation and one-shot tuples must include it when present; weights artifacts must write `weight_qual`.

### Use Actual Trading Calendar in Vectorbt

Generate vectorbt execution dates from the first observed trading day of each month in `data_dfs`, as `simple_runner` does. Do not emit orders on generic business-month-start dates that are absent from the price index.

### More Conservative Defaults

Introduce a default research breadth of `top_n=10` for strategy, optimizer CLI, and paper signal generation. Existing callers can still override `top_n` explicitly.

### Avoid Contradictory Default Grids

Default optimizer grids should reject tuples where both momentum and short-term mean reversion are positive. Explicit custom grids remain supported for research experiments, but default artifacts should not search contradictory combinations.

## README Updates

README should state:

- Post-repair walk-forward totals are compounded, while legacy artifacts may be additive.
- Default research breadth is 10 names, not 3.
- Small-sample walk-forward optimization, small static universes, P/B weakness, long-only beta exposure, and gold buy-and-hold observations are not fixed alpha evidence.

## Testing Requirements

- Test compound walk-forward totals and active returns.
- Test Backtrader visible history excludes the current execution bar under cheat-on-close.
- Test five-factor grid/Optuna-to-validation weight propagation and `weight_qual` artifact rows.
- Test vectorbt uses actual first trading days and does not drop orders generated on exchange holidays.
- Test default optimizer grid rejects simultaneous positive momentum and mean-reversion weights.
- Test default `top_n` behavior is 10 for CLI/paper/strategy dispatch while explicit overrides still work.
