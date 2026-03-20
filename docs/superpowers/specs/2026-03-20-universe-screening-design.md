# Universe Screening Design

**Date:** 2026-03-20

## Goal

Add a reproducible universe-screening layer that can narrow a broader candidate universe into a smaller research universe before ranking, walk-forward optimization, and paper-signal generation run.

The system should answer two different questions cleanly:

1. Is this symbol eligible to enter the research universe at all?
2. Among eligible symbols, how should the strategy rank and select names?

The new screening layer owns question 1. The existing multi-factor scorer continues to own question 2.

## Motivation

The current project already supports:

- static named universes
- cached price loading
- lightweight price-frame validation
- cross-sectional ranking
- walk-forward optimization
- universe participation diagnostics

What is still missing is a first-class step that converts a broader candidate pool into a trustworthy research universe. Right now, symbols can silently disappear because of empty slices, missing data, or weak historical coverage. That makes it harder to separate:

- symbols we intentionally rejected because they were not research-ready
- symbols we requested but could not use because data did not support the run

This design adds that missing layer.

## Design Principles

- Keep eligibility separate from alpha ranking.
- Start with price- and liquidity-based hard rules that are easy to explain and test.
- Produce explicit rejection reasons for every screened-out symbol.
- Preserve the current ranking logic as-is for eligible symbols.
- Reuse the new participation diagnostics so larger-universe research can distinguish screening loss from data loss.
- Do not make phase 1 depend on fragile point-in-time fundamental data.
- Leave a clean extension point for future `PB` / `PE` / value-factor integration.

## Scope

### Phase 1: Included

Phase 1 adds a price-based eligibility pipeline using already-available market data.

The first version evaluates symbols against configurable hard rules such as:

- minimum history length
- maximum missing-ratio threshold inside the requested range
- minimum latest close price
- minimum recent trading activity
- maximum recent inactive-day ratio

It also persists structured screening output so downstream research can inspect:

- which symbols were eligible
- which symbols were rejected
- why they were rejected
- what summary counts the screen produced

### Phase 1: Not Included

Phase 1 does not:

- change the factor math in the scorer
- add valuation fields directly into ranking
- require point-in-time fundamental datasets
- create a separate portfolio-construction layer
- fully redesign named-universe management

### Phase 2: Explicit Follow-On

Phase 2 may add a fundamentals-backed eligibility provider that can supply fields like:

- `price_to_book`
- `price_to_earnings`
- `market_cap`
- `book_value_per_share`

Those fields can then support either:

- additional eligibility rules
- future value-oriented ranking factors

Phase 2 should remain a separate slice because it introduces new data-source and time-alignment risk.

## Proposed Architecture

The new pipeline becomes:

1. candidate universe selection
2. market-data loading
3. eligibility screening
4. eligible-universe handoff
5. ranking / walk-forward / paper-signal generation

In practical terms:

- `src/data/universe.py` continues to define candidate universes.
- `src/data/bulk_loader.py` continues to load and cache raw market data.
- a new `screening` module evaluates symbol eligibility using requested date ranges plus loaded price history.
- optimization and backtest entry points can optionally call the screen before ranking.

This keeps each layer focused:

- loaders fetch data
- validators check data quality
- screeners decide eligibility
- scorers rank eligible symbols

## Screening Model

### Inputs

The screening layer should take:

- `candidate_symbols`
- `data_dfs`
- `start`
- `end`
- `screening_rules`

Optional future inputs:

- `fundamentals_by_symbol`
- `liquidity_overrides`
- `screen_as_of`

### Outputs

The screening layer should return a structured result with:

- `eligible_symbols`
- `rejected_symbols`
- `by_symbol`
- `summary`

`by_symbol` should expose one record per requested symbol, for example:

```json
{
  "symbol": "7203.T",
  "eligible": true,
  "reasons": [],
  "metrics": {
    "history_days": 756,
    "missing_ratio": 0.01,
    "latest_close": 2875.0,
    "recent_trading_day_ratio": 0.98
  }
}
```

A rejected record should look like:

```json
{
  "symbol": "1234.T",
  "eligible": false,
  "reasons": ["insufficient_history", "low_recent_activity"],
  "metrics": {
    "history_days": 47,
    "missing_ratio": 0.34,
    "latest_close": 81.2,
    "recent_trading_day_ratio": 0.21
  }
}
```

The summary should include counts such as:

- `requested_symbol_count`
- `eligible_symbol_count`
- `screened_out_symbol_count`
- `eligibility_ratio`
- reason-level counts such as `screened_out_insufficient_history_count`

## Rule Set for Phase 1

The default rules should remain conservative and easy to interpret.

