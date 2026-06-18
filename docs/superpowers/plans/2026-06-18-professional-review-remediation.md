# Professional Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the locally repairable issues from the professional finance review and document the issues that require external data or broader research policy.

**Architecture:** Preserve the existing research stack and repair parameter/data flow defects in place. Make `simple` the more complete realistic engine by adding daily evaluation accounting and diagnostics, while keeping backward-compatible defaults.

**Tech Stack:** Python 3.12, pandas, pytest, Backtrader, vectorbt, local Parquet store, SQLite paper trading.

---

## File Map

| File | Role |
| --- | --- |
| `src/optimize.py` | Add and forward `top_n` through optimizer and evaluator closures. |
| `src/engine/simple_runner.py` | Add daily mark-to-market evaluation and symbol diagnostics. |
| `src/paper/bot.py` | Pass quality inputs through 12_1 paper scoring. |
| `src/research/approved_params.py` | Preserve optional value/quality approved weights. |
| `src/main.py` | Make `--engine simple|vectorbt` route through engine dispatch. |
| `README.md` | Document repaired and unrepaired professional limitations. |
| `tests/engine/test_simple_runner.py` | Regression tests for daily evaluation and diagnostics. |
| `tests/research/test_walk_forward.py` | Regression tests for `top_n` propagation. |
| `tests/scoring/test_multi_factor.py` | Regression test for 12_1 paper quality scoring. |
| `tests/research/test_approved_params.py` | Regression tests for optional `val`/`qual` approval. |
| `tests/test_main.py` or existing main test file | Regression test for CLI engine dispatch. |

## Task 1: Propagate `top_n` Through Optimizer

**Files:**
- Modify: `tests/research/test_walk_forward.py`
- Modify: `src/optimize.py`

- [ ] **Step 1: Write failing tests**
  Add tests that call `evaluate_weight_tuple(..., top_n=2, engine="simple")` and verify the returned scores mark two names as top-N. Add a run-walk-forward test that monkeypatches `evaluate_weight_tuple` and asserts every nested evaluator receives `top_n=2`.

- [ ] **Step 2: Run focused tests to verify RED**
  Run: `.venv/bin/pytest tests/research/test_walk_forward.py -q`
  Expected: FAIL because `top_n` is not accepted or not forwarded.

- [ ] **Step 3: Implement minimal propagation**
  Add `top_n: int = 3` to `evaluate_weight_tuple` and `run_walk_forward_optimization`. Forward it through all training, validation, baseline, and one-shot closures. Add `--top-n` to the optimizer CLI.

- [ ] **Step 4: Run focused tests**
  Run: `.venv/bin/pytest tests/research/test_walk_forward.py -q`
  Expected: PASS.

## Task 2: Improve Simple Engine Accounting and Diagnostics

**Files:**
- Modify: `tests/engine/test_simple_runner.py`
- Modify: `src/engine/simple_runner.py`

- [ ] **Step 1: Write failing tests**
  Add a test where the final evaluation date is after the last rebalance and the held stock changes price; assert `return_pct` includes that final mark-to-market move. Add a test with one winner and one loser that asserts `symbol_returns` is a non-empty list of `{symbol, return_pct}` rows.

- [ ] **Step 2: Run focused tests to verify RED**
  Run: `.venv/bin/pytest tests/engine/test_simple_runner.py -q`
  Expected: FAIL because the engine only records rebalance-day equity and returns empty symbol diagnostics.

- [ ] **Step 3: Implement daily valuation and P&L tracking**
  Track realized P&L when holdings are sold and mark open positions at evaluation end. Record portfolio equity on every trading day. Compute return, Sharpe, and drawdown from the evaluation daily equity series.

- [ ] **Step 4: Run focused tests**
  Run: `.venv/bin/pytest tests/engine/test_simple_runner.py -q`
  Expected: PASS.

## Task 3: Fix 12_1 Paper Quality Flow

**Files:**
- Modify: `tests/scoring/test_multi_factor.py`
- Modify: `src/paper/bot.py`

- [ ] **Step 1: Write failing test**
  Add a `calculate_current_signals(..., momentum_definition="12_1", weight_qual=1.0, roe_values=...)` test with flat price factors and different ROE values; assert the high-ROE symbol wins.

- [ ] **Step 2: Run focused test to verify RED**
  Run: `.venv/bin/pytest tests/scoring/test_multi_factor.py -q`
  Expected: FAIL because the 12_1 paper path ignores `weight_qual` and `roe_values`.

- [ ] **Step 3: Forward quality args**
  Pass `weight_qual` and `roe_values` into `score_research_universe` in `_build_signal_run`.

- [ ] **Step 4: Run focused tests**
  Run: `.venv/bin/pytest tests/scoring/test_multi_factor.py -q`
  Expected: PASS.

## Task 4: Preserve Optional Value and Quality Approved Weights

**Files:**
- Modify: `tests/research/test_approved_params.py`
- Modify: `src/research/approved_params.py`

- [ ] **Step 1: Write failing tests**
  Add a test where a weights CSV includes `weight_val` and `weight_qual`; assert approval writes `{"val": ..., "qual": ...}`. Add a resolver test showing `load_approved_paper_trading_params` accepts optional keys and `calculate_current_signals` can read them.

- [ ] **Step 2: Run focused tests to verify RED**
  Run: `.venv/bin/pytest tests/research/test_approved_params.py -q`
  Expected: FAIL because optional factor weights are dropped.

- [ ] **Step 3: Implement optional key preservation**
  Preserve `weight_val` and `weight_qual` when columns exist. Keep old artifacts compatible by requiring only mom/vol/rev.

- [ ] **Step 4: Run focused tests**
  Run: `.venv/bin/pytest tests/research/test_approved_params.py -q`
  Expected: PASS.

## Task 5: Make Main CLI Engine Dispatch Real

**Files:**
- Modify: a focused main CLI test file
- Modify: `src/main.py`

- [ ] **Step 1: Write failing test**
  Add a CLI test that invokes main with `--engine simple --no-plot`, monkeypatches `run_backtest`, and asserts it is called with `engine="simple"`.

- [ ] **Step 2: Run focused test to verify RED**
  Run the focused CLI test.
  Expected: FAIL because `main` currently calls `run_with_logging` regardless of `--engine`.

- [ ] **Step 3: Implement dispatch**
  Use `run_with_logging` only for Backtrader logging mode. For `simple` and `vectorbt`, call `src.engine.runner.run_backtest` and render the returned metrics.

- [ ] **Step 4: Run focused test**
  Run the focused CLI test.
  Expected: PASS.

## Task 6: README Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**
  Document locally repaired issues and remaining unfixable issues: PIT constituents, true filing timestamps, vendor data audit, full strategy lifecycle gates, and stale artifacts.

- [ ] **Step 2: Check docs text**
  Run: `git diff -- README.md`
  Expected: README no longer overclaims production-grade validity.

## Task 7: Full Verification and Branch Finish

**Files:**
- All touched files.

- [ ] **Step 1: Run full tests**
  Run: `.venv/bin/pytest -q`
  Expected: PASS.

- [ ] **Step 2: Run diff checks**
  Run: `git diff --check`
  Expected: PASS.

- [ ] **Step 3: Inspect final diff**
  Run: `git diff --stat`
  Expected: Changes match this plan.

- [ ] **Step 4: Commit implementation branch**
  Commit with message: `fix: remediate professional review findings`.

- [ ] **Step 5: Finish branch**
  Merge to main, remove the worktree, and delete the branch unless verification fails.
