# Quant

This repository is a small quantitative trading research and paper-trading project focused on Japanese equities.

Today, the project can:

- Fetch and cache a small stock universe from Yahoo Finance.
- Run Backtrader-based backtests across multiple stocks.
- Rank stocks with cross-sectional factor strategies.
- Optimize factor weights with a basic in-sample vs out-of-sample workflow.
- Generate paper-trading rebalance orders from the current signal engine.

The current default idea is:

1. Score each stock in the universe.
2. Rank the stocks cross-sectionally.
3. Buy the top `N` names.
4. Rebalance periodically.

## Current Situation

The project has already moved beyond a single-stock toy strategy and now supports a simple portfolio selection workflow.

### What exists now

- Data pipeline
  - [`src/data/universe.py`](/Users/y-yang/Developer/quant/src/data/universe.py) defines the stock universe helpers.
  - [`src/data/bulk_loader.py`](/Users/y-yang/Developer/quant/src/data/bulk_loader.py) fetches historical data for multiple symbols.
  - [`src/data/yfinance_loader.py`](/Users/y-yang/Developer/quant/src/data/yfinance_loader.py) provides Yahoo Finance loading support.

- Strategies
  - [`src/strategies/sma_crossover.py`](/Users/y-yang/Developer/quant/src/strategies/sma_crossover.py) is a simple single-name baseline.
  - [`src/strategies/momentum_factor.py`](/Users/y-yang/Developer/quant/src/strategies/momentum_factor.py) ranks stocks by cross-sectional momentum and buys the top names monthly.
  - [`src/strategies/multi_factor.py`](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py) is the current main stock-selection strategy. It combines:
    - momentum
    - low volatility
    - mean reversion

- Backtesting and execution modeling
  - [`src/main.py`](/Users/y-yang/Developer/quant/src/main.py) is the main CLI entry point for running backtests.
  - [`src/engine/runner.py`](/Users/y-yang/Developer/quant/src/engine/runner.py) provides the engine runner.
  - [`src/engine/commission.py`](/Users/y-yang/Developer/quant/src/engine/commission.py) models commissions and slippage assumptions.

- Optimization
  - [`src/optimize.py`](/Users/y-yang/Developer/quant/src/optimize.py) runs a grid search over factor weights and performs a simple anti-overfitting check using one in-sample and one out-of-sample split.

- Paper trading
  - [`src/paper/bot.py`](/Users/y-yang/Developer/quant/src/paper/bot.py) generates live rebalance orders from the latest data.
  - [`src/paper/db.py`](/Users/y-yang/Developer/quant/src/paper/db.py) stores cash, holdings, and order history in SQLite.
  - [`src/paper/notifier.py`](/Users/y-yang/Developer/quant/src/paper/notifier.py) sends daily summaries.

- Tests
  - Basic tests exist under [`tests/`](/Users/y-yang/Developer/quant/tests), but coverage is still minimal and mostly validates initialization and simple utility behavior.

### What the current strategy does

The main strategy in [`src/strategies/multi_factor.py`](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py):

- computes factor values for each stock
- converts each factor into a cross-sectional Z-score
- combines those Z-scores using configurable weights
- ranks the universe by total score
- holds the top `N` stocks with equal weights
- rebalances on month changes

In short: the system already knows how to decide which stocks to buy from a small universe.

### What is still missing

The project is in a strong prototype stage, but it is not yet a robust production-grade decision engine.

Main gaps:

- The optimizer uses a one-time train/test split rather than a rolling walk-forward process.
- The live paper-trading signal path does not yet fully depend on dynamically validated parameters.
- The stock-selection output is not very explainable yet; we do not persist factor contributions per rebalance.
- Portfolio turnover control is limited, so rank churn can create unnecessary trading.
- Test coverage does not yet deeply validate ranking behavior, rebalance decisions, or paper/live consistency.
- Universe construction is still relatively small and static.

## Planned Milestones

### Milestone 1: README and project framing

Status: complete with this document.

Goal:

- Make the current architecture and direction easy to understand for future work.

