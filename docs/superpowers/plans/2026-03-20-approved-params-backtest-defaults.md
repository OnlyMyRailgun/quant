# Approved Params Backtest Defaults Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Backtrader backtest CLI load approved walk-forward parameters by default for the multi-factor strategy, so paper trading and backtesting share the same default parameter source.

**Architecture:** Keep explicit CLI weights as overrides, but add a small parameter-resolution layer in the backtest path that loads `.research_artifacts/paper_trade_params.json` when the multi-factor strategy is run without intentional overrides. This should mirror the paper-trading default-resolution behavior and add tests proving that backtest and paper paths consume the same approved parameter source under default configuration.

**Tech Stack:** Python, pathlib, json, pytest, backtrader

---

## File Structure

### New files

- `tests/research/test_backtest_defaults.py`
  - Tests for approved-parameter resolution in the backtest CLI path and default-source parity with paper trading.

### Modified files

- `src/main.py`
  - Add approved-params loading for the multi-factor strategy default path while preserving explicit CLI overrides.
- `src/research/approved_params.py`
  - Add any small helper needed to resolve approved weights for both paper and backtest consumers without duplication.
- `src/paper/bot.py`
  - Reuse any shared resolution helper if the new implementation warrants it.
- `README.md`
  - Update Milestone 4 wording if the shared approved-parameter source is now the default in both paper and backtest paths.

## Task 1: Add Backtest Default Resolution Tests

**Files:**
- Create: `tests/research/test_backtest_defaults.py`
- Modify: `src/main.py`

- [ ] **Step 1: Write the failing tests**

Add tests for a helper such as `resolve_multi_factor_weights` that:

- loads approved params when no explicit weights are provided
- preserves explicit weights when they are intentionally set

```python
def test_resolve_multi_factor_weights_uses_approved_params_when_cli_uses_defaults(tmp_path: Path):
    ...
    weights = resolve_multi_factor_weights(
        artifact_dir=tmp_path,
        weight_mom=1.0,
        weight_vol=1.0,
        weight_rev=1.0,
        explicit_override=False,
    )
    assert weights == {"weight_mom": 0.5, "weight_vol": 1.0, "weight_rev": 0.5}
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/research/test_backtest_defaults.py -v`
Expected: FAIL because the helper does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Implement a helper that:

- reads approved params from `.research_artifacts/`
- returns strategy kwargs for the multi-factor strategy
- distinguishes between default CLI values and explicit user overrides

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/research/test_backtest_defaults.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/research/test_backtest_defaults.py src/main.py
git commit -m "feat: resolve backtest defaults from approved params"
```

## Task 2: Share Resolution Logic Between Paper and Backtest

**Files:**
- Modify: `src/research/approved_params.py`
- Modify: `src/paper/bot.py`
- Modify: `src/main.py`
- Modify: `tests/research/test_backtest_defaults.py`

- [ ] **Step 1: Write the failing tests**

Add a test proving both consumers resolve the same approved weights from the same artifact directory.

```python
def test_backtest_and_paper_resolve_same_approved_weights(tmp_path: Path):
    ...
    assert backtest_weights == {"weight_mom": 0.0, "weight_vol": 1.0, "weight_rev": 0.5}
    assert paper_weights == (0.0, 1.0, 0.5)
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/research/test_backtest_defaults.py tests/scoring/test_multi_factor.py -v`
Expected: FAIL because the resolution logic is still duplicated or incomplete.

- [ ] **Step 3: Write the minimal implementation**

Add or reuse a shared helper in `src/research/approved_params.py` so:

- paper trading and backtesting both read approved params through the same source logic
- backtesting gets strategy kwargs
- paper trading keeps its current tuple-style resolution behavior

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/research/test_backtest_defaults.py tests/scoring/test_multi_factor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/research/approved_params.py src/paper/bot.py src/main.py tests/research/test_backtest_defaults.py tests/scoring/test_multi_factor.py
git commit -m "refactor: share approved param resolution across backtest and paper"
```

## Task 3: Wire the CLI Path

**Files:**
- Modify: `src/main.py`
- Modify: `tests/research/test_backtest_defaults.py`

- [ ] **Step 1: Write the failing tests**

Add coverage that the multi-factor CLI kwargs path uses approved params only when explicit overrides were not supplied.

```python
def test_build_multi_strategy_kwargs_respects_explicit_cli_overrides(tmp_path: Path):
    ...
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/research/test_backtest_defaults.py -v`
Expected: FAIL because `main.py` still hardcodes the raw argparse values.

- [ ] **Step 3: Write the minimal implementation**

Update `src/main.py` so that:

- default multi-factor runs read approved params automatically
- explicit CLI values still win
- non-multi strategies are unaffected

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `pytest tests/research/test_backtest_defaults.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/research/test_backtest_defaults.py
git commit -m "feat: use approved params as backtest defaults"
```

## Task 4: Update Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write the documentation changes**

Update Milestone 4 to reflect that:

- paper trading and multi-factor backtesting now share the same default approved-params source
- explicit CLI weights are still available as overrides

- [ ] **Step 2: Review for clarity**

Check:

- README does not imply every research path auto-loads approved params if that is not true
- wording stays precise about “default source” versus “mandatory source”

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update default approved params behavior"
```

## Task 5: Run Verification

**Files:**
- No additional files unless failures are found.

- [ ] **Step 1: Run focused test suites**

Run: `pytest tests/research/test_backtest_defaults.py tests/scoring/test_multi_factor.py tests/strategies/test_multi_factor_parity.py -v`
Expected: PASS

- [ ] **Step 2: Run the broader suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 3: Run manual smoke checks**

Run:

```bash
uv run python -m src.optimize
uv run python -m src.main --strategy multi --universe --no-plot
```

Expected:

- walk-forward artifacts can still be generated
- approved params can still be produced from those artifacts
- backtest CLI completes using the approved params default path unless explicit weights are supplied

- [ ] **Step 4: Summarize follow-up work**

Capture any intentionally deferred items:

- exposing approval actions as a formal CLI
- applying approved params to more research entry points
- adding regression fixtures for specific approved-params snapshots
