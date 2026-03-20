# Backtrader Shared Scorer Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the Backtrader multi-factor strategy so its ranking decisions are produced through the shared pandas scoring module, giving research/backtest and paper trading the same scoring implementation.

**Architecture:** Add a small adapter layer inside the Backtrader strategy path that converts each rebalance date's visible historical bars into the `symbol -> DataFrame` format expected by `src/scoring/multi_factor.py`. The strategy should keep its current rebalance timing and portfolio management behavior, but replace its internal factor math and z-score logic with calls to the shared scorer. Tests should prove that the Backtrader adapter produces the same top-N ranking as the shared scorer and paper-trading path under the same weights.

**Tech Stack:** Python, pandas, backtrader, pytest

---

## File Structure

### New files

- `tests/strategies/test_multi_factor_parity.py`
  - Parity and adapter-focused tests proving the Backtrader strategy path uses the same ranking output as the shared scorer.

### Modified files

- `src/strategies/multi_factor.py`
  - Replace strategy-local factor math with a Backtrader-to-shared-scorer adapter and shared ranking call.
- `tests/strategies/test_multi_factor.py`
  - Expand beyond init-only coverage where useful for local adapter behavior.
- `tests/scoring/test_multi_factor.py`
  - Add any cross-checks needed to compare shared scorer output against the strategy adapter output.
- `README.md`
  - Update milestone wording if this change materially improves the “shared scoring logic” claim.

## Task 1: Add Adapter Snapshot Tests

**Files:**
- Create: `tests/strategies/test_multi_factor_parity.py`
- Modify: `src/strategies/multi_factor.py`

- [ ] **Step 1: Write the failing tests**

Add tests for a helper that extracts the currently visible price history from Backtrader datas into pandas DataFrames.

```python
def test_collect_visible_history_returns_symbol_dataframes():
    ...
    history = strategy._collect_visible_history()
    assert set(history) == {"AAA.T", "BBB.T"}
    assert list(history["AAA.T"].columns) == ["Close"]
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/strategies/test_multi_factor_parity.py -v`
Expected: FAIL because the adapter helper does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Implement a helper in `src/strategies/multi_factor.py` that:

- reads visible bars only up to the current Backtrader index
- creates a per-symbol DataFrame with at least `Close`
- skips datas without enough visible rows

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/strategies/test_multi_factor_parity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/strategies/test_multi_factor_parity.py src/strategies/multi_factor.py
git commit -m "test: add Backtrader history adapter coverage"
```

## Task 2: Add Shared-Scorer Parity Tests

**Files:**
- Modify: `tests/strategies/test_multi_factor_parity.py`
- Modify: `src/strategies/multi_factor.py`

- [ ] **Step 1: Write the failing tests**

Add a test that compares the strategy adapter's ranking output against `score_universe` on the same synthetic dataset and weights.

```python
from src.scoring.multi_factor import score_universe


def test_strategy_adapter_ranking_matches_shared_scorer():
    ...
    ranked = strategy._score_visible_universe()
    expected = score_universe(data, top_n=2, weight_mom=..., weight_vol=..., weight_rev=...)
    assert ranked["symbol"].tolist() == expected["symbol"].tolist()
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/strategies/test_multi_factor_parity.py -v`
Expected: FAIL because the strategy still uses its own internal factor math path.

- [ ] **Step 3: Write the minimal implementation**

Implement a scoring helper in `src/strategies/multi_factor.py` that:

- collects visible history
- calls `src.scoring.multi_factor.score_universe`
- returns ranked results for the current rebalance date

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/strategies/test_multi_factor_parity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/strategies/test_multi_factor_parity.py src/strategies/multi_factor.py
git commit -m "feat: route strategy ranking through shared scorer adapter"
```

## Task 3: Replace Strategy Rebalance Ranking Logic

**Files:**
- Modify: `src/strategies/multi_factor.py`
- Modify: `tests/strategies/test_multi_factor.py`
- Modify: `tests/strategies/test_multi_factor_parity.py`

- [ ] **Step 1: Write the failing tests**

Add a test that confirms `rebalance()` selects the same top symbols as the shared scorer and still issues target allocations for winners only.

```python
def test_rebalance_uses_shared_ranked_top_n():
    ...
    strategy.rebalance()
    assert captured_targets == {"AAA.T", "CCC.T"}
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/strategies/test_multi_factor.py tests/strategies/test_multi_factor_parity.py -v`
Expected: FAIL because rebalance still uses the old local ranking path.

- [ ] **Step 3: Write the minimal implementation**

Update `rebalance()` so it:

- uses the shared ranked DataFrame instead of local indicator/z-score math
- maps ranked symbols back to Backtrader datas
- preserves the current liquidation and target-weight logic

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/strategies/test_multi_factor.py tests/strategies/test_multi_factor_parity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/strategies/multi_factor.py tests/strategies/test_multi_factor.py tests/strategies/test_multi_factor_parity.py
git commit -m "refactor: use shared scorer in Backtrader rebalance"
```

## Task 4: Add End-to-End Research/Paper Parity Coverage

**Files:**
- Modify: `tests/strategies/test_multi_factor_parity.py`
- Modify: `tests/scoring/test_multi_factor.py`

- [ ] **Step 1: Write the failing tests**

Add an end-to-end parity test showing:

- shared scorer output
- strategy adapter ranking output
- paper-trading ranking output

all match under the same input data and weights or approved params.

```python
def test_shared_strategy_and_paper_paths_match_under_same_weights():
    ...
    assert strategy_ranked["symbol"].tolist() == shared["symbol"].tolist()
    assert paper["symbol"].tolist() == shared.head(2)["symbol"].tolist()
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/strategies/test_multi_factor_parity.py tests/scoring/test_multi_factor.py -v`
Expected: FAIL until the strategy and paper paths are aligned through the shared scorer.

- [ ] **Step 3: Write the minimal implementation**

Adjust any remaining helper seams so the test can compare all three paths without duplicating logic.

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/strategies/test_multi_factor_parity.py tests/scoring/test_multi_factor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/strategies/test_multi_factor_parity.py tests/scoring/test_multi_factor.py src/strategies/multi_factor.py
git commit -m "test: add research and paper ranking parity coverage"
```

## Task 5: Update Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write the documentation changes**

Update milestone wording to reflect that:

- paper and Backtrader ranking logic now share the same scorer
- remaining Milestone 4 work focuses on parameter-source governance and broader end-to-end confidence

- [ ] **Step 2: Review for clarity**

Check:

- the README does not overclaim full end-to-end parity beyond what tests prove
- milestone status wording still matches reality

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update parity milestone status"
```

## Task 6: Run Verification

**Files:**
- No additional files unless failures are found.

- [ ] **Step 1: Run focused test suites**

Run: `pytest tests/strategies/test_multi_factor.py tests/strategies/test_multi_factor_parity.py tests/scoring/test_multi_factor.py -v`
Expected: PASS

- [ ] **Step 2: Run the broader suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 3: Run a manual smoke backtest**

Run:

```bash
uv run python -m src.main --strategy multi --universe --no-plot
```

Expected:

- backtest completes
- no strategy ranking exceptions occur
- output remains compatible with the existing CLI path

- [ ] **Step 4: Summarize follow-up work**

Capture any intentionally deferred items:

- pushing approved params all the way through backtest CLI defaults
- richer explainability outputs from the shared ranked DataFrame
- further cleanup of any leftover strategy-local ranking helpers
