# Quant

This repository is a Japanese equities research and paper-trading project.

It is currently a research prototype that can score a small universe, run walk-forward backtests, persist research artifacts, and generate paper-trading rebalance orders from approved parameters.

Today, the system can:

- fetch and cache named stock universes from Yahoo Finance
- rank stocks cross-sectionally with a shared multi-factor scorer
- run Backtrader portfolio backtests with commission and slippage assumptions
- optimize factor weights with a rolling walk-forward workflow
- persist scored-universe and experiment artifacts for later inspection
- generate paper-trading orders from the same approved research path

## Strategy At a Glance

The current default idea is:

1. Score each stock in the configured universe.
2. Rank the stocks cross-sectionally.
3. Buy the top `N` names.
4. Rebalance periodically.

The main strategy in [`src/strategies/multi_factor.py`](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py) uses the shared scorer in [`src/scoring/multi_factor.py`](/Users/y-yang/Developer/quant/src/scoring/multi_factor.py).

| Factor | Current definition | Direction | Current lookback |
| --- | --- | --- | --- |
| Momentum | Price return from the current close to the close `90` trading days earlier | Higher is better | `90` days |
| Low volatility | Standard deviation of daily returns over the last `20` trading days | Lower is better | `20` days |
| Mean reversion | Distance between the current close and the `20`-day simple moving average | Lower is better | `20` days |

These raw factor values are converted into cross-sectional Z-scores on each rebalance date and combined with configurable weights. The portfolio then holds the top `N` names with equal target weights, with optional buy/sell rank buffers to reduce churn.

## Architecture Flow

The high-level research and execution path is:

`Yahoo Finance / cache -> universe definition -> shared scorer -> backtest or walk-forward research -> artifact store and registry -> approved params -> paper-trading bot`

The main modules are:

- Data and universe loading:
  [`src/data/universe.py`](/Users/y-yang/Developer/quant/src/data/universe.py),
  [`src/data/bulk_loader.py`](/Users/y-yang/Developer/quant/src/data/bulk_loader.py),
  [`src/data/yfinance_loader.py`](/Users/y-yang/Developer/quant/src/data/yfinance_loader.py)
- Shared scoring and strategy logic:
  [`src/scoring/multi_factor.py`](/Users/y-yang/Developer/quant/src/scoring/multi_factor.py),
  [`src/strategies/multi_factor.py`](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py)
- Backtesting and execution modeling:
  [`src/main.py`](/Users/y-yang/Developer/quant/src/main.py),
  [`src/engine/runner.py`](/Users/y-yang/Developer/quant/src/engine/runner.py),
  [`src/engine/commission.py`](/Users/y-yang/Developer/quant/src/engine/commission.py)
- Walk-forward research, artifacts, and approvals:
  [`src/optimize.py`](/Users/y-yang/Developer/quant/src/optimize.py),
  [`src/research/walk_forward.py`](/Users/y-yang/Developer/quant/src/research/walk_forward.py),
  [`src/research/artifacts.py`](/Users/y-yang/Developer/quant/src/research/artifacts.py),
  [`src/research/registry.py`](/Users/y-yang/Developer/quant/src/research/registry.py),
  [`src/research/approve.py`](/Users/y-yang/Developer/quant/src/research/approve.py)
- Paper trading:
  [`src/paper/bot.py`](/Users/y-yang/Developer/quant/src/paper/bot.py),
  [`src/paper/db.py`](/Users/y-yang/Developer/quant/src/paper/db.py),
  [`src/paper/notifier.py`](/Users/y-yang/Developer/quant/src/paper/notifier.py)

## Current State

What exists now:

- A shared multi-factor scorer is already used across research, backtesting, and paper-trading paths.
- Walk-forward optimization can save per-rebalance parameter choices and benchmark comparisons under `.research_artifacts/`.
- Paper trading can load approved parameters instead of maintaining a separate factor-math path.
- Explainability artifacts can persist winners, near-misses, and full scored universes.
- The offline test suite covers scoring, diagnostics, artifact persistence, approval flow, and ranking parity.

What is still missing:

- Data validation is still lightweight and does not yet cover richer cache-quality, coverage, or corporate-action diagnostics.
- Configured universes are explicit and reproducible, but they are still static lists rather than point-in-time membership sets.
- Trust diagnostics still need to grow beyond turnover, hit rate, contributors, and participation coverage.
- Strategy lifecycle controls between research, approval, and paper activation are still thinner than they should be.

Detailed milestone history and completion notes live in [`docs/progress.md`](/Users/y-yang/Developer/quant/docs/progress.md).

