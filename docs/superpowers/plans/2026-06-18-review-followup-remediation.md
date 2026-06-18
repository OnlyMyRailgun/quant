# Review Follow-up Remediation Implementation Plan

> **For agentic workers:** AGENTS requires Superpowers skills for this workflow. If those skills are unavailable in the runtime, follow the same sequence manually: spec, plan, failing tests, implementation, verification, branch finish.

**Goal:** Fix true, unrepaired issues from the two professional reviews that can be repaired locally, and document the remaining true methodology limitations.

## Task 1: Compound Walk-forward Returns

**Files:**
- `tests/research/test_walk_forward.py`
- `src/research/walk_forward.py`

- [ ] Add a failing test with +10% then -10% validation windows and verify summary total is -1%, not 0%.
- [ ] Add active/excess assertions so baseline and benchmark totals compound before subtraction.
- [ ] Implement a compounding helper and replace additive summary totals.
- [ ] Run focused walk-forward tests.

## Task 2: Remove Backtrader Look-ahead

**Files:**
- `tests/strategies/test_multi_factor_parity.py` or `tests/research/test_walk_forward.py`
- `src/strategies/multi_factor.py`

- [ ] Add a failing test proving current-bar close is excluded from visible scoring history.
- [ ] Update `_collect_visible_history()` to drop the current bar.
- [ ] Verify Backtrader scoring still works with normal warmup data.

## Task 3: Preserve Five-factor Qual Weights

**Files:**
- `tests/research/test_walk_forward.py`
- `src/research/walk_forward.py`
- `src/optimize.py`

- [ ] Add tests showing `select_best_weights()` and Optuna mapping preserve a fifth `qual` weight.
- [ ] Add a run-walk-forward test showing validation and one-shot evaluation receive a 5-element tuple.
- [ ] Add `roe_values` forwarding where needed and grep all call sites for signature changes.
- [ ] Persist `weight_qual` in weight rows when present.

## Task 4: Use Actual Trading Calendar in Vectorbt

**Files:**
- `tests/engine/test_vectorbt_runner.py`
- `src/engine/vectorbt_runner.py`

- [ ] Add a failing test where calendar BMS is absent from the data index but the first actual trading day exists.
- [ ] Generate execution dates from observed first trading days.
- [ ] Verify orders are placed on actual index dates.

## Task 5: Reduce Default Concentration and Avoid Contradictory Default Grids

**Files:**
- `tests/research/test_walk_forward.py`
- `tests/research/test_backtest_defaults.py`
- `tests/paper/test_bot.py`
- `src/optimize.py`
- `src/main.py`
- `src/paper/bot.py`
- `src/strategies/multi_factor.py`

- [ ] Add tests proving default optimizer grid excludes positive momentum plus positive mean-reversion tuples.
- [ ] Add tests proving explicit custom grids can still include those tuples.
- [ ] Change default research `top_n` to 10 for strategy, optimizer CLI, main dispatch, and paper signal generation.
- [ ] Keep explicit `top_n` overrides working.

## Task 6: README Methodology Limits

**Files:**
- `README.md`

- [ ] Document which review points remain methodology/data limitations.
- [ ] Mark legacy additive walk-forward artifacts as stale.
- [ ] State default `top_n=10` and the reason for avoiding `mom+rev` default grids.

## Task 7: Verification and Branch Finish

- [ ] Run focused tests for changed areas.
- [ ] Run full suite with network approval if yfinance test requires it.
- [ ] Run `git diff --check`.
- [ ] Commit implementation branch.
- [ ] Merge back to `main`, remove worktree, delete branch.