### 1. Minimum History

Reject symbols that do not have enough observations to support both screening and ranking lookbacks with margin.

This protects the scorer from quietly dropping names later because they lack enough history.

### 2. Missing-Data Threshold

Reject symbols whose requested-range slice is too sparse.

This makes the research universe more stable and reduces cases where a symbol technically loaded but is not usable for consistent evaluation.

### 3. Minimum Latest Close

Reject symbols trading below a configured minimum close threshold.

This acts as a simple tradability and data-quality proxy, especially useful when broadening the candidate universe.

### 4. Recent Activity Threshold

Reject symbols with too few non-empty recent trading days inside a configurable recent window.

This helps screen out stale or effectively inactive names.

### 5. Recent Inactive-Day Threshold

Reject symbols that show too high a ratio of inactive recent dates.

This complements the activity threshold and makes the rule easier to explain in diagnostics.

## Integration with Existing Research Diagnostics

The existing universe participation diagnostics already report:

- requested symbols
- loaded symbols
- skipped symbols
- coverage ratio

After screening, diagnostics should evolve to distinguish two classes of loss:

- `screened_out_symbol_count`
- `loaded_but_unusable_symbol_count`

This distinction matters:

- screening loss is intentional governance
- unusable-data loss is an execution/data-quality problem

Phase 1 does not need to rewrite every summary immediately, but the screening result should expose enough structured counts for that integration.

## Where Screening Should Run

### Recommended Phase 1 Integration Points

- research and optimization entry points
- backtest entry points that operate on named universes

This gives the screening system immediate value for:

- walk-forward research
- larger-universe experimentation
- future reproducible universe artifacts

### Deliberately Deferred Integration

- live paper-trading signal generation

Paper trading already depends on approved parameters and current signal generation. Screening should only reach that path once the research-side workflow is stable and artifact conventions are clear.

## Artifact Strategy

Screening should produce a lightweight artifact similar to other research outputs.

Suggested artifact contents:

- metadata:
  - start/end
  - universe name
  - screening rule thresholds
- per-symbol decisions
- summary counts

This artifact enables:

- reproducible research-universe formation
- debugging of why a symbol disappeared
- comparison of eligible universes over time

## Future Fundamentals Hook

The screening system should reserve an optional fundamentals provider interface so later work can add `PB` / `PE` without restructuring the whole pipeline.

Phase 2 should introduce a provider that returns normalized symbol-level fields, for example:

```python
{
    "7203.T": {
        "price_to_book": 1.2,
        "price_to_earnings": 10.8,
        "market_cap": 4_000_000_000_000,
    }
}
```

Important constraint:

Future fundamentals-based screening must be explicit about as-of timing. We should not mix current Yahoo metadata into historical walk-forward windows and pretend it is point-in-time correct. That is the main reason this work stays out of phase 1.

## Testing Strategy

Phase 1 should add focused tests for:

- eligibility evaluation with passing and failing symbols
- multi-reason rejection behavior
- omission vs inclusion of screening summaries
- preservation of existing scorer behavior for eligible-only inputs
- integration path from screening result to research entry point

Artifact tests should verify that:

- screening summaries are persisted unchanged
- rejection reasons remain machine-readable

## Risks and Trade-Offs

### Risk: Over-filtering

If the rules are too strict, the eligible universe may become too small and harm research breadth.

Mitigation:

- keep default thresholds conservative
- persist explicit summary counts
- make thresholds configurable

### Risk: Hiding Data Problems Behind Screening

If screening runs too early or too opaquely, real loader/data issues could look like intentional governance.

Mitigation:

- keep rejection reasons explicit
- keep screened-out counts separate from downstream unusable-data counts

### Risk: Premature Fundamentals Integration

Adding `PB` / `PE` too early could introduce time-alignment errors and unclear trust boundaries.

Mitigation:

- phase fundamentals separately
- design an interface now, but do not depend on it in phase 1

## Recommended Implementation Sequence

1. Add a dedicated screening module with result and rule structures.
2. Implement phase-1 hard rules against loaded price data.
3. Add screening artifact persistence and regression coverage.
4. Integrate screening into research-facing entry points.
5. Extend diagnostics so larger-universe runs can separate screened-out symbols from downstream data loss.
6. Revisit fundamentals-backed rules only after the phase-1 workflow is stable.

## Decision

Implement a two-stage universe-construction workflow:

- phase 1: price-based hard-rule eligibility screening
- phase 2: optional fundamentals-backed eligibility hooks for `PB` / `PE`

This gives the project a reliable and explainable way to build a research universe from a broader candidate pool without prematurely coupling the core research path to fragile valuation data.