## Quant Guardrails and Current Limits

This README should make the current research limits explicit:

- Look-ahead bias:
  the walk-forward workflow is designed to choose weights using prior data only, but the current strategy still works from end-of-day bars and monthly rebalance logic. It should be treated as a research approximation until signal timing and trading-calendar policy become more explicit.
- Yahoo Finance data quality:
  [`src/data/yfinance_loader.py`](/Users/y-yang/Developer/quant/src/data/yfinance_loader.py) currently wraps `yf.download(...)` with minimal post-processing. Adjusted-price conventions, suspensions, delistings, and other corporate-action edge cases are not yet independently normalized or audited in this project.
- Survivorship bias:
  the named universes in [`src/data/universe.py`](/Users/y-yang/Developer/quant/src/data/universe.py) are curated static lists, not historical point-in-time constituents. Backtest results may therefore overstate robustness.
- Transaction-cost sensitivity:
  commission and slippage are modeled in [`src/engine/commission.py`](/Users/y-yang/Developer/quant/src/engine/commission.py), but the project still needs more explicit sensitivity analysis under higher-friction assumptions.

Those constraints mean the current output is best used as research evidence, not as proof that the strategy is ready for real capital.

## Trust Model

The project should not treat profitability alone as proof of quality.

Instead, system trustworthiness should be evaluated across four dimensions:

1. Consistency
   The same data, date, and parameters should produce the same ranking and decision output across research and paper-trading paths.
2. Reproducibility
   Important results should be rerunnable from stored inputs and artifacts.
3. Relative edge
   Strategy performance should be compared against explicit baselines, not only absolute returns.
4. Stability
   A useful strategy should remain credible across time windows and reasonable parameter changes.

## Confidence Levels

- Low confidence:
  the system can generate recommendations, but research and execution trust is still limited.
- Medium confidence:
  shared scoring, artifacts, benchmark comparisons, and reproducible universes make conclusions inspectable.
- High confidence:
  stronger data validation, long-running out-of-sample evidence, lifecycle controls, and trust diagnostics create a durable feedback loop.

## Milestone Status

The roadmap is now organized as numbered milestones only:

| Milestone | Status | Focus |
| --- | --- | --- |
| 1 | Complete | README and project framing |
| 2 | Complete | Walk-forward decision engine |
| 3 | Complete | Explainable stock selection |
| 4 | Complete | Paper trader alignment with research pipeline |
| 5 | Complete | Turnover and risk controls |
| 6 | Complete | Stronger test coverage |
| 7 | In progress | Better universe and portfolio research |
| 8 | In progress | Confidence infrastructure and lifecycle controls |

Milestone 8 replaces the old "Milestone X" label. It is a follow-on platform milestone, not a parallel track to Milestone 7.

The intended boundary is:

- Milestone 7 focuses on larger universes, benchmark coverage, and richer portfolio diagnostics.
- Milestone 8 focuses on confidence infrastructure such as data validation, traceability, lifecycle states, and trust reporting.

## Near-Term Priorities

If work continues now, the recommended order is:

1. Add richer diagnostics such as rank-stability and factor-spread reporting.
2. Expand universe governance beyond the initial static named registries.
3. Strengthen lifecycle-state and trust-reporting infrastructure on top of saved artifacts.

That sequence improves decision quality first, then research breadth, then operational discipline.

## How to Run the Current Project

Examples:

```bash
uv sync --dev
```

```bash
uv run python -m src.main --strategy multi --universe --no-plot
```

```bash
uv run python -m src.main --strategy multi --universe-name topix_top_10 --no-plot
```

```bash
uv run python -m src.optimize
```

```bash
uv run python -m src.optimize --start 2024-01-04 --end 2025-12-30 --train-months 12 --validation-months 6 --step-months 6
```

```bash
uv run python -m src.optimize --universe-name topix_top_10 --start 2024-01-04 --end 2025-12-30 --train-months 12 --validation-months 6 --step-months 6
```

`src.optimize` supports explicit CLI control over the research window, named universe selection, and walk-forward settings. Its default research period is `2021-01-01` through `2024-01-01`, with a `12`-month training window, `6`-month validation window, and `6`-month step size. Walk-forward artifacts are written under `.research_artifacts/`, and paper trading should use the approved params file at `.research_artifacts/paper_trade_params.json` rather than assuming the newest run is automatically approved.

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

Paper trading:

```bash
uv run python -m src.paper.bot status
uv run python -m src.paper.bot generate
```

Tests:

```bash
uv run pytest -q
```
