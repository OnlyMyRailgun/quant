# Universe Screening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a phase-1 universe-screening workflow that can turn a broader named candidate universe into an eligible research universe using point-in-time price/liquidity/history hard rules, persist the screening decision, and apply it in the main backtest entry point.

**Architecture:** Introduce a dedicated screening module in the research layer so loaders keep fetching raw data, screeners decide eligibility, and scorers continue to rank only eligible symbols. Scope this slice to one-shot backtest/research usage in `src/main.py`, plus screening artifacts and diagnostics, while deliberately leaving walk-forward per-window screening and paper-trading integration for later work.

**Tech Stack:** Python, pandas, pytest, existing market-data loader, existing research artifact helpers

---

## File Structure

### Existing files to modify

- `src/main.py`
  Responsibility: optionally run the new screening flow before backtests that use broader universes, print a compact screening summary, and persist a screening artifact when enabled.
- `src/research/artifacts.py`
  Responsibility: add a dedicated screening artifact writer plus small metadata/summary helpers that match the existing artifact conventions.
- `tests/research/test_artifacts.py`
  Responsibility: cover screening artifact persistence.
- `tests/research/test_backtest_defaults.py`
  Responsibility: cover `src.main` integration, including filtering the loaded universe down to eligible symbols and preserving current defaults when screening is not used.

### New files to create

- `src/research/screening.py`
  Responsibility: define phase-1 screening rules, symbol-level screening records, aggregate summary helpers, and the point-in-time screening function.
- `tests/research/test_screening.py`
  Responsibility: focused regression coverage for rule evaluation, rejection reasons, point-in-time truncation, and summary aggregation.

### Existing files to inspect but not necessarily modify

- `src/data/bulk_loader.py`
  Responsibility: stays focused on fetching/caching market data; do not move eligibility decisions into the loader.
- `src/scoring/multi_factor.py`
  Responsibility: should remain unchanged in behavior except that callers may hand it a smaller eligible universe.

### Boundaries

- Do not integrate screening into `src/optimize.py` in this slice, because phase 1 explicitly defers walk-forward per-window screening.
- Do not integrate screening into `src/paper/bot.py` in this slice.
- Do not add `PB` / `PE` data fetching or fundamentals providers in this slice.
- Do not infer future information by screening against the full backtest range when `screen_as_of` is earlier; all symbol metrics must be computed using data truncated at `screen_as_of`.

## Task 1: Add Point-in-Time Screening Core

**Files:**
- Create: `src/research/screening.py`
- Create: `tests/research/test_screening.py`

- [ ] **Step 1: Write the failing screening-core tests**

Add focused tests in `tests/research/test_screening.py` covering:

- a symbol that passes all hard rules
- a symbol rejected for insufficient history
- a symbol rejected for high missing ratio
- a symbol rejected for low latest close
- a symbol rejected for weak recent trading activity
- a symbol rejected for multiple reasons at once
- summary aggregation of requested, eligible, screened-out, and reason-level counts

Use tiny deterministic pandas frames so the expected counts are obvious.

- [ ] **Step 2: Run the focused screening-core tests to verify RED**

Run: `uv run pytest -q tests/research/test_screening.py::test_screen_universe_accepts_symbol_that_meets_phase1_rules tests/research/test_screening.py::test_screen_universe_rejects_symbol_with_multiple_reasons`

Expected: FAIL because `src/research/screening.py` does not exist yet.

- [ ] **Step 3: Write the minimal screening implementation**

Create `src/research/screening.py` with:

- a `ScreeningRules` dataclass containing conservative default thresholds
- a symbol-level screening record shape
- helper(s) that compute:
  - `history_days`
  - `missing_ratio`
  - `latest_close`
  - `recent_trading_day_ratio`
  - `recent_inactive_day_ratio`
- a `screen_universe(...)` function that:
  - accepts `candidate_symbols`, `data_dfs`, `start`, `end`, `screen_as_of`, and `screening_rules`
  - truncates every symbol frame to `<= screen_as_of` before evaluating metrics
  - returns `eligible_symbols`, `rejected_symbols`, `by_symbol`, and `summary`
  - emits stable machine-readable rejection reasons

Implementation constraints:

- if a requested symbol is missing from `data_dfs`, it must still appear in `by_symbol` as rejected
- default thresholds should be conservative enough that current small-universe tests can easily opt out or pass explicitly
- keep the API fundamentals-free for phase 1

- [ ] **Step 4: Run the focused screening-core tests to verify GREEN**

Run: `uv run pytest -q tests/research/test_screening.py::test_screen_universe_accepts_symbol_that_meets_phase1_rules tests/research/test_screening.py::test_screen_universe_rejects_symbol_with_multiple_reasons`

Expected: PASS.

## Task 2: Lock In Point-in-Time Behavior and Summary Shape

**Files:**
- Modify: `tests/research/test_screening.py`
- Modify: `src/research/screening.py`

- [ ] **Step 1: Write the failing point-in-time tests**

Extend `tests/research/test_screening.py` with coverage that proves:

- screening ignores rows after `screen_as_of`
- `latest_close` uses the last price at or before `screen_as_of`
- recent-activity metrics are computed from the truncated frame, not the full frame
- summary keys are stable and reason-level counts stay machine-readable

- [ ] **Step 2: Run the point-in-time tests to verify RED**

Run: `uv run pytest -q tests/research/test_screening.py::test_screen_universe_truncates_metrics_at_screen_as_of tests/research/test_screening.py::test_screen_universe_summary_counts_rejection_reasons`

