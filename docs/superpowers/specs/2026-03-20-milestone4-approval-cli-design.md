# Milestone 4 Approval CLI Design

## Objective

Make the walk-forward approval workflow operator-friendly enough to use directly from the command line.

This design narrows the next Milestone 4 slice to two usability improvements on top of the new approval CLI:

1. `approve` should default to the latest available `rebalance_date` for a selected run.
2. `list` should show the latest `rebalance_date` and the weights artifact path for each candidate run.

## Why This Matters

The project already has the core approval mechanics:

- walk-forward runs are persisted as artifacts
- approved params can be written to `paper_trade_params.json`
- paper trading and backtests can read the approved params file

The remaining gap is operator usability. Requiring the operator to manually inspect a weights CSV to find the latest rebalance date creates avoidable friction and increases the chance of approving the wrong slice of a run.

## Scope

In scope:

- enrich approval CLI list output with latest rebalance date and weights path
- allow `approve --run-id <id>` to work without explicitly passing `--rebalance-date`
- keep explicit `--rebalance-date` support for manual overrides
- produce clear CLI success and error messages

Out of scope:

- approval history or audit log files
- interactive prompts
- changes to walk-forward scoring or artifact schema
- GUI or web workflow

## Approaches

### Approach A: CLI-only convenience layer

Keep all approval rules in `src/research/approved_params.py` and make `src/research/approve.py` compute the latest rebalance date by reading the weights file for the chosen run.

Pros:

- smallest change
- minimal new surface area
- easy to verify

Cons:

- some run-inspection logic lives in the CLI layer

### Approach B: Shared inspection helper plus thin CLI

Add helper(s) in `src/research/approved_params.py` for loading walk-forward runs and determining the latest rebalance date, then make the CLI consume those helpers.

Pros:

- cleaner separation
- reusable for other research entry points later
- better fit for Milestone 4 unification work

Cons:

- slightly more code than Approach A

### Approach C: Full approval manifest workflow

Add richer metadata, selection state, and approval records alongside the CLI.

Pros:

- strongest auditability

Cons:

- too much scope for this slice

## Recommendation

Choose Approach B.

It keeps the operator-facing CLI thin while moving reusable inspection behavior into the research approval module, which is a better foundation for the remaining Milestone 4 work.

## Proposed Design

### Shared approval inspection helpers

Extend `src/research/approved_params.py` with helper(s) that:

- load walk-forward runs from the registry
- attach parsed `summary.json`
- read `weights.csv`
- derive the latest available `rebalance_date`

Each returned candidate record should include:

- `run_id`
- `summary`
- `weights`
- `latest_rebalance_date`
- `weights_path`

### CLI behavior

`src/research/approve.py` should support:

- `list`
  - print one row per walk-forward run
  - include `run_id`, `window_count`, `baseline_return_pct`, `walk_forward_return_pct`, `active_return_pct`, `latest_rebalance_date`, and `weights_path`
- `approve`
  - require `--run-id`
  - accept optional `--rebalance-date`
  - if `--rebalance-date` is omitted, use the candidate run's `latest_rebalance_date`
  - print the selected rebalance date and the output path for `paper_trade_params.json`

### Error handling

Failures should be explicit and operator-readable:

- missing run id
- missing or invalid weights file
- no available rebalance rows
- invalid explicit rebalance date

### Testing

Add tests for:

- `list` includes latest rebalance date and weights path
- `approve` works without `--rebalance-date`
- explicit rebalance date still overrides the default
- failure messaging remains readable when the run or weights are invalid

## Definition of Done

This slice is complete when:

1. operators can inspect candidate runs without opening CSV files manually
2. operators can approve a run with only `--run-id`
3. approved params still write to the same stable file location
4. tests cover both the convenience path and the explicit override path
