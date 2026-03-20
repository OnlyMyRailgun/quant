# Milestone 7 Universe Behavior Diagnostics Design

## Goal

Add a lightweight larger-universe run-quality layer so research output can show how much of the requested universe actually participated in each walk-forward window.

This slice is aimed at answering a practical Milestone 7 question:

- when we ask the system to research a larger configured universe, how many symbols were actually usable?

It is not a new factor, attribution, or reporting subsystem. It is a confidence layer on top of the existing walk-forward research flow.

The broader product goal remains the same:

- build a screening system that can rank and select candidates across a wider configured universe with visible, trustworthy participation diagnostics

## Why This Slice Next

The project now has:

- explicit named universes, including larger curated registries
- walk-forward optimization with benchmark comparison
- portfolio diagnostics such as hit rate and contributor summaries
- basic data validation that can skip invalid symbols

The next weak point for Milestone 7 is visibility into what happened when a larger universe was requested.

Right now a larger-universe experiment can silently degrade into a smaller effective universe because:

- some symbols fail validation
- some symbols have no usable window slice
- benchmark and return summaries do not reveal participation quality

That makes larger-universe research harder to trust, even if the run technically succeeds.

## Scope

### In scope

- compact run-quality diagnostics for walk-forward research
- per-window counts for requested, loaded, and skipped symbols
- per-window coverage ratio
- summary-level aggregates across all evaluation windows
- compact optimizer CLI output for these diagnostics
- persisted diagnostics in the existing walk-forward artifact summary

### Out of scope

- symbol-by-symbol detailed skip reports in the CLI
- new factor formulas
- new portfolio construction logic
- lifecycle-state automation
- a separate reporting command or visualization layer

## Options Considered

### Option A: Summary-only run-quality diagnostics

Add compact counts and ratios to each walk-forward window and to the final summary:

- `requested_symbol_count`
- `loaded_symbol_count`
- `skipped_symbol_count`
- `coverage_ratio`

Pros:

- minimal implementation surface
- directly answers the trust question for larger universes
- fits naturally into existing walk-forward artifacts and optimizer output
- low risk of overwhelming the CLI

Cons:

- does not preserve detailed symbol-level skip reasons

### Option B: Summary diagnostics plus symbol-level skip records

Add the compact counts above and also persist detailed per-symbol validation failures.

Pros:

- stronger debugging value
- easier to investigate bad caches or broken tickers

Cons:

- larger artifact payloads
- more output-shape complexity
- pushes this slice toward a reporting subsystem

### Option C: Separate larger-universe diagnostics report

Leave walk-forward summary mostly unchanged and add a second artifact/report dedicated to universe quality.

Pros:

- isolates diagnostics cleanly
- could scale to richer future analysis

Cons:

- too heavy for the current milestone
- duplicates existing summary/reporting paths

## Recommendation

Choose Option A.

This is the smallest slice that materially improves trust in larger-universe research. It tells us whether a `japan_large_30` or `japan_broad_50` run actually evaluated 30 or 50 names, or whether it effectively shrank because of missing or invalid data.

It also composes well with the current architecture:

- existing data validation already decides what gets skipped
- existing walk-forward summaries already persist compact diagnostics
- existing optimizer output already prints one-screen summaries

## Definitions

To keep the metrics interpretable, this slice uses validation-window participation only.

For each walk-forward validation window:

- `requested_symbol_count`
  - the number of symbols in the originally requested universe for the experiment
- `loaded_symbol_count`
  - the number of requested symbols whose already-loaded frame produces a non-empty validation-window slice
- `skipped_symbol_count`
  - `requested_symbol_count - loaded_symbol_count`
- `coverage_ratio`
  - `round(loaded_symbol_count / requested_symbol_count, 4)` when `requested_symbol_count > 0`, otherwise `0.0`

Important semantic boundary:

- symbols rejected by `fetch_universe()` before optimization begins count as skipped in every window
- symbols that were initially loaded but have no rows in a specific validation window also count as skipped for that window
- this slice does **not** measure training-window coverage
- this slice does **not** persist symbol-level skip reasons beyond the existing loader console output

