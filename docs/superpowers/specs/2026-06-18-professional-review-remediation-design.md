# Professional Review Remediation Design

## Status

Approved by direct user request: "please fix all fixable issues found; document unfixable issues in README."

## Goal

Repair the locally fixable defects found in the professional finance review and make the remaining institutional research limitations explicit in README.

## In Scope

- Make `top_n` a first-class research/backtest parameter instead of hard-coding `3` in optimizer execution paths.
- Correct the `simple` engine's evaluation series so returns, Sharpe, and drawdown are based on portfolio value through the evaluation end, not only rebalance-day snapshots.
- Add symbol-level return diagnostics to the `simple` engine so walk-forward contributor and hit-rate reports work on the canonical realistic engine.
- Pass quality/ROE through the 12_1 paper-signal path instead of silently ignoring it.
- Preserve value and quality weights in approved paper-trading parameters, including validation and resolution.
- Make the main backtest CLI's `--engine` flag actually select the requested engine.
- Update README so stale or unreproducible performance claims are labeled, and unfixable professional research gaps are documented.

## Out of Scope

These require external data, research policy, or a larger redesign and must be documented rather than locally "fixed":

- Full point-in-time historical constituents for TOPIX/Nikkei universes.
- Actual filing timestamps for fundamental data instead of fiscal-period-end plus an estimated delay.
- Independent vendor audit for adjusted prices, corporate actions, suspensions, delistings, and restatements.
- Live broker execution and real fill reconciliation.
- Institutional approval gates such as minimum OOS length, deflated Sharpe, multiple-testing controls, capacity/liquidity gates, and formal strategy retirement rules.
- A full asset-allocation research engine; the current asset-allocation notes remain exploratory.

## Design

### Research Parameter Flow

Add `top_n` to `evaluate_weight_tuple`, `run_walk_forward_optimization`, and the optimizer CLI. Every nested evaluator closure must accept and forward it. This directly addresses the known concentration flaw while preserving the default behavior of `top_n=3`.

### Simple Engine Accounting

Keep the `simple` engine as the realistic canonical path, but record portfolio equity on every trading day from the union calendar after each rebalance. Month-start trades still occur as before. Metrics are computed from the evaluation-window daily equity series, including a mark-to-market value at `evaluation_end`.

### Simple Engine Diagnostics

Track per-symbol realized and open P&L as a percentage of starting capital. Return `symbol_returns` in the same list-of-dicts shape expected by walk-forward diagnostics.

### Factor and Approval Consistency

The 12_1 paper-signal path must pass `weight_qual` and `roe_values` into `score_research_universe`. Approved paper-trading params should preserve any `weight_val` and `weight_qual` columns present in walk-forward weights and validate optional `val`/`qual` keys without requiring them for older artifacts.

### CLI Engine Dispatch

`src.main` should route non-logging engine runs through `src.engine.runner.run_backtest` when `--engine simple` or `--engine vectorbt` is requested. The existing Backtrader logging path can remain the default for order/trade log output when `--engine backtrader` is explicitly selected.

### Documentation

README should say which issues are locally repaired and which are not. It must not present legacy OOS numbers, current paper-trading configuration, or asset-allocation results as production-grade evidence without reproducible artifacts and fresh post-repair reruns.

## Testing Requirements

- Regression test for `top_n` propagation through `evaluate_weight_tuple` and `run_walk_forward_optimization`.
- Regression test showing `simple` engine includes evaluation-end mark-to-market performance beyond the last rebalance date.
- Regression test showing `simple` engine returns symbol-level diagnostics.
- Regression test showing 12_1 paper signals use ROE/quality.
- Regression test showing approved params preserve and resolve optional `val`/`qual`.
- Regression test showing `src.main --engine simple` uses the simple engine path.
- Full suite must pass with `uv run pytest -q` or equivalent project pytest command.
