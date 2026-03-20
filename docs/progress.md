# Progress

This file keeps detailed milestone history and completion notes so [`README.md`](/Users/y-yang/Developer/quant/README.md) can stay focused on the current system shape.

## Milestone Summary

| Milestone | Status | Scope |
| --- | --- | --- |
| 1 | Complete | README and project framing |
| 2 | Complete | Walk-forward decision engine |
| 3 | Complete | Explainable stock selection |
| 4 | Complete | Paper trader alignment with research pipeline |
| 5 | Complete | Turnover and risk controls |
| 6 | Complete | Stronger test coverage |
| 7 | In progress | Better universe and portfolio research |
| 8 | In progress | Confidence infrastructure and lifecycle controls |

Milestone 8 was previously labeled "Milestone X". It has been renamed to make its position explicit in the roadmap.

## Milestone 1: README and Project Framing

Status: complete.

Goal:

- Make the current architecture and direction easy to understand for future work.

Current closeout:

- The README now focuses on the current system, architecture flow, quant caveats, and milestone status.
- Detailed milestone history has been moved into this file to reduce README maintenance overhead.

## Milestone 2: Walk-Forward Decision Engine

Status: complete.

Goal:

- Replace the one-off optimization workflow with a rolling walk-forward process.

Completed:

- [`src/optimize.py`](/Users/y-yang/Developer/quant/src/optimize.py) runs a rolling walk-forward workflow instead of only a one-shot IS/OOS script.
- Rolling training and validation window construction lives in [`src/research/walk_forward.py`](/Users/y-yang/Developer/quant/src/research/walk_forward.py).
- Walk-forward runs persist per-rebalance weights and summary artifacts under `.research_artifacts/`.
- Walk-forward reporting includes static default, one-shot optimized, and walk-forward return comparisons.
- Regression coverage for walk-forward windowing, artifact writing, summary diagnostics, and runner output lives in:
  [`tests/research/test_walk_forward.py`](/Users/y-yang/Developer/quant/tests/research/test_walk_forward.py),
  [`tests/research/test_diagnostics.py`](/Users/y-yang/Developer/quant/tests/research/test_diagnostics.py)

## Milestone 3: Explainable Stock Selection

Status: complete.

Goal:

- Make each buy decision understandable.

Completed:

- [`src/scoring/multi_factor.py`](/Users/y-yang/Developer/quant/src/scoring/multi_factor.py) emits raw factors, Z-scores, factor contributions, total score, rank, and top-`N` flags.
- [`src/paper/bot.py`](/Users/y-yang/Developer/quant/src/paper/bot.py) and [`src/research/artifacts.py`](/Users/y-yang/Developer/quant/src/research/artifacts.py) persist winners, near-misses, and the full scored universe.
- Explainability helpers live in [`src/research/explain.py`](/Users/y-yang/Developer/quant/src/research/explain.py).
- Strategy-level rebalance artifacts are persisted from [`src/strategies/multi_factor.py`](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py).
- Coverage lives in:
  [`tests/scoring/test_multi_factor.py`](/Users/y-yang/Developer/quant/tests/scoring/test_multi_factor.py),
  [`tests/research/test_artifacts.py`](/Users/y-yang/Developer/quant/tests/research/test_artifacts.py),
  [`tests/research/test_explain.py`](/Users/y-yang/Developer/quant/tests/research/test_explain.py),
  [`tests/strategies/test_multi_factor_parity.py`](/Users/y-yang/Developer/quant/tests/strategies/test_multi_factor_parity.py)

## Milestone 4: Paper Trader Alignment With Research Pipeline

Status: complete.

Goal:

- Ensure live signals are generated from the same validated decision logic used in research.

Completed:

- Shared scoring logic lives in [`src/scoring/multi_factor.py`](/Users/y-yang/Developer/quant/src/scoring/multi_factor.py).
- [`src/paper/bot.py`](/Users/y-yang/Developer/quant/src/paper/bot.py) and [`src/strategies/multi_factor.py`](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py) now route through the shared scorer path.
- Walk-forward parameter artifacts can be produced by [`src/optimize.py`](/Users/y-yang/Developer/quant/src/optimize.py).
- Approved paper-trading params can be selected and loaded by default via:
  [`src/research/approved_params.py`](/Users/y-yang/Developer/quant/src/research/approved_params.py),
  [`src/research/approve.py`](/Users/y-yang/Developer/quant/src/research/approve.py)
- The multi-factor backtest path in [`src/main.py`](/Users/y-yang/Developer/quant/src/main.py) uses the same approved params source by default unless explicit CLI weights are supplied.

## Milestone 5: Turnover and Risk Controls

Status: complete.

Goal:

- Reduce fragile portfolio churn and make rebalancing more realistic.

Completed:

- [`src/strategies/multi_factor.py`](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py) supports `buy_rank_threshold` and `sell_rank_threshold` while preserving top-`N` behavior by default.
- Turnover metrics now flow through the strategy and reusable backtest runner.
- [`src/main.py`](/Users/y-yang/Developer/quant/src/main.py) accepts turnover-control CLI settings and reports turnover metrics in multi-factor backtest output.
- Focused regression coverage lives in [`tests/strategies/test_multi_factor_turnover.py`](/Users/y-yang/Developer/quant/tests/strategies/test_multi_factor_turnover.py).