This treatment is deliberate. It favors a stable experiment-level denominator over trying to reconstruct symbol eligibility separately for each downstream path.

## Proposed Design

### 1. Run-quality diagnostics belong to the research orchestration layer

The new fields should be computed in the walk-forward orchestration path rather than inside the scorer.

Reason:

- symbol participation is a property of the research window inputs, not a property of factor scoring
- the scorer should remain focused on ranking the symbols it receives

Recommended placement:

- `src/optimize.py` gathers the per-window symbol-participation inputs using the originally requested universe list plus the current validation-window slices
- `src/research/walk_forward.py` stores those inputs into window rows and aggregates them into summary diagnostics

### 2. Diagnostics schema

Each evaluated validation window should expose:

- `requested_symbol_count`
- `loaded_symbol_count`
- `skipped_symbol_count`
- `coverage_ratio`

The final summary should expose:

- `avg_loaded_symbol_count`
- `avg_skipped_symbol_count`
- `avg_coverage_ratio`
- `min_loaded_symbol_count`
- `min_coverage_ratio`

This keeps the first slice compact while still surfacing both the typical and worst-case participation level.

### 3. Data flow

The existing optimization path already slices a per-symbol data map for each window.

The new behavior should be:

1. start from the full requested universe symbol list
2. slice the requested date window from the cached loaded data map
3. count how many symbols remain available for the evaluation window
4. pass the participation counts into walk-forward result rows
5. aggregate those counts into the final summary

This means the diagnostics reflect actual evaluation participation, not only initial registry size.

If the original requested universe list is unavailable, the system should not silently infer `requested_symbol_count` from `data_dfs.keys()`. Instead, the diagnostics should either:

- use the explicit `universe_symbols` input when provided, or
- stay disabled for participation-quality fields in that call path

This avoids collapsing the denominator to only already-loaded symbols.

## Implementation Contract

To keep the slice additive and narrow:

- validation evaluators in `src/optimize.py` may return four additional plain-Python fields:
- validation evaluators in `src/optimize.py` may return four additional plain-Python fields:
  - `requested_symbol_count`
  - `loaded_symbol_count`
  - `skipped_symbol_count`
  - `coverage_ratio`
- these participation counts are computed once per validation window and attached to validation metrics, not recomputed during each training-grid evaluation
- `src/research/walk_forward.py` should persist those fields into window rows when present
- `src/research/walk_forward.py` should aggregate summary-level participation fields only from those explicit values
- existing return, benchmark, and portfolio-diagnostics behavior should remain unchanged
- existing callers that do not provide the required participation inputs should continue to work without these new metrics
- when participation diagnostics are disabled, the implementation should omit participation columns from window rows, omit participation keys from summary payloads, and skip the CLI participation section entirely
- this milestone does not require changing the `fetch_universe()` return shape; the denominator comes from explicit `universe_symbols`

### 4. CLI reporting

`src.optimize` should print a small larger-universe quality section after the existing return and benchmark block.

Recommended output shape:

- average loaded symbols
- average skipped symbols
- average coverage ratio
- minimum coverage ratio

Formatting should stay single-screen friendly and avoid raw JSON.
This slice should add only a few summary lines and should not redesign the existing weights table or broader optimizer print layout.

### 5. Artifact persistence

The current walk-forward artifact summary should persist these new fields without creating a second artifact type.

That keeps downstream consumption simple:

- one walk-forward summary for returns, benchmark comparison, portfolio diagnostics, and universe participation quality

## Testing Strategy

Add or extend tests so they cover:

- deterministic aggregation of coverage metrics in `src/research/walk_forward.py`
- walk-forward result rows including the per-window participation fields
- optimizer CLI output including the compact universe-quality section
- artifact persistence of the new summary fields

The tests should prefer stable counts and ratios over fragile formatting assertions.

## Success Criteria

This slice is done when:

- a larger-universe walk-forward run records how many symbols actually participated in each window
- the final summary shows typical and worst-case participation quality
- optimizer output makes coverage loss visible without opening artifacts
- the implementation reuses the existing walk-forward and artifact paths rather than creating a parallel reporting system
