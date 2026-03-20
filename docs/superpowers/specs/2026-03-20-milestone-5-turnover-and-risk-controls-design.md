# Milestone 5 Turnover And Risk Controls Design

## Goal

Reduce unnecessary portfolio churn by adding configurable buy/sell rank thresholds and basic turnover reporting, while preserving the current top-`N` multi-factor strategy as the default path when no controls are enabled.

This milestone is aimed first at making the system's rebalancing behavior more realistic and easier to compare before and after turnover controls. It is not a full portfolio risk-engine milestone.

## Context

The current main stock-selection strategy in [`src/strategies/multi_factor.py`](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py) uses a simple monthly rebalance:

- rank the entire visible universe with the shared scorer
- liquidate any current holding not in the top `N`
- equal-weight the new top `N`

That behavior is intentionally simple, but it creates a churn problem:

- a stock can be sold immediately after a small ranking slip
- a new stock can be bought immediately after a small ranking improvement
- there is no turnover metric to show whether the strategy is overtrading

Milestone 5 in the README asks for:

- rank buffer or buy/sell threshold rules
- optional minimum holding period
- optional volatility or concentration caps
- better transaction-awareness around rebalance decisions

For the first iteration, the user explicitly chose the rank-buffer path and asked to prioritize the double-threshold design:

- `buy threshold + sell threshold`

## Requirements

From the README acceptance criteria, the implementation must achieve:

- current holdings can optionally be retained unless they fall below a configurable sell threshold
- backtest output includes at least one turnover-related metric
- portfolio behavior can be compared before and after turnover controls
- risk-control settings are configurable and do not break the base strategy path

The user also prefers a design that is understandable without domain expertise, which pushes the first iteration toward rules that are simple to explain and easy to test.

## Options Considered

### Option A: Sell-threshold only

Keep current buy behavior, but allow existing holdings to remain until they fall below a looser sell rank.

Pros:

- minimal implementation surface
- directly addresses premature selling
- easy to explain

Cons:

- only half of a proper rank buffer
- still allows aggressive new entries on small ranking changes

### Option B: Buy-threshold + sell-threshold rank buffer

Require new positions to meet a stricter buy rank, while allowing existing holdings to remain until they fall below a looser sell rank.

Pros:

- directly reduces both unnecessary exits and unnecessary entries
- closely matches the README acceptance criteria
- preserves the current scorer and portfolio construction model
- easy to compare against the base path

Cons:

- requires a little more rebalance logic than Option A
- needs careful handling to avoid overfilling the portfolio

### Option C: Turnover metrics only

Leave strategy behavior unchanged for now and only add turnover measurement.

Pros:

- very low implementation risk
- useful diagnostic foundation

Cons:

- does not actually reduce churn
- misses the central Milestone 5 behavioral goal

### Recommendation

Choose Option B.

This option gives the project a real turnover-control mechanism without turning Milestone 5 into a large risk-management rewrite. It also keeps the control logic understandable:

- new ideas must be strong enough to enter
- existing holdings get some buffer before forced exit

## Proposed Design

### 1. Add rank-buffer parameters to the multi-factor strategy

Extend [`src/strategies/multi_factor.py`](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py) with configurable threshold parameters:

- `buy_rank_threshold`
- `sell_rank_threshold`

Interpretation:

- a stock is eligible for new entry only if its rank is at or above `buy_rank_threshold`
- an existing holding may stay in the portfolio as long as its rank remains at or above `sell_rank_threshold`

Recommended invariants:

- if a threshold is not provided, derive it from the existing `top_n` behavior
- default behavior must remain equivalent to the current implementation
- `buy_rank_threshold` should not exceed `sell_rank_threshold`
- the portfolio should still cap itself to a maximum practical holding count, anchored by `top_n`

### 2. Rebalance logic becomes holding-aware

The current rebalance process only distinguishes between "in top N" and "not in top N." The new process should distinguish among:

- current holdings inside the keep zone
- current holdings outside the keep zone
- non-held symbols inside the buy zone
- non-held symbols outside the buy zone

Recommended rebalance flow:

1. rank the visible universe using the existing shared scorer
2. identify currently held symbols
3. keep held symbols whose rank is within the sell threshold
4. mark held symbols below the sell threshold for exit
5. consider non-held symbols for entry only if their rank is within the buy threshold
6. fill remaining portfolio slots with the highest-ranked entry candidates
7. size final target holdings equally as before