### Milestone 2: Walk-forward decision engine

Status: complete.

Goal:

- Replace the current one-off optimization workflow with a rolling walk-forward process.

Why this matters:

- This is the most important next step for trustworthiness.
- It moves the project from "we found weights that worked once" to "we are selecting stocks using parameters that were validated only on past data."

Deliverables:

- Rolling training and validation windows.
- Per-period selection of factor weights.
- A reusable artifact containing chosen weights by rebalance date.
- Clear comparison between fixed weights and walk-forward weights.

Acceptance criteria:

- A command can run walk-forward optimization across multiple rebalance periods.
- For each rebalance date, the system selects weights using only prior data.
- The output is saved in a machine-readable format such as CSV or JSON.
- Backtest results can compare:
  - static default weights
  - one-shot optimized weights
  - walk-forward weights
- The workflow can be rerun deterministically on the same cached data.

Completed so far:

- [`src/optimize.py`](/Users/y-yang/Developer/quant/src/optimize.py) now runs a rolling walk-forward workflow instead of only a one-shot IS/OOS script.
- Rolling train and validation window construction lives in [`src/research/walk_forward.py`](/Users/y-yang/Developer/quant/src/research/walk_forward.py).
- Walk-forward runs persist per-rebalance weights and summary artifacts under `.research_artifacts/`.
- The walk-forward workflow now reports static default, one-shot optimized, and walk-forward return comparisons in the same run summary.
- Regression coverage for walk-forward windowing, weight selection, artifact writing, and runner output lives in [`tests/research/test_walk_forward.py`](/Users/y-yang/Developer/quant/tests/research/test_walk_forward.py).
- Determinism-oriented regression coverage and artifact-loading ergonomics for downstream consumers are now covered by the research test suite.

### Milestone 3: Explainable stock selection

Status: not started.

Goal:

- Make each buy decision understandable.

Deliverables:

- Save factor-level scores for each stock on each rebalance date.
- Show why a stock was selected, for example:
  - momentum contribution
  - volatility contribution
  - mean reversion contribution
  - final composite score
- Add reporting for the top winners and near-misses.

Why this matters:

- It makes debugging easier.
- It helps confirm whether the strategy is behaving as intended.
- It makes paper-trading decisions easier to trust.

Acceptance criteria:

- Each rebalance produces a record of per-stock factor values and final scores.
- The system can show the selected stocks and at least the next few near-miss candidates.
- A user can inspect why one stock ranked above another on a given rebalance date.
- The explainability output is generated from the same scoring logic as the strategy itself.

### Milestone 4: Paper trader alignment with research pipeline

Status: complete.

Goal:

- Ensure live signals are generated from the same validated decision logic used in research.

Deliverables:

- Paper-trading signal generation reads the latest approved walk-forward parameters.
- Shared scoring logic between backtest and live signal generation.
- Reduced drift between research code and live decision code.

Why this matters:

- The current project already has a paper-trading loop, so connecting it tightly to validated research is the highest-leverage operational improvement.

Acceptance criteria:

- Paper-trading signal generation does not duplicate factor math in a separate incompatible path.
- The paper trader can load the latest validated parameter set automatically.
- Given the same date and market data, research mode and paper-trading mode produce the same ranked winners.
- The project documents where validated parameters live and how they are refreshed.

Completed so far:

