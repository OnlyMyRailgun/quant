# Milestone 4 Approval CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the approval CLI easier for operators to use by showing latest rebalance metadata in `list` output and allowing `approve --run-id` to default to the latest rebalance date.

**Architecture:** Move walk-forward run inspection into `src/research/approved_params.py` so the CLI can stay thin and reusable. The CLI should delegate candidate loading and latest-rebalance resolution to shared helpers, then keep its job limited to parsing args, printing readable output, and calling the existing approval writer.

**Tech Stack:** Python, argparse, pandas, pytest

---

## File Structure

### New files

- None

### Modified files

- `src/research/approved_params.py`
  - Add shared helpers for loading walk-forward candidates from the registry and resolving each run's latest rebalance date.
- `src/research/approve.py`
  - Update CLI list formatting and support approving a run without an explicit rebalance date.
- `tests/research/test_approve_cli.py`
  - Cover richer list output, default latest-date approval, explicit override, and readable failure output.
- `tests/research/test_approved_params.py`
  - Cover the new shared helper(s) that inspect walk-forward runs and derive latest rebalance dates.

## Task 1: Add Shared Candidate Inspection Helpers

**Files:**
- Modify: `src/research/approved_params.py`
- Modify: `tests/research/test_approved_params.py`

- [ ] **Step 1: Write the failing tests**

Add tests that verify a helper such as `load_walk_forward_run_candidates(artifact_dir)`:

- returns walk-forward runs only
- attaches parsed summary data
- exposes `latest_rebalance_date`
- exposes `weights_path`

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `uv run --with pytest pytest /Users/y-yang/Developer/quant/tests/research/test_approved_params.py -q`
Expected: FAIL because the helper does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Implement helper(s) in `src/research/approved_params.py` that:

- load registry records
- filter to `run_name == "walk_forward"`
- validate and load `weights.csv`
- derive the latest rebalance date from the final weights row
- return candidate dicts sorted deterministically

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `uv run --with pytest pytest /Users/y-yang/Developer/quant/tests/research/test_approved_params.py -q`
Expected: PASS

## Task 2: Make `list` Output Operator-Friendly

**Files:**
- Modify: `src/research/approve.py`
- Modify: `tests/research/test_approve_cli.py`

- [ ] **Step 1: Write the failing test**

Extend `test_approve_cli_list_shows_candidate_runs` so it asserts the output includes:

- `latest_rebalance_date`
- `weights_path`
- the correct latest rebalance date for each run

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `uv run --with pytest pytest /Users/y-yang/Developer/quant/tests/research/test_approve_cli.py -q`
Expected: FAIL because list output does not include the extra fields yet.

- [ ] **Step 3: Write the minimal implementation**

Update `src/research/approve.py` so `list` consumes the shared candidate helper and prints:

- `run_id`
- `window_count`
- `baseline_return_pct`
- `walk_forward_return_pct`
- `active_return_pct`
- `latest_rebalance_date`
- `weights_path`

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `uv run --with pytest pytest /Users/y-yang/Developer/quant/tests/research/test_approve_cli.py -q`
Expected: PASS

## Task 3: Allow Approval Without Explicit `--rebalance-date`

**Files:**
- Modify: `src/research/approve.py`
- Modify: `tests/research/test_approve_cli.py`

- [ ] **Step 1: Write the failing tests**

Add tests that verify:

- `approve --run-id wf-b` succeeds without `--rebalance-date`
- the default chosen date is the latest rebalance date for that run
- an explicit `--rebalance-date` still overrides the default

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `uv run --with pytest pytest /Users/y-yang/Developer/quant/tests/research/test_approve_cli.py -q`
Expected: FAIL because `--rebalance-date` is currently required.

- [ ] **Step 3: Write the minimal implementation**

Update the CLI so:

- `--rebalance-date` becomes optional
- the selected candidate run supplies `latest_rebalance_date` when omitted
- success output prints the actual rebalance date that was approved

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `uv run --with pytest pytest /Users/y-yang/Developer/quant/tests/research/test_approve_cli.py -q`
Expected: PASS

## Task 4: Keep Failure Messaging Readable

**Files:**
- Modify: `src/research/approve.py`
- Modify: `tests/research/test_approve_cli.py`

- [ ] **Step 1: Write the failing test**

Add a CLI test that approves a missing `run_id` and asserts the output includes:

- `Approval workflow failed:`
- the missing run id value

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `uv run --with pytest pytest /Users/y-yang/Developer/quant/tests/research/test_approve_cli.py -q`
Expected: FAIL if the CLI message is missing the useful detail.

- [ ] **Step 3: Write the minimal implementation**

Tighten the CLI error output only as needed so the operator sees the actionable failure message without a traceback.

- [ ] **Step 4: Run the targeted tests to verify pass**

Run: `uv run --with pytest pytest /Users/y-yang/Developer/quant/tests/research/test_approve_cli.py -q`
Expected: PASS

## Task 5: Run Verification

**Files:**
- No additional files unless failures are found

- [ ] **Step 1: Run focused approval tests**

Run: `uv run --with pytest pytest /Users/y-yang/Developer/quant/tests/research/test_approve_cli.py /Users/y-yang/Developer/quant/tests/research/test_approved_params.py -q`
Expected: PASS

- [ ] **Step 2: Run adjacent Milestone 4 safety tests**

Run: `uv run --with pytest pytest /Users/y-yang/Developer/quant/tests/research/test_backtest_defaults.py /Users/y-yang/Developer/quant/tests/scoring/test_multi_factor.py /Users/y-yang/Developer/quant/tests/strategies/test_multi_factor_parity.py -q`
Expected: PASS

- [ ] **Step 3: Summarize operator usage**

Capture the final usage shape:

- `uv run python -m src.research.approve list`
- `uv run python -m src.research.approve approve --run-id <id>`
- `uv run python -m src.research.approve approve --run-id <id> --rebalance-date YYYY-MM-DD`
