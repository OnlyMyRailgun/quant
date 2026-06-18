# Professionalization Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Subagent-driven development is intentionally not used because the available subagent tool is restricted to explicit user-requested delegation.

**Goal:** Fix the locally repairable finance-professionalism defects identified in the repository review and leave the remaining external-data gaps explicitly documented.

**Architecture:** Keep `simple` as the canonical realistic backtest engine, but make its evaluation window accounting correct and test-backed. Repair paper trading execution assumptions in place with small helper functions. Avoid pretending external point-in-time data problems are solved locally.

**Tech Stack:** Python 3.12, pandas, pytest, vectorbt, Backtrader, SQLite paper-trading database.

---

### Task 1: Restore Test Baseline

**Files:**
- Modify: `tests/paper/test_bot.py`

- [ ] **Step 1: Write the failing test/update**

Change the filled-order fixture so "this month" is generated from `pd.Timestamp.today()` rather than a hard-coded `2026-04-27`.

- [ ] **Step 2: Run test to verify current failure**

Run: `uv run pytest tests/paper/test_bot.py::test_monthly_guard_skips_when_already_rebalanced_this_month -q`
Expected before fix: FAIL because the hard-coded date is not in the current month.

- [ ] **Step 3: Implement minimal test-fixture fix**

Use `pd.Timestamp.today().strftime("%Y-%m-%d")` for the inserted filled-order date when `with_filled_orders=True`.

- [ ] **Step 4: Run focused test**

Run: `uv run pytest tests/paper/test_bot.py::test_monthly_guard_skips_when_already_rebalanced_this_month -q`
Expected: PASS.

### Task 2: Correct Simple Engine Evaluation Window

**Files:**
- Modify: `tests/engine/test_simple_runner.py` or create it if absent
- Modify: `src/engine/simple_runner.py`

- [ ] **Step 1: Write failing regression test**

Create a test where `start` includes a warmup/trading month before `evaluation_start`; the first evaluation value is intentionally different from `initial_cash`. Assert `return_pct` uses first evaluation equity as denominator.

- [ ] **Step 2: Run focused test to verify RED**

Run: `uv run pytest tests/engine/test_simple_runner.py -q`
Expected: FAIL under current denominator behavior.

- [ ] **Step 3: Implement minimal accounting fix**

Compute `total_return = (vals.iloc[-1] / vals.iloc[0] - 1) * 100` for evaluation windows. Keep drawdown and Sharpe based on `vals`.

- [ ] **Step 4: Run focused test to verify GREEN**

Run: `uv run pytest tests/engine/test_simple_runner.py -q`
Expected: PASS.

### Task 3: Repair Paper Trading Execution Assumptions

**Files:**
- Modify: `tests/paper/test_bot.py`
- Modify: `src/paper/bot.py`

- [ ] **Step 1: Write failing tests**

Add tests that generated buy quantities are rounded down to 100-share lots and that auto-fill applies adverse slippage: buy price = theoretical * (1 + slippage), sell price = theoretical * (1 - slippage).

- [ ] **Step 2: Run focused paper tests to verify RED**

Run: `uv run pytest tests/paper/test_bot.py -q`
Expected: new tests fail against current one-share sizing and buy price minus slippage.

- [ ] **Step 3: Implement helpers and wire them in**

Add small helpers in `src/paper/bot.py` for lot sizing and side-aware slippage. Use them from `generate_rebalance_orders`.

- [ ] **Step 4: Run focused paper tests**

Run: `uv run pytest tests/paper/test_bot.py -q`
Expected: PASS.

### Task 4: Implement Research Quality Factor

**Files:**
- Modify: `tests/research/test_research_scoring.py`
- Modify: `src/research/research_scoring.py`

- [ ] **Step 1: Write failing quality-factor test**

Add a test with equal momentum/vol/reversal values and different `roe_values`, asserting `qual_z`, `qual_contribution`, and ranking reflect higher quality when `weight_qual > 0`.

- [ ] **Step 2: Run focused test to verify RED**

Run: `uv run pytest tests/research/test_research_scoring.py -q`
Expected: FAIL because quality is currently ignored.

- [ ] **Step 3: Implement quality scoring**

Mirror `score_universe` quality handling: collect raw quality values, z-score high-is-better, add contribution and total score.

- [ ] **Step 4: Run focused scoring tests**

Run: `uv run pytest tests/research/test_research_scoring.py -q`
Expected: PASS.

### Task 5: Make Vectorbt Slippage Honest

**Files:**
- Modify: `tests/engine/test_vectorbt_runner.py`
- Modify: `src/engine/vectorbt_runner.py`

- [ ] **Step 1: Write failing test**

Add a test that `slippage_pct > 0` is not silently ignored. Preferred assertion: the runner raises `NotImplementedError` explaining that target-percent vectorbt slippage is unsupported in this path.

- [ ] **Step 2: Run focused test to verify RED**

Run: `uv run pytest tests/engine/test_vectorbt_runner.py -q`
Expected: FAIL because non-zero slippage is accepted silently.

- [ ] **Step 3: Implement explicit rejection**

Raise `NotImplementedError` for non-zero `slippage_pct` in `run_backtest_vectorbt` until a side-aware vectorbt order path is implemented. Update `evaluate_weight_tuple(engine="vectorbt")` to pass `slippage_pct=0.0`.

- [ ] **Step 4: Run focused vectorbt tests**

Run: `uv run pytest tests/engine/test_vectorbt_runner.py -q`
Expected: PASS.

### Task 6: Documentation and Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Remove the stale "211 passing, zero regressions" claim and clarify what is fixed versus still limited by external data.

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 3: Inspect git diff**

Run: `git diff --stat` and `git diff --check`
Expected: no whitespace errors; changes match this plan.

- [ ] **Step 4: Commit implementation branch**

Commit focused changes with a message such as `fix: repair financial backtest and paper execution assumptions`.