- Shared scoring logic now lives in [`src/scoring/multi_factor.py`](/Users/y-yang/Developer/quant/src/scoring/multi_factor.py).
- [`src/paper/bot.py`](/Users/y-yang/Developer/quant/src/paper/bot.py) uses the shared scorer instead of maintaining a separate factor-math path.
- [`src/strategies/multi_factor.py`](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py) now routes ranking through the shared scorer via a Backtrader adapter instead of maintaining its own factor-math path.
- Tests cover ranking parity between the shared scorer and paper-signal generation.
- Tests now cover ranking parity across the shared scorer, the Backtrader strategy adapter, and the paper-trading path under the same weights.
- Walk-forward parameter artifacts can now be produced by [`src/optimize.py`](/Users/y-yang/Developer/quant/src/optimize.py).
- Approved paper-trading params can now be selected from qualified walk-forward runs and loaded by the paper trader by default.
- An operator-facing approval CLI now lives in [`src/research/approve.py`](/Users/y-yang/Developer/quant/src/research/approve.py), including candidate listing and default approval of the latest rebalance date for a chosen run.
- The multi-factor backtest path in [`src/main.py`](/Users/y-yang/Developer/quant/src/main.py) now uses the same approved params source by default unless explicit CLI weights are supplied.
- The walk-forward optimizer now supports explicit CLI time-window control in [`src/optimize.py`](/Users/y-yang/Developer/quant/src/optimize.py), so research runs can be reproduced and approved against stable date ranges instead of hand-edited script values.

### Milestone 5: Turnover and risk controls

Status: complete.

Goal:

- Reduce fragile portfolio churn and make rebalancing more realistic.

Deliverables:

- Rank buffer or buy/sell threshold rules.
- Optional minimum holding period.
- Optional volatility or concentration caps.
- Better transaction-awareness around rebalance decisions.

Why this matters:

- A strategy can look good on ranking quality but still lose edge through overtrading.

Acceptance criteria:

- The strategy can optionally keep a current holding unless it falls below a configurable sell threshold.
- Backtest output includes at least one turnover-related metric.
- We can compare portfolio behavior before and after turnover controls.
- Risk-control settings are configurable and do not break the base strategy path.

Completed so far:

- [`src/strategies/multi_factor.py`](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py) now supports configurable `buy_rank_threshold` and `sell_rank_threshold` controls while preserving the original top-`N` behavior by default.
- The multi-factor rebalance path now keeps existing holdings inside the sell buffer, only admits new names inside the buy threshold, and still caps final target holdings by `top_n`.
- Simple turnover metrics now flow through the strategy and reusable backtest runner, including rebalance count, position change count, and turnover ratio.
- [`src/main.py`](/Users/y-yang/Developer/quant/src/main.py) now accepts turnover-control CLI settings and reports turnover metrics in multi-factor backtest output.
- Focused turnover-control regression coverage now lives in [`tests/strategies/test_multi_factor_turnover.py`](/Users/y-yang/Developer/quant/tests/strategies/test_multi_factor_turnover.py).
- Existing parity and backtest-default coverage now also validates that buffered turnover controls do not break the base shared-scoring path or approved-weight resolution workflow.

### Milestone 6: Stronger test coverage

Status: complete.

Goal:

- Build confidence that ranking, rebalancing, and paper trading remain correct as the system evolves.

Deliverables:

- Strategy tests for factor scoring and top-`N` selection.
- Rebalance tests for entering, exiting, and resizing positions.
- Tests that verify live signal generation matches the research scoring logic.
- Regression tests for optimizer and walk-forward output.

Acceptance criteria:

- Tests cover both ranking correctness and rebalance behavior.
- At least one test ensures paper-trading signals match shared research scoring.
- At least one regression-style test protects walk-forward output shape and saved artifacts.
- The core milestone workflows can run in CI without requiring live network access.

Completed so far:

- Shared scoring behavior is covered in [`tests/scoring/test_multi_factor.py`](/Users/y-yang/Developer/quant/tests/scoring/test_multi_factor.py).
- Artifact writing and registry behavior are covered in [`tests/research/test_artifacts.py`](/Users/y-yang/Developer/quant/tests/research/test_artifacts.py).
- Paper-signal parity with the shared scorer is covered at the unit-test level.
- Walk-forward runner behavior and artifact shape are covered in [`tests/research/test_walk_forward.py`](/Users/y-yang/Developer/quant/tests/research/test_walk_forward.py).
- Rebalance behavior now has a no-op regression for non-rankable universes in [`tests/strategies/test_multi_factor_parity.py`](/Users/y-yang/Developer/quant/tests/strategies/test_multi_factor_parity.py).
- The main backtest CLI has a CI-oriented offline smoke test that verifies approved-parameter resolution and plotting suppression in [`tests/research/test_backtest_defaults.py`](/Users/y-yang/Developer/quant/tests/research/test_backtest_defaults.py).
- The offline approval flow is covered end to end in [`tests/research/test_approved_params.py`](/Users/y-yang/Developer/quant/tests/research/test_approved_params.py) and [`tests/research/test_approve_cli.py`](/Users/y-yang/Developer/quant/tests/research/test_approve_cli.py).
- The milestone is closed out by a small CI-friendly regression pack that runs without network access and exercises research artifacts, approval selection, strategy parity, and the backtest entrypoint together.