## Milestone 6: Stronger Test Coverage

Status: complete.

Goal:

- Build confidence that ranking, rebalancing, and paper trading remain correct as the system evolves.

Completed:

- Shared scoring behavior is covered in [`tests/scoring/test_multi_factor.py`](/Users/y-yang/Developer/quant/tests/scoring/test_multi_factor.py).
- Artifact writing and registry behavior are covered in [`tests/research/test_artifacts.py`](/Users/y-yang/Developer/quant/tests/research/test_artifacts.py).
- Portfolio diagnostics are covered in [`tests/research/test_diagnostics.py`](/Users/y-yang/Developer/quant/tests/research/test_diagnostics.py).
- Walk-forward runner behavior and artifact shape are covered in [`tests/research/test_walk_forward.py`](/Users/y-yang/Developer/quant/tests/research/test_walk_forward.py).
- Offline approval flow and backtest-default coverage live in:
  [`tests/research/test_approved_params.py`](/Users/y-yang/Developer/quant/tests/research/test_approved_params.py),
  [`tests/research/test_approve_cli.py`](/Users/y-yang/Developer/quant/tests/research/test_approve_cli.py),
  [`tests/research/test_backtest_defaults.py`](/Users/y-yang/Developer/quant/tests/research/test_backtest_defaults.py)

## Milestone 7: Better Universe and Portfolio Research

Status: in progress.

Goal:

- Improve the quality of research inputs and portfolio construction.

Acceptance criteria:

- The system can evaluate a larger configured universe without changing core strategy code.
- At least one benchmark comparison is available in reports.
- Research output includes portfolio-level diagnostics beyond return alone.
- Universe definition is explicit and reproducible for a given experiment.

Completed:

- Benchmark comparison is available in walk-forward reporting through:
  [`src/optimize.py`](/Users/y-yang/Developer/quant/src/optimize.py),
  [`src/research/walk_forward.py`](/Users/y-yang/Developer/quant/src/research/walk_forward.py)
- Portfolio-level turnover diagnostics already flow through:
  [`src/engine/runner.py`](/Users/y-yang/Developer/quant/src/engine/runner.py),
  [`src/main.py`](/Users/y-yang/Developer/quant/src/main.py)
- Walk-forward research output includes hit-rate and top/bottom contributor summaries.
- Universe selection is explicit and reproducible through:
  [`src/data/universe.py`](/Users/y-yang/Developer/quant/src/data/universe.py),
  [`src/main.py`](/Users/y-yang/Developer/quant/src/main.py),
  [`src/optimize.py`](/Users/y-yang/Developer/quant/src/optimize.py),
  [`src/research/artifacts.py`](/Users/y-yang/Developer/quant/src/research/artifacts.py)
- The named registry includes larger curated Japanese equity universes.

Still missing:

- Stronger research outputs around larger-universe behavior
- Richer trust diagnostics such as rank stability and factor spread
- Better linkage to lifecycle-state controls in the approval-to-paper path

## Milestone 8: Confidence Infrastructure and Lifecycle Controls

Status: in progress.

Goal:

- Add the platform layer that makes research outputs traceable, comparable, reusable, and safer to connect to paper trading.

Acceptance criteria:

- Research, backtest, optimization, and paper trading can point to the same scoring logic.
- Every meaningful experiment produces a recorded configuration and saved artifacts.
- Results can be compared against at least one explicit benchmark.
- Data quality failures are detected before they silently affect conclusions.
- The system can explain not only what it recommends, but also how trustworthy that recommendation is.

Completed:

- Unified scoring core in [`src/scoring/multi_factor.py`](/Users/y-yang/Developer/quant/src/scoring/multi_factor.py)
- Experiment registry in [`src/research/registry.py`](/Users/y-yang/Developer/quant/src/research/registry.py)
- Research artifact store in [`src/research/artifacts.py`](/Users/y-yang/Developer/quant/src/research/artifacts.py)
- Walk-forward orchestration and weight artifacts through:
  [`src/research/walk_forward.py`](/Users/y-yang/Developer/quant/src/research/walk_forward.py),
  [`src/optimize.py`](/Users/y-yang/Developer/quant/src/optimize.py)
- Approved-parameter loading and operator approval flow through:
  [`src/research/approved_params.py`](/Users/y-yang/Developer/quant/src/research/approved_params.py),
  [`src/research/approve.py`](/Users/y-yang/Developer/quant/src/research/approve.py)
- Basic data validation for cached historical slices through:
  [`src/research/data_validation.py`](/Users/y-yang/Developer/quant/src/research/data_validation.py),
  [`src/data/bulk_loader.py`](/Users/y-yang/Developer/quant/src/data/bulk_loader.py)

Still missing:

- Richer diagnostics beyond hit rate, contributor summaries, and universe participation
- Explicit strategy lifecycle states on top of approved-parameter loading
- Broader universe governance beyond the current static named registries

## Recommended Near-Term Order

1. Add richer diagnostics on top of the current data-validation and explainability foundations.
2. Expand universe governance in a controlled, reproducible way.
3. Strengthen lifecycle-state and trust-reporting infrastructure.

That order improves decision quality first, then research breadth, then operational discipline.
