# Milestone 5 Turnover And Risk Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add double-threshold turnover controls and basic turnover metrics to the multi-factor backtest path without breaking the existing default strategy behavior.

**Architecture:** Keep ranking logic unchanged in the shared scorer and apply turnover controls only inside the rebalance layer of the Backtrader strategy. Track simple turnover counters on the strategy, expose them through the backtest runner, and surface the controls and metrics in the CLI so buffered and unbuffered runs can be compared directly.

**Tech Stack:** Python, Backtrader, pandas, pytest, existing CLI/backtest helpers

---

## File Structure

### Existing files to modify

- `src/strategies/multi_factor.py`
  Responsibility: multi-factor rebalance logic, turnover-control parameters, and turnover counters.
- `tests/strategies/test_multi_factor_parity.py`
  Responsibility: shared-scorer parity and rebalance behavior coverage for the strategy adapter.
- `src/main.py`
  Responsibility: backtest CLI argument parsing and result reporting.
- `tests/research/test_backtest_defaults.py`
  Responsibility: backtest parameter resolution coverage for the multi-factor path.

### Existing files that may need targeted edits

- `src/engine/runner.py`
  Responsibility: if we need a reusable backtest metrics hook outside the CLI, keep turnover metrics flow consistent here too.

### New files to create

- `tests/strategies/test_multi_factor_turnover.py`
  Responsibility: focused behavior tests for buy/sell thresholds and turnover counters without overloading the parity suite.

### Boundaries

- Do not change factor formulas or the shared scorer contract.
- Apply rank-buffer rules after ranking has already been computed.
- Preserve default behavior exactly when no threshold controls are supplied.
- Keep turnover metrics simple, deterministic, and testable.

## Task 1: Add Buffered Rebalance Rules

**Files:**
- Modify: `src/strategies/multi_factor.py`
- Modify: `tests/strategies/test_multi_factor_parity.py`
- Create: `tests/strategies/test_multi_factor_turnover.py`

- [ ] **Step 1: Write the failing strategy behavior tests**

Add tests covering:

- default strategy settings still buy the same top-`N` names as today
- an existing holding remains when it is still within `sell_rank_threshold`
- an existing holding exits when it falls below `sell_rank_threshold`
- a non-held symbol inside the keep zone but outside `buy_rank_threshold` is not newly bought
- final target holdings stay bounded by `top_n`

- [ ] **Step 2: Run strategy tests to verify RED**

Run: `uv run --with pytest pytest tests/strategies/test_multi_factor_parity.py tests/strategies/test_multi_factor_turnover.py -q`
Expected: FAIL because the strategy does not yet support buy/sell threshold buffering.

- [ ] **Step 3: Write the minimal buffered rebalance implementation**

Update `src/strategies/multi_factor.py` to:

- add `buy_rank_threshold` and `sell_rank_threshold` params
- derive default thresholds from `top_n` so existing behavior is preserved
- compute the ranked universe once per rebalance
- keep existing holdings whose rank is within `sell_rank_threshold`
- allow new entries only from non-held symbols within `buy_rank_threshold`
- build the final target set with capacity bounded by `top_n`

- [ ] **Step 4: Run strategy tests to verify GREEN**

Run: `uv run --with pytest pytest tests/strategies/test_multi_factor_parity.py tests/strategies/test_multi_factor_turnover.py -q`
Expected: PASS.

- [ ] **Step 5: Run scorer-adjacent regression coverage**

Run: `uv run --with pytest pytest tests/scoring/test_multi_factor.py tests/strategies/test_multi_factor_parity.py tests/strategies/test_multi_factor_turnover.py -q`
Expected: PASS.

- [ ] **Step 6: Commit phase 1**

```bash
git add src/strategies/multi_factor.py tests/strategies/test_multi_factor_parity.py tests/strategies/test_multi_factor_turnover.py
git commit -m "feat(strategy): add buffered rebalance thresholds"
```

## Task 2: Add Turnover Metrics

**Files:**
- Modify: `src/strategies/multi_factor.py`
- Modify: `tests/strategies/test_multi_factor_turnover.py`
- Modify: `src/engine/runner.py`

- [ ] **Step 1: Write the failing turnover metric tests**

Add tests covering:

- `rebalance_count` increments deterministically across rebalances
- `position_change_count` reflects buys and sells emitted by the buffered strategy
- buffered settings produce lower turnover than default settings on a churn-heavy fixture
- runner-level metrics include a turnover field when using the strategy

