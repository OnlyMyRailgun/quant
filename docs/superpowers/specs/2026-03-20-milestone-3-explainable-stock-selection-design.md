# Milestone 3 Explainable Stock Selection Design

## Goal

Deliver explainability for each rebalance so the system can answer why a stock was selected, why another stock missed selection, and whether research and paper-trading are using the same scoring evidence.

This milestone is aimed at stronger system validation and easier debugging, not at producing a more polished discretionary-investing reading experience.

## Context

The repository already has a shared scoring path in [`src/scoring/multi_factor.py`](/Users/y-yang/Developer/quant/src/scoring/multi_factor.py). That scorer is used directly by the paper-trading signal path in [`src/paper/bot.py`](/Users/y-yang/Developer/quant/src/paper/bot.py), and the Backtrader strategy adapter also routes ranking through the same shared scorer in [`src/strategies/multi_factor.py`](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py).

That existing architecture creates a clear design constraint for Milestone 3: explainability should be generated inside the shared scorer rather than reconstructed later in reporting code. If we generate explanations outside the scorer, ranking logic and explanation logic can drift apart.

## Requirements

From the README acceptance criteria, the system must:

- persist per-stock factor details for each rebalance
- show selected stocks and near-miss candidates
- allow inspection of why one stock ranked above another on a given rebalance date
- ensure explainability output comes from the same scoring logic as selection

The user's explicit preference refines that goal further:

- prioritize stronger judgment/debug evidence for the system
- do not optimize first for a more professional-looking human-facing report

## Recommended Approach

### Option A: Extend the shared scorer and build everything on top of it

This approach adds factor-level contribution columns directly to the shared ranked universe output. Artifact writing and reporting then consume those columns without re-deriving them.

Pros:

- strongest guarantee that explanation data matches selection logic
- lowest long-term drift risk
- easiest to reuse across research, strategy, and paper-trading paths
- best fit for debugging and parity checks

Cons:

- first phase is mostly foundation work rather than user-visible output polish

### Option B: Keep scorer unchanged and add artifact-side explainability assembly

This approach leaves the scorer returning the current columns and derives contribution summaries later when saving artifacts.

Pros:

- can produce artifacts quickly

Cons:

- explanation logic becomes a second implementation of the ranking math
- higher risk of research/paper divergence
- weaker basis for debugging subtle ranking issues

### Option C: Start with richer paper-trading CLI output

This approach focuses first on terminal output and presentation in `paper generate`.

Pros:

- immediate visibility

Cons:

- weakest support for reproducible debugging
- does not naturally create durable evidence for past rebalances
- likely to over-invest in presentation before the underlying evidence model is stable

### Recommendation

Choose Option A.

Milestone 3 should treat explainability as part of the scoring contract, not as a reporting afterthought. The shared scorer should emit the exact evidence needed to justify rankings, and all downstream artifact/reporting code should simply serialize or display that evidence.

## Proposed Design

### 1. Shared scorer becomes the source of explainability truth

The shared scorer should continue to return one row per symbol, but with explicit factor-contribution columns in addition to the existing raw factor and z-score columns.

Recommended output columns:

- `symbol`
- `price`
- `mom_raw`
- `vol_raw`
- `rev_raw`
- `mom_z`
- `vol_z`
- `rev_z`
- `mom_contribution`
- `vol_contribution`
- `rev_contribution`
- `total_score`
- `rank`
- `is_top_n`

The contribution columns should be defined directly from the scoring formula:

- `mom_contribution = weight_mom * mom_z`
- `vol_contribution = weight_vol * vol_z`
- `rev_contribution = weight_rev * rev_z`

This gives the system a direct answer to "which factor pushed this stock up or down?" without needing any later recomputation.

### 2. Rebalance artifacts persist complete ranking evidence

When a paper/research scoring run is saved, the full ranked universe CSV should already contain the explainability columns above. Artifact metadata and summary should then add a compact, human-scannable view of:

- selected symbols
- near-miss symbols
- each selected symbol's strongest positive or negative contribution if helpful

The full CSV remains the canonical evidence store. Metadata and summary should remain compact and avoid duplicating the entire table.

### 3. Near-miss reporting is a first-class concept

Near-miss candidates should be defined deterministically from the ranked universe:

- winners: rows where `is_top_n == True`
- near-misses: the next `N` rows immediately after the selected set

For the first implementation, use a default near-miss count of `3`. This is enough to support debugging without over-designing a generic reporting system up front.

### 4. Stock-vs-stock comparison should be derived from persisted evidence

To answer "why did A rank above B?", the system does not need a separate ranking engine. It only needs a simple comparison layer over the saved explainability table:

- compare each factor contribution side by side
- compare total scores
- show the score delta

This should be implemented as a lightweight reporting/helper layer, not as a second scorer.

## Phase Breakdown

### Phase 1: Scorer evidence foundation

Scope:

- extend the shared scorer with contribution columns
- keep ordering behavior unchanged
- add or expand scorer tests to lock contribution math and ranking stability

Outcome:

- the system has a complete explainability table generated from the exact selection logic

Commit boundary:

- scorer and scorer-focused tests only

### Phase 2: Artifact persistence and near-miss summaries

Scope:

- persist explainability-rich score tables in scoring artifacts
- add compact summary/metadata for winners and near-misses
- add regression tests for artifact shape and deterministic persistence behavior

Outcome:

- each saved scoring run contains durable evidence for debugging rebalance decisions

Commit boundary:

- artifact-writing code, paper signal artifact integration, and tests only

### Phase 3: Comparison/reporting entry point

Scope:

- add a lightweight way to inspect selected stocks and near-misses
- add a simple "why A over B" comparison from persisted evidence
- keep implementation thin by reading saved scoring output rather than recalculating

Outcome:

- operators can inspect and debug a rebalance decision without manually parsing raw CSV files

Commit boundary:

- reporting/read-path code and tests only

## Data and Interface Decisions

### Backward compatibility

Existing consumers already expect columns such as `total_score`, `rank`, `is_top_n`, and the raw factor aliases used by `calculate_current_signals()`. Milestone 3 should preserve those columns and only add new ones. This keeps current ranking and paper-trading flows compatible.

### Scope limits

This milestone should not:

- change the factor formulas
- change portfolio construction rules
- change walk-forward parameter approval behavior
- introduce a rich UI or dashboard

Those are separate concerns. Milestone 3 only strengthens evidence around the current decision engine.

## Testing Strategy

The implementation should follow TDD and verify three levels of behavior:

1. scorer-level unit tests
   - contribution columns equal weight times z-score
   - `total_score` equals the sum of contributions
   - ranking order remains stable

2. artifact regression tests
   - saved score files include explainability columns
   - summary/metadata include winners and near-misses in deterministic order

3. reporting/comparison tests
   - a saved run can explain why one stock outranks another
   - near-miss output reflects the same saved scoring table

## Risks and Mitigations

### Risk: explanation logic diverges from ranking logic

Mitigation:

- generate contribution columns in the shared scorer only
- downstream code may serialize or display, but not re-derive factor math

### Risk: artifacts become noisy or overly large

Mitigation:

- keep the full ranked CSV as the detailed record
- keep metadata/summary compact and selective

### Risk: new columns break existing consumers

Mitigation:

- add columns without removing or renaming current ones
- preserve existing top-N result behavior in paper trading and strategy parity tests

## Implementation Handoff

The next step is to write a staged implementation plan that executes the three phases above with TDD and a separate git commit at the end of each phase.
