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

### Milestone 3: Explainable stock selection

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

### Milestone 5: Turnover and risk controls

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

### Milestone 6: Stronger test coverage

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

### Milestone 7: Better universe and portfolio research

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
- parameter usage that matches recorded artifacts

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

Definition of done:

- We can run a walk-forward experiment end to end.
- The chosen weights are saved by rebalance date.
- The results are comparable against the current static-weight approach.

Suggested implementation tasks:

1. Refactor optimization code so parameter search can run for an arbitrary date window.
2. Add rolling window orchestration on top of that reusable optimizer.
3. Save validated weights to an artifact file.
4. Add summary output comparing walk-forward and baseline performance.

### Phase 2: Remove research/live drift

Scope:

- Build Milestone 4 immediately after Milestone 2.

Definition of done:

- Live paper-trading signals and research backtests share the same scoring logic and parameter source.

Suggested implementation tasks:

1. Extract factor scoring into a shared module.
2. Update the Backtrader strategy to consume shared score calculations where practical.
3. Update the paper trader to read validated parameters from the walk-forward artifact.
4. Add a parity test between research ranking and paper-trading ranking.

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

If we are starting implementation now, the best next task is:

1. Refactor the optimizer into reusable functions that can run on arbitrary date windows.
2. Build a walk-forward runner on top of those functions.
3. Save chosen weights by rebalance period.

That gives the project a stronger decision foundation before we invest in more live execution behavior.

## Suggested Near-Term Order

If we want the best sequence from here, the recommended order is:

1. Build walk-forward optimization.
2. Unify research and paper-trading scoring logic.
3. Add explainability output for each rebalance.
4. Add turnover controls.
5. Deepen tests.

That order improves decision quality first, then operational consistency, then safety and maintainability.

## How to Run the Current Project

Examples:

```bash
python3 src/main.py --strategy multi --universe --no-plot
```

```bash
python3 src/optimize.py
```

```bash
python3 src/paper/bot.py status
python3 src/paper/bot.py generate
```

## Notes

- The current system is best understood as a research prototype with real momentum toward a more disciplined portfolio engine.
- The strongest completed capability today is cross-sectional stock ranking and top-`N` portfolio selection.
- The highest-value next milestone is making those buy decisions walk-forward validated and consistent between backtest and paper trading.