- [ ] **Step 2: Run turnover tests to verify RED**

Run: `uv run --with pytest pytest tests/strategies/test_multi_factor_turnover.py -q`
Expected: FAIL because turnover counters and summaries are not yet exposed.

- [ ] **Step 3: Write the minimal turnover metric implementation**

Update strategy and runner code to:

- track `rebalance_count`
- track `position_change_count`
- expose a simple `turnover_ratio`
- include these values in the backtest metrics payload in a deterministic way

- [ ] **Step 4: Run turnover tests to verify GREEN**

Run: `uv run --with pytest pytest tests/strategies/test_multi_factor_turnover.py -q`
Expected: PASS.

- [ ] **Step 5: Run broader backtest regression coverage**

Run: `uv run --with pytest pytest tests/strategies/test_multi_factor_parity.py tests/strategies/test_multi_factor_turnover.py tests/research/test_backtest_defaults.py -q`
Expected: PASS.

- [ ] **Step 6: Commit phase 2**

```bash
git add src/strategies/multi_factor.py src/engine/runner.py tests/strategies/test_multi_factor_turnover.py
git commit -m "feat(strategy): track turnover metrics"
```

## Task 3: Surface Controls And Metrics In The CLI

**Files:**
- Modify: `src/main.py`
- Modify: `tests/research/test_backtest_defaults.py`
- Modify: `tests/strategies/test_multi_factor_turnover.py`

- [ ] **Step 1: Write the failing CLI/reporting tests**

Add tests covering:

- CLI argument resolution for `buy_rank_threshold` and `sell_rank_threshold`
- default CLI path still resolves approved factor weights correctly
- backtest output/reporting includes turnover metrics for multi-factor runs

- [ ] **Step 2: Run CLI/reporting tests to verify RED**

Run: `uv run --with pytest pytest tests/research/test_backtest_defaults.py tests/strategies/test_multi_factor_turnover.py -q`
Expected: FAIL because the CLI does not yet accept or report turnover-control settings.

- [ ] **Step 3: Write the minimal CLI/reporting implementation**

Update `src/main.py` to:

- accept `--buy-rank-threshold`
- accept `--sell-rank-threshold`
- pass them into the multi-factor strategy kwargs
- print turnover metrics in backtest results for the multi-factor path

Keep existing weight resolution behavior intact.

- [ ] **Step 4: Run CLI/reporting tests to verify GREEN**

Run: `uv run --with pytest pytest tests/research/test_backtest_defaults.py tests/strategies/test_multi_factor_turnover.py -q`
Expected: PASS.

- [ ] **Step 5: Run the complete milestone-adjacent test set**

Run: `uv run --with pytest pytest tests/scoring/test_multi_factor.py tests/strategies/test_multi_factor_parity.py tests/strategies/test_multi_factor_turnover.py tests/research/test_backtest_defaults.py tests/research/test_artifacts.py tests/research/test_approved_params.py tests/research/test_walk_forward.py -q`
Expected: PASS.

- [ ] **Step 6: Commit phase 3**

```bash
git add src/main.py tests/research/test_backtest_defaults.py tests/strategies/test_multi_factor_turnover.py
git commit -m "feat(cli): expose turnover control settings"
```

## Final Verification

- [ ] **Step 1: Run the full Milestone 5 regression set**

Run: `uv run --with pytest pytest tests/scoring/test_multi_factor.py tests/strategies/test_multi_factor_parity.py tests/strategies/test_multi_factor_turnover.py tests/research/test_backtest_defaults.py tests/research/test_artifacts.py tests/research/test_approved_params.py tests/research/test_walk_forward.py -q`
Expected: PASS.

- [ ] **Step 2: Review git status**

Run: `git status --short`
Expected: clean working tree.

- [ ] **Step 3: Prepare branch completion**

Use `superpowers:finishing-a-development-branch` after implementation is complete and verification is green.

## Notes For Execution

- Do not begin implementation on `main`; create an isolated worktree/branch first.
- Follow TDD strictly: each production change must be preceded by a failing test.
- Keep each phase independently shippable and commit immediately after its tests pass.
- If the turnover metric definition needs a small adjustment for determinism, keep it simple and document it in tests rather than introducing finance-heavy formulas.