Expected: FAIL until truncation and reason-count behavior are correct.

- [ ] **Step 3: Tighten the implementation**

Update `src/research/screening.py` so:

- every metric is computed only from the point-in-time-truncated slice
- summary generation includes:
  - `requested_symbol_count`
  - `eligible_symbol_count`
  - `screened_out_symbol_count`
  - `eligibility_ratio`
  - `screened_out_<reason>_count` keys for each seen reason
- output ordering is stable enough for deterministic tests

- [ ] **Step 4: Run the screening test file**

Run: `uv run pytest -q tests/research/test_screening.py`

Expected: PASS.

## Task 3: Add Screening Artifact Persistence

**Files:**
- Modify: `src/research/artifacts.py`
- Modify: `tests/research/test_artifacts.py`

- [ ] **Step 1: Write the failing artifact tests**

Extend `tests/research/test_artifacts.py` with dedicated coverage for a screening artifact writer that:

- writes metadata JSON
- writes per-symbol decisions as CSV
- writes summary JSON
- records the run in the existing registry JSONL

Also add focused expectations for screening metadata such as:

- `universe_name`
- `screen_as_of`
- serialized screening thresholds

- [ ] **Step 2: Run the focused artifact tests to verify RED**

Run: `uv run pytest -q tests/research/test_artifacts.py::test_write_screening_run_persists_decisions_and_summary`

Expected: FAIL because no screening artifact writer exists yet.

- [ ] **Step 3: Write the minimal artifact implementation**

Update `src/research/artifacts.py` to add:

- `build_screening_metadata(...)`
- `build_screening_summary(...)` if helpful, or keep summary construction in screening and only persist it here
- `write_screening_run(...)`

Artifact shape should mirror existing research conventions:

- run directory under `.research_artifacts/universe_screening/...`
- `metadata.json`
- `decisions.csv`
- `summary.json`

- [ ] **Step 4: Run the focused artifact tests to verify GREEN**

Run: `uv run pytest -q tests/research/test_artifacts.py::test_write_screening_run_persists_decisions_and_summary`

Expected: PASS.

## Task 4: Integrate Screening into Main Backtest Entry Point

**Files:**
- Modify: `src/main.py`
- Modify: `tests/research/test_backtest_defaults.py`

- [ ] **Step 1: Write the failing `src.main` integration tests**

Extend `tests/research/test_backtest_defaults.py` with coverage that proves:

- when screening is enabled for a named/broader universe, `main()` filters `data_dfs` down to `eligible_symbols` before calling `run_with_logging`
- `main()` prints a compact summary containing requested, eligible, and screened-out counts
- `main()` writes a screening artifact when screening runs
- default small-ticker behavior remains unchanged when screening is not requested

Use monkeypatched `fetch_universe`, `screen_universe`, and `write_screening_run` stubs so the test stays offline and deterministic.

- [ ] **Step 2: Run the focused `src.main` tests to verify RED**

Run: `uv run pytest -q tests/research/test_backtest_defaults.py::test_main_multi_factor_filters_named_universe_with_screening tests/research/test_backtest_defaults.py::test_main_defaults_do_not_run_screening_without_universe_selection`

Expected: FAIL because `src.main` does not yet call the screening flow.

- [ ] **Step 3: Write the minimal `src.main` implementation**

Update `src/main.py` so that:

- broader-universe backtests can run screening before strategy execution
- screening defaults are conservative and explicit
- screening uses `screen_as_of=args.end` for this one-shot phase-1 integration
- only eligible symbols are passed to `run_with_logging`
- if screening removes every symbol, the CLI exits with a friendly message
- the compact console summary prints:
  - requested symbol count
  - eligible symbol count
  - screened-out symbol count
  - eligibility ratio
- a screening artifact is written through `src.research.artifacts`

Implementation constraints:

- keep screening out of the default small 3-symbol fallback path unless explicitly enabled by the new integration rule
- do not change approved-weight behavior or strategy kwargs resolution

- [ ] **Step 4: Run the focused `src.main` tests to verify GREEN**

Run: `uv run pytest -q tests/research/test_backtest_defaults.py::test_main_multi_factor_filters_named_universe_with_screening tests/research/test_backtest_defaults.py::test_main_defaults_do_not_run_screening_without_universe_selection`

Expected: PASS.

## Task 5: Run Adjacent Regression Coverage

**Files:**
- Modify as needed from earlier tasks

- [ ] **Step 1: Run the screening and artifact regression slice**

Run: `uv run pytest -q tests/research/test_screening.py tests/research/test_artifacts.py tests/research/test_backtest_defaults.py`

Expected: PASS.

- [ ] **Step 2: Run the full regression suite**

Run: `uv run pytest -q`

Expected: PASS.

- [ ] **Step 3: Commit the phase-1 screening slice**

Run:

```bash
git add src/research/screening.py src/research/artifacts.py src/main.py tests/research/test_screening.py tests/research/test_artifacts.py tests/research/test_backtest_defaults.py
git commit -m "feat(research): add universe screening pipeline"
```

Expected: commit succeeds after all tests pass.

## Notes for the Implementer

- Keep phase 1 intentionally narrow: it should produce a real, explainable universe-screening workflow without pulling in fundamentals, walk-forward per-window screening, or paper-trading changes.
- Preserve deterministic output as much as possible so screening reasons and summary keys stay easy to regression-test.
- If the current CLI needs a tiny explicit switch or rule to avoid screening the default small fallback universe, prefer a simple, explicit condition over hidden heuristics.
