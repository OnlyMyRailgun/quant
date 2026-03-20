# Research Platform Foundation Design

## Objective

Build the missing platform layer that makes strategy research more trustworthy before expanding execution complexity.

The project already has:

- a factor-based stock selection strategy
- parameter optimization
- a paper-trading workflow
- slippage feedback into backtests

The current gap is confidence. The system can produce recommendations, but it cannot yet clearly demonstrate:

- that research and paper-trading paths use the same decision logic
- that a result is reproducible from stored inputs and artifacts
- that performance is meaningfully better than a stated benchmark
- that conclusions are not being silently distorted by data issues

This design defines a new milestone group called `Research Platform Foundation` and narrows the first implementation scope to the smallest high-leverage slice.

## Why This Matters

Without a research foundation, the project risks becoming a recommendation generator rather than a trustworthy decision system.

The main failure modes today are:

1. Logic drift between Backtrader research code and paper-trading signal code.
2. Results that are printed once but not persisted or auditable later.
3. Evaluation based on absolute return without strong baseline comparison.
4. Silent data quality issues in cached market data.

These are more important to solve now than adding more strategy features.

## Trust Model

System trustworthiness should be evaluated across four dimensions.

### 1. Consistency

The same data, date, and parameters should produce the same ranking and decision output across research and paper-trading paths.

Evidence:

- research and paper-trading ranking parity
- parameter values used at runtime match stored artifacts
- fewer duplicated scoring implementations

### 2. Reproducibility

An important result should be rerunnable from stored inputs and recorded outputs.

Evidence:

- experiments are registered with their configuration
- artifacts are persisted and reloadable
- reruns on the same cached data produce the same outputs

### 3. Relative Edge

Strategy quality should be measured against an explicit benchmark, not just absolute return.

Evidence:

- active return versus equal-weight or other baseline
- drawdown comparisons relative to benchmark
- walk-forward results outperforming static defaults

### 4. Stability

A strategy should remain believable across time windows and reasonable parameter changes.

Evidence:

- walk-forward robustness
- stable rank behavior
- manageable turnover
- low sensitivity to small configuration changes

## Confidence Levels

The project should be thought of in stages rather than as simply "working" or "not working."

### Low Confidence

Recommendations can be generated, but the system cannot strongly justify them.

Typical traits:

- duplicated scoring logic
- weak experiment tracking
- limited benchmark comparison
- low auditability

### Medium Confidence

Research conclusions are inspectable and repeatable.

Typical traits:

- shared scoring core
- saved experiment records and artifacts
- benchmark comparison
- basic diagnostics and data validation

### High Confidence

The system has strong discipline across research and operational paths.

Typical traits:

- long-running out-of-sample evidence
- robust data validation
- strong parity between research and paper trading
- explicit portfolio construction and lifecycle controls

## Scope Decomposition

`Research Platform Foundation` is too broad to implement as one change. It should be split into smaller subprojects.

Recommended subprojects:

1. Shared scoring and experiment artifacts
2. Benchmark and diagnostics reporting
3. Data validation and cache integrity
4. Portfolio construction and lifecycle controls
5. Universe governance improvements

This spec focuses on subproject 1 because it unlocks all later work.

## Recommended First Subproject

### Name

`Unified Scoring Core and Experiment Artifacts`

### Goal

Create a shared scoring engine and artifact flow so research, optimization, and paper trading can use the same ranking logic and produce auditable outputs.

### Why First

This is the smallest change that most directly improves confidence.

It solves the highest-priority problem:

- the same strategy can currently exist in more than one code path

It also creates the storage pattern needed by later milestones:

- walk-forward outputs
- explainability outputs
- benchmark comparisons
- paper-trading parameter loading

## Architecture

### Current State

Today the project has at least two relevant scoring paths:

- `src/strategies/multi_factor.py`
  - computes factor values inside Backtrader for rebalancing
- `src/paper/bot.py`
  - computes similar factor values in pandas for live signal generation

This duplication creates a trust problem even if the formulas look similar.

### Proposed State

Add a shared scoring module that is independent from Backtrader strategy orchestration.

Suggested responsibilities:

- compute raw factor values from tabular market data
- normalize factors cross-sectionally
- combine weighted factor scores
- rank securities
- return a structured scoring result

Backtrader strategy code should remain responsible for:

- scheduling rebalances
- position management
- order generation

Paper-trading code should remain responsible for:

- fetching latest data
- loading approved parameters
- generating actionable rebalance diffs
- storing orders

The shared scoring core should sit underneath both.

## Component Design

### 1. Shared Scoring Core

Suggested module:

- `src/scoring/multi_factor.py`