This keeps the control logic entirely in the rebalance layer rather than the scorer, which is important because turnover control is a portfolio rule, not a scoring rule.

### 3. Preserve the base strategy path when controls are disabled

Default configuration should behave exactly like the current strategy:

- buy threshold effectively equals `top_n`
- sell threshold effectively equals `top_n`

That means a user who does not opt into turnover controls sees no behavior change.

This is important for:

- backwards compatibility
- regression safety
- clean before/after comparisons

### 4. Add turnover metrics at the strategy/backtest layer

Milestone 5 needs at least one turnover-related metric in backtest output. For the first implementation, use simple, stable metrics that are easy to test and explain:

- `rebalance_count`
- `position_change_count`
- `turnover_ratio`

Suggested definitions:

- `rebalance_count`: number of rebalances that produced a portfolio decision pass
- `position_change_count`: count of buy/sell position changes triggered by rebalances
- `turnover_ratio`: `position_change_count / rebalance_count` or another similarly simple, deterministic summary

The exact formula matters less than having:

- a clear documented definition
- deterministic tests
- output that supports before/after comparison

### 5. Surface turnover metrics in backtest reporting

Backtest output in [`src/main.py`](/Users/y-yang/Developer/quant/src/main.py) should include the turnover summary when running the multi-factor strategy.

That output should make it easy to compare:

- base top-`N` behavior
- rank-buffer behavior

This does not require a fully automated A/B comparison command in the first pass. It is enough to expose the metric so two runs can be compared with different CLI settings.

## Scope Limits

The first Milestone 5 implementation should not yet include:

- minimum holding period rules
- volatility caps
- concentration caps
- a full optimizer over turnover-control settings

Those remain valid future extensions, but including them now would make the milestone substantially larger and harder to verify.

## Testing Strategy

The implementation should follow TDD and validate three layers.

### Strategy behavior tests

Add tests that verify:

- default settings preserve current top-`N` rebalance behavior
- existing holdings remain when rank is still inside the sell threshold
- existing holdings are removed when rank drops below the sell threshold
- non-held symbols are not newly purchased unless they are inside the buy threshold
- portfolio size remains bounded even when keep candidates and entry candidates overlap

### Turnover metric tests

Add tests that verify:

- turnover counters increment deterministically for a known rebalance sequence
- a buffered configuration produces lower turnover than the default configuration on a churn-heavy fixture

### Backtest/reporting tests

Add tests that verify:

- turnover metrics are present in reported results
- multi-factor runs can accept turnover-control settings without breaking existing weight resolution behavior

## Risks and Mitigations

### Risk: rank-buffer logic silently changes the base strategy

Mitigation:

- default thresholds must reproduce current behavior exactly
- preserve existing parity and rebalance tests

### Risk: portfolio capacity rules become ambiguous

Mitigation:

- explicitly define final target holdings as a bounded set derived from current holdings plus qualified entries
- keep `top_n` as the anchor for maximum intended portfolio size

### Risk: turnover metrics become too finance-specific or fragile

Mitigation:

- start with simple deterministic counters
- document the metric definition in code and tests

### Risk: controls drift away from the shared scorer

Mitigation:

- keep the scorer unchanged
- apply turnover controls only after ranking is produced

## Phase Breakdown

### Phase 1: Buffered rebalance rules

Scope:

- add buy/sell threshold configuration
- update the strategy rebalance logic
- preserve default behavior

Outcome:

- the strategy can reduce churn by keeping current holdings inside a sell buffer and only admitting new holdings inside a buy threshold

### Phase 2: Turnover metrics

Scope:

- collect turnover counters during strategy execution
- expose them through backtest metrics
- test default vs buffered behavior

Outcome:

- the system can quantify whether turnover controls are actually reducing churn

### Phase 3: CLI/reporting integration

Scope:

- surface configuration and turnover metrics in the backtest entry point
- make before/after comparisons practical from the command line

Outcome:

- operators can run buffered and unbuffered backtests and compare churn behavior directly

## Implementation Handoff

The next step is to write a staged implementation plan that:

- uses TDD throughout
- commits each phase separately
- keeps the first Milestone 5 pass focused on double-threshold rank buffering and turnover metrics only