Milestone 6 closeout:

- Added deeper rebalance-behavior coverage without changing strategy logic.
- Added regression coverage for walk-forward outputs, parameter artifacts, and approval round-tripping.
- Added offline workflow checks for the main backtest entrypoint so core research and paper-trading paths stay CI-safe.

### Milestone 7: Better universe and portfolio research

Status: not started.

Goal:

- Improve the quality of research inputs and portfolio construction.

Deliverables:

- Larger universe support.
- More realistic universe definitions.
- Better baselines and benchmark comparisons.
- Portfolio analytics such as turnover, hit rate, and contribution analysis.

Acceptance criteria:

- The system can evaluate a larger configured universe without changing core strategy code.
- At least one benchmark comparison is available in reports.
- Research output includes portfolio-level diagnostics beyond return alone.
- Universe definition is explicit and reproducible for a given experiment.

### Milestone X: Research Platform Foundation

Status: in progress.

Goal:

- Add the missing platform layer that makes research outputs traceable, comparable, reusable, and safer to connect to paper trading.

Why this matters:

- The project already has strategies, optimization, and paper trading.
- The current weak point is not "lack of features" but "lack of confidence infrastructure."
- In practice, this solves the trust problem of research/live drift: the same score is computed once, saved once, and can be audited or replayed later.
- Without this layer, the system can produce recommendations before it can clearly prove:
  - why the recommendation exists
  - whether the result is reproducible
  - whether research and paper trading are using the same decision logic
  - whether the system is becoming more trustworthy over time

Core components:

- Unified Scoring Core
  - Shared scoring logic in [`src/scoring/multi_factor.py`](/Users/y-yang/Developer/quant/src/scoring/multi_factor.py) used by research, backtesting, optimization, and paper trading.
- Experiment Registry
  - A structured record of each experiment, including universe, date range, parameters, benchmark, metrics, and artifact paths.
- Research Artifact Store
  - Persistent outputs written under `.research_artifacts/` via [`src/research/artifacts.py`](/Users/y-yang/Developer/quant/src/research/artifacts.py) and tracked in [`src/research/registry.py`](/Users/y-yang/Developer/quant/src/research/registry.py).
- Benchmark and Attribution Layer
  - Explicit baseline comparison so we can measure active value, not only absolute returns.
- Data Validation Layer
  - Checks for missing data, duplicate rows, date coverage, cache quality, and other silent data issues.
- Diagnostics Layer
  - Metrics such as turnover, rank stability, holding period, hit rate, and factor spread behavior.
- Portfolio Construction Layer
  - A clear portfolio-building step that can evolve beyond equal weight top-`N`.
- Calendar and Rebalance Policy
  - Explicit rules for signal timing, trading days, and rebalance scheduling.
- Strategy Lifecycle States
  - States such as draft, research-approved, and paper-active to prevent mixing experimental ideas with paper-traded decisions.
- Universe Governance
  - Reproducible universe definitions for research and future point-in-time improvements.

Recommended priority:

1. Unified Scoring Core
2. Experiment Registry
3. Research Artifact Store
4. Benchmark and Attribution Layer
5. Data Validation Layer
6. Diagnostics Layer
7. Portfolio Construction Layer
8. Calendar and Rebalance Policy
9. Strategy Lifecycle States
10. Universe Governance

Completed so far:

- Unified Scoring Core in [`src/scoring/multi_factor.py`](/Users/y-yang/Developer/quant/src/scoring/multi_factor.py)
- Experiment Registry in [`src/research/registry.py`](/Users/y-yang/Developer/quant/src/research/registry.py)
- Research Artifact Store in [`src/research/artifacts.py`](/Users/y-yang/Developer/quant/src/research/artifacts.py)
- Paper-signal integration through [`src/paper/bot.py`](/Users/y-yang/Developer/quant/src/paper/bot.py)
- Walk-forward orchestration and weight artifacts through [`src/research/walk_forward.py`](/Users/y-yang/Developer/quant/src/research/walk_forward.py) and [`src/optimize.py`](/Users/y-yang/Developer/quant/src/optimize.py)

Next foundation slice:

- Explicit approval and lifecycle controls on top of validated-parameter loading
- Benchmark comparison output
- Data validation and diagnostics

Acceptance criteria:

- Research, backtest, optimization, and paper trading can point to the same scoring logic.
- Every meaningful experiment produces a recorded configuration and saved artifacts.
- Results can be compared against at least one explicit benchmark.
- Data quality failures are detected before they silently affect conclusions.
- The system can explain not only what it recommends, but also how trustworthy that recommendation is.

## Trust Model

The project should not treat profitability alone as proof of quality.

Instead, system trustworthiness should be evaluated across four dimensions:

### 1. Consistency

The same data, date, and parameters should produce the same ranking and decision output across research and paper-trading paths.

Signals of improvement:

- research and paper-trading ranking parity
- reduced drift across execution paths
- parameter usage that matches approved recorded artifacts

### 2. Reproducibility

Any important result should be rerunnable from stored inputs and artifacts.

Signals of improvement:

- each experiment has a traceable record
- artifacts are saved and reloadable
- repeated runs on the same cached data produce the same outputs

### 3. Relative Edge

The strategy should be evaluated against explicit baselines, not just on absolute returns.

Signals of improvement:

- outperformance versus equal-weight or other benchmark baselines
- better drawdown behavior relative to benchmark
- walk-forward results that hold up against static defaults

### 4. Stability

A useful strategy should remain credible across time windows and reasonable parameter changes.

Signals of improvement:

- walk-forward robustness
- lower unnecessary turnover
- stable rank behavior
- lower sensitivity to small changes in configuration

## Confidence Levels

To keep the roadmap practical, we can think about the system in three confidence stages.

### Low Confidence

The system can generate recommendations, but trust is limited.

Typical traits:

- research and paper-trading logic may drift
- result tracking is incomplete
- benchmark comparison is weak
- recommendations are difficult to audit after the fact

### Medium Confidence

The system has enough structure to make research conclusions meaningfully inspectable.

Typical traits:

- shared scoring logic
- experiment registry and saved artifacts
- walk-forward outputs recorded
- explicit benchmark comparisons
- basic diagnostics and data validation

### High Confidence

The system has a strong feedback loop for both decision quality and operational discipline.

Typical traits:

- robust data validation
- long-running out-of-sample evidence
- strong research and paper-trading parity
- portfolio construction and lifecycle controls
- clear evidence that trustworthiness is improving over time

## Execution Plan

This section turns the roadmap into a practical build order with a clear definition of done.

### Phase 1: Make decisions trustworthy

Scope:

- Build Milestone 2 first.

Status: next active phase.

Current state: complete.

Definition of done:

- We can run a walk-forward experiment end to end.
- The chosen weights are saved by rebalance date.
- The results are comparable against the current static-weight approach.

Suggested implementation tasks:

1. Refactor optimization code so parameter search can run for an arbitrary date window.
2. Add rolling window orchestration on top of that reusable optimizer.
3. Save validated weights to an artifact file.
4. Add summary output comparing walk-forward and baseline performance.
5. Extend the same summary so static default, one-shot optimized, and walk-forward results can be compared side by side.

### Phase 2: Remove research/live drift

Scope:

- Build Milestone 4 immediately after Milestone 2.

Status: complete.

Definition of done:

- Live paper-trading signals and research backtests share the same scoring logic and parameter source.

Suggested implementation tasks:

1. Backtest/research path should consume the same shared scorer where practical.
2. Update the paper trader to read validated parameters from the walk-forward artifact.
3. Add a parity test between research ranking and paper-trading ranking under the validated parameter source.

### Phase 3: Make stock picks explainable

Scope:

- Build Milestone 3 once the live and research paths are aligned.

Definition of done:

- For any rebalance date, we can explain why a stock was selected.

Suggested implementation tasks:

1. Persist factor inputs and weighted contributions per stock.
2. Add a simple report or CLI view for winners and near-misses.
3. Save outputs in a format that is easy to inspect later.

### Phase 4: Reduce unnecessary trading

Scope:

- Build Milestone 5 after explainability makes the strategy easier to inspect.

Definition of done:

- We can measure and reduce avoidable portfolio churn.

Suggested implementation tasks:

1. Add sell-buffer and buy-buffer rules.
2. Add turnover metrics to backtest output.
3. Compare performance and trading activity with and without the new controls.

### Phase 5: Harden the system

Scope:

- Build Milestones 6 and 7 as the stabilization and scaling phase.

Definition of done:

- The project is easier to extend, test, and trust with larger universes and richer reporting.

Suggested implementation tasks:

1. Expand unit and regression tests around ranking and rebalance behavior.
2. Remove avoidable duplication in research and execution code paths.
3. Add broader benchmark and portfolio analytics support.
4. Expand universe definitions in a controlled, reproducible way.

## Recommended Immediate Next Task

If we are starting implementation now, the best next task is Milestone 3 explainability output:

1. Persist per-stock factor inputs and weighted contributions for each rebalance.
2. Show selected winners alongside near-miss candidates from the same ranking run.
3. Make the output easy to inspect later from saved artifacts or a lightweight CLI view.

That turns aligned research and paper-trading decisions into decisions we can also explain and debug.

## Suggested Near-Term Order

If we want the best sequence from here, the recommended order is:

1. Add explainability output for each rebalance.
2. Add turnover controls.
3. Deepen tests.

That order improves decision quality first, then operational consistency, then safety and maintainability.

## How to Run the Current Project

Examples:

```bash
uv sync --dev
```

```bash
uv run python -m src.main --strategy multi --universe --no-plot
```

```bash
uv run python -m src.optimize
```

```bash
uv run python -m src.optimize --start 2024-01-04 --end 2025-12-30 --train-months 12 --validation-months 6 --step-months 6
```

`src.optimize` now supports explicit CLI control over the research window and walk-forward settings. Its default research period is `2021-01-01` through `2024-01-01`, with a 12-month training window, 6-month validation window, and 6-month step size. It prints a summary that compares static default weights, one-shot optimized weights, and walk-forward weights. Walk-forward artifacts are written under `.research_artifacts/`. The newest run is not automatically treated as approved for paper trading. Instead, paper trading should use the approved params file at `.research_artifacts/paper_trade_params.json`, which points to a chosen validated parameter set.

Operator approval flow:

```bash
uv run python -m src.research.approve list
```

```bash
uv run python -m src.research.approve approve --run-id <id>
```

```bash
uv run python -m src.research.approve approve --run-id <id> --rebalance-date YYYY-MM-DD
```

The strict offline verification path for Milestone 2 lives in the research tests, including walk-forward summary regression coverage, deterministic artifact checks, approved-parameter validation, and an offline optimizer smoke test.

```bash
uv run python -m src.paper.bot status
uv run python -m src.paper.bot generate
```

```bash
uv run pytest -q
```

## Notes

- The current system is best understood as a research prototype with real momentum toward a more disciplined portfolio engine.
- The strongest completed capability today is cross-sectional stock ranking and top-`N` portfolio selection.
- The shared scoring core and experiment artifact foundation are now in place for paper-signal generation.
- The highest-value next milestone is Milestone 3: making each rebalance decision explainable.
- Python dependencies are now managed through `uv` using [`pyproject.toml`](/Users/y-yang/Developer/quant/pyproject.toml) and `uv.lock`.