Responsibilities:

- accept a symbol-to-DataFrame mapping
- compute momentum, volatility, and mean reversion factors
- calculate cross-sectional z-scores
- combine weights into a total score
- return ranked results as a DataFrame or typed result object

Output fields should include at least:

- `symbol`
- `price`
- `mom_raw`
- `vol_raw`
- `rev_raw`
- `mom_z`
- `vol_z`
- `rev_z`
- `total_score`
- `rank`

### 2. Experiment Artifact Writer

Suggested module:

- `src/research/artifacts.py`

Responsibilities:

- save experiment outputs to disk
- define a predictable artifact directory structure
- write metadata and score tables in machine-readable formats

Suggested first artifact types:

- run metadata JSON
- ranked score table CSV
- summary JSON

Suggested storage area:

- `.research_artifacts/`

### 3. Experiment Registry

Suggested module:

- `src/research/registry.py`

Responsibilities:

- generate a unique run identifier
- record experiment inputs
- record output artifact paths
- record summary metrics and timestamps

This can start as a JSON-lines or SQLite-backed registry. For the first implementation, JSON is enough if it is simple and append-only.

### 4. Research-to-Paper Parameter Flow

Suggested behavior:

- the paper trader should be able to load an approved parameter artifact rather than hardcoded default weights

This spec does not require a full approval workflow yet. A simple "latest artifact path" or explicit file path is enough for the first version.

## Data Flow

### Research Run

1. Fetch universe data.
2. Pass symbol data and weights into shared scoring core.
3. Receive ranked output table.
4. Save artifacts and metadata.
5. Use artifacts for analysis, explainability, and later comparison.

### Paper-Trading Run

1. Fetch latest universe data.
2. Load weights from approved or specified artifact.
3. Pass symbol data and weights into shared scoring core.
4. Receive ranked output table.
5. Select winners and compute rebalance diff.
6. Store generated orders and report artifacts if needed.

### Backtrader Strategy Run

There are two acceptable stages:

1. Near-term:
   - Keep factor computation inside Backtrader, but add parity tests against the shared scoring core.
2. Preferred future state:
   - Gradually reuse shared logic or a mathematically equivalent adapter to minimize divergence.

This staged approach avoids overcomplicating the first change.

## Error Handling

The first implementation should explicitly handle:

- empty or undersized DataFrames
- missing required price columns
- insufficient history for factor lookbacks
- zero standard deviation during z-score normalization
- empty valid universe after filtering
- invalid or missing artifact paths

Failures should be explicit and readable, not silent.

## Testing Strategy

Tests should focus on trust-building behavior, not just initialization.

### Shared Scoring Tests

- same inputs produce deterministic ranking output
- factor values are computed correctly on known fixtures
- z-score logic handles constant cross-sections safely
- ranking order matches expected total scores

### Parity Tests

- paper-trading winner selection matches shared scoring core
- current Backtrader path is mathematically aligned with shared scoring on controlled fixtures where possible

### Artifact Tests

- registry writes metadata successfully
- artifact files are created with expected schema
- saved artifacts can be reloaded

### Data Validation Tests

- invalid inputs fail with clear errors
- insufficient history causes symbols to be excluded consistently

## Trade-Offs

### Option A: Full platform redesign now

Pros:

- strong long-term architecture

Cons:

- too much scope
- high risk of delay
- mixes infrastructure work with strategy changes

### Option B: Minimal shared scoring and artifacts first

Pros:

- high leverage
- directly improves trust
- low enough scope to complete safely
- supports later milestones cleanly

Cons:

- benchmark and diagnostics still need follow-up work

### Option C: Skip foundation and continue adding features

Pros:

- faster visible feature growth

Cons:

- highest risk of producing misleading recommendations
- compounds technical and research debt

Recommendation:

- choose Option B

## Acceptance Criteria

This subproject is complete when:

1. A shared multi-factor scoring module exists and is used by paper-trading signal generation.
2. The scoring output includes factor-level fields and final ranks.
3. Research or signal-generation runs can save artifacts to a predictable location.
4. A registry entry records the configuration and artifact paths for a run.
5. Tests verify deterministic ranking behavior and paper-trading parity.
6. The README and documentation explain how this improves system confidence.

## Out of Scope

The following are intentionally not part of the first subproject:

- full walk-forward optimization redesign
- benchmark analytics dashboard
- advanced portfolio constraints
- point-in-time universe membership
- stateful approval workflow for strategies

Those should be implemented in later specs and plans after the foundation is in place.

## Recommended Next Step

Create an implementation plan for `Unified Scoring Core and Experiment Artifacts`.
