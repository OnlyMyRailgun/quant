# Platform Foundation Next Slice Design

## Goal

Build the next confidence-oriented slice after the shared scoring and artifact foundation by making universe selection explicit and reproducible, and by adding a lightweight data-validation layer for cached historical price data.

This slice is not a replacement for the earlier `Unified Scoring Core and Experiment Artifacts` subproject. That earlier subproject is already implemented in the repository. This design covers the next unfinished platform gaps identified in the roadmap review.

## Why This Slice Next

The current codebase already has:

- shared scoring across research and paper trading
- experiment artifacts and registry records
- walk-forward artifacts and approval flow
- benchmark comparison output in optimization summaries

The next weak points are upstream of scoring:

1. universe definition is still mostly implicit and hardcoded
2. cached market data can still contain silent quality problems before scoring sees it
3. README milestone state lags behind the actual codebase, which makes roadmap decisions noisy

This slice improves confidence without changing factor math or portfolio behavior.

## Scope

### In scope

- named universe definitions with stable symbol ordering
- explicit universe selection in research and backtest entrypoints
- persisted universe metadata in experiment artifacts
- deterministic validation for historical price frames
- loader behavior that skips invalid symbols with structured reasons
- README updates that are backed by implemented code and tests

### Out of scope

- point-in-time universe membership
- new factor formulas
- new portfolio construction rules
- richer explainability UI
- lifecycle-state automation beyond what already exists

## Design Decisions

### 1. Universe governance should start with named static definitions

The first step is not point-in-time membership. It is a small registry of named universes with explicit symbol lists and stable ordering.

That should live in `src/data/universe.py`.

Recommended API:

- `list_universe_names() -> list[str]`
- `get_universe(name: str) -> list[str]`
- compatibility helper `get_topix_top_10()`

Why:

- keeps current behavior stable
- gives research runs a reproducible universe identifier
- creates a clean seam for later expansion

### 2. Universe selection should be persisted into artifacts

Experiment artifacts should record:

- `universe_name`
- `universe_symbols`

This lets later users answer "what did this run actually trade over?" without reconstructing CLI inputs from memory.

### 3. Data validation should fail closed at the symbol level

This slice should not abort an entire multi-symbol load because one symbol has bad cached data. Instead:

- validate each symbol after slicing to the requested date range
- skip invalid symbols
- expose a compact validation summary that callers can persist or print

Why:

- avoids silent pollution of research conclusions
- preserves robustness for mixed-quality data sets
- keeps behavior deterministic and easy to test

### 4. Validation contract

For this slice, a frame is invalid if any of the following are true:

- missing `Close`
- empty after slicing
- duplicate timestamps
- unsorted timestamps
- non-finite close values
- non-positive close values

The validation helper should return a structured result with:

- `is_valid`
- `issues`
- `row_count`
- `start`
- `end`

### 5. README updates must cite implemented evidence

README changes should not be editorial guesswork. Each milestone status change should be backed by:

- code paths
- tests
- persisted artifact behavior

That keeps roadmap state reviewable.

## Execution Breakdown

### Task A: Universe registry foundation

Scope:

- add named universe APIs
- preserve current default Topix-10 behavior
- add unit tests for deterministic resolution

### Task B: Data validation foundation

Scope:

- add validation helper module
- integrate validation into bulk loading
- add unit and loader tests

### Task C: CLI and artifact integration

Scope:

- thread selected universe name through optimizer and backtest CLI
- persist universe metadata into artifacts
- add integration tests

### Task D: README sync

Scope:

- update milestone 3 / 7 / X wording to match the codebase
- document the new universe and validation capabilities

## Parallelism Rules

Only Task A and Task B are safe to run in parallel.

Task C depends on Task A because it needs the named universe API.
Task D should happen after Tasks A-C are green.

## Testing Strategy

- universe API tests for name resolution and error handling
- validation unit tests for issue detection and summaries
- loader tests for symbol-skipping behavior
- CLI/artifact tests for explicit universe persistence
- final full-suite regression run
