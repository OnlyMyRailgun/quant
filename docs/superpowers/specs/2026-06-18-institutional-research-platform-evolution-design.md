# Institutional Research Platform Evolution Design

## Status

Draft for user review. This spec captures the recommended next evolution after the professional review remediation. It is not yet an approved implementation plan.

## Goal

Evolve the repo from a strategy backtest and paper-trading project into a more institutionally credible factor research platform. The next work should prioritize data breadth, point-in-time correctness, factor evidence, risk attribution, and objective acceptance gates before adding more alpha ideas or tuning weights.

## Background

The current project has repaired several local correctness issues: compounded walk-forward summaries, Backtrader no-look-ahead scoring, vectorbt trading calendar alignment, quality-weight propagation, broader default `top_n`, and less contradictory default grids.

The remaining limitations are research-design limitations:

- The static 30-name universe is too small for robust cross-sectional factor evidence.
- Short OOS windows make Sharpe, IC, and walk-forward weight selection statistically weak.
- P/B alone is a weak value proxy.
- Long-only returns can be dominated by market and sector beta.
- Walk-forward optimization can still overfit if the experiment design lacks sufficient breadth, holdout discipline, and multiple-testing controls.

## Design Principles

- Evidence before optimization: prove factor predictiveness before optimizing portfolio weights.
- Point-in-time first: no alpha claim should depend on data that would not have been known on the scoring date.
- Breadth before complexity: increase universe and history before adding more factors.
- Risk-adjusted conclusions: report beta, sector, concentration, turnover, and cost attribution alongside raw return.
- Machine-checkable gates: a run should pass explicit research acceptance criteria before it can be approved for paper trading.

## Scope

### 1. Point-in-Time Data Foundation

Build a research data layer that can support institutional-style experiments.

Requirements:

- Add support for a broad universe target, initially TOPIX500 or equivalent, with a migration path to TOPIX1000 if data availability allows.
- Store point-in-time constituent membership by effective date.
- Store symbol lifecycle fields: listing date, delisting date, exchange, ticker changes, and corporate action metadata where available.
- Align fundamentals by report/filing availability date, not just fiscal period end.
- Keep local Parquet manifests explicit about vendor, download timestamp, source coverage, and validation status.
- Add data-quality reports for missing prices, stale prices, suspended names, duplicate dates, non-positive prices, and corporate-action discontinuities.

Acceptance criteria:

- A historical universe query for any rebalance date returns only symbols investable on that date.
- A fundamental query for any scoring date returns only fields available as of that date.
- A data-quality command emits a deterministic JSON/CSV report and fails when configured critical thresholds are exceeded.
- Existing small curated universes remain available for smoke tests but are labeled non-decision-grade in research outputs.

Non-goals:

- Do not build a broker-grade execution simulator in this phase.
- Do not claim survivorship-free research until membership and lifecycle data are validated against an authoritative source.

### 2. Factor Research Layer

Separate factor evidence from portfolio P&L.

Requirements:

- Produce per-rebalance cross-sectional factor panels for all eligible universe members.
- Compute forward returns for 1M, 3M, 6M, and 12M horizons.
- Report Pearson IC and rank IC by period and horizon.
- Report IC mean, standard deviation, t-stat, hit rate, skew, and decay.
- Segment IC by sector, size bucket, liquidity bucket, and market regime where data supports it.
- Report factor correlation and factor turnover.
- Save factor panels and summaries as versioned artifacts.

Acceptance criteria:

- A factor-analysis run produces `factor_panel.parquet`, `forward_returns.parquet`, `ic_summary.csv`, `ic_by_period.csv`, `factor_correlation.csv`, and `metadata.json`.
- The run can be reproduced from metadata without manually reconstructing parameters.
- At least one test fixture proves forward returns are computed from future prices while factor values use only prior or as-of data.
- The reporting layer can show that a factor has no statistically useful IC instead of forcing a strategy conclusion.

Non-goals:

- Do not optimize strategy weights inside the factor research layer.
- Do not approve paper trading parameters directly from IC output without portfolio and risk checks.

### 3. Risk Model and Portfolio Construction

Move beyond equal-weight top-N as the only construction method.

Requirements:

- Estimate market beta against TOPIX and N225 benchmarks.
- Estimate sector exposures and active sector weights versus the research universe or benchmark.
- Estimate single-name concentration, volatility contribution, and idiosyncratic risk proxies.
- Track turnover, gross traded value, transaction costs, and lot-size cash drag.
- Add portfolio construction modes:
  - equal-weight top-N, kept as baseline;
  - constrained long-only optimization;
  - beta-targeted long-only;
  - optional beta-neutral research mode if short/hedge instruments are available.
- Support constraints for max single-name weight, max sector deviation, max turnover, min liquidity, and target beta range.

Acceptance criteria:

- Every backtest artifact includes return attribution, beta, sector exposure, concentration, turnover, and cost summaries.
- A long-only run cannot claim alpha unless its report separates raw return, benchmark return, active return, and beta-adjusted residual return.
- Tests cover at least one synthetic case where raw outperformance disappears after beta adjustment.
- Portfolio construction constraints are deterministic and fail loudly when no feasible portfolio exists.

Non-goals:

- Do not implement a complex commercial-grade multi-factor risk model before the simpler beta/sector/concentration model is working.
- Do not hide constraint failures by falling back silently to equal weight.

### 4. Research Acceptance Gates

Make strategy approval explicit and machine-checkable.

Requirements:

- Define a `research_report.json` schema with required metrics and pass/fail gates.
- Generate a human-readable `research_report.md` from the same data.
- Gate categories:
  - data coverage and point-in-time validity;
  - minimum OOS length and rebalance count;
  - factor IC significance and stability;
  - benchmark-relative and beta-adjusted performance;
  - drawdown and downside risk;
  - turnover, transaction cost, and capacity;
  - concentration and sector exposure;
  - parameter stability across walk-forward windows;
  - untouched holdout performance after parameter freeze.
- The approval CLI should reject parameter approval when required gates fail unless an explicit override file is supplied.

Initial suggested gates:

- Minimum OOS history: 5 years for exploratory approval, 8-10 years for decision-grade approval.
- Minimum OOS rebalance windows: 60 monthly windows for exploratory approval.
- Minimum broad universe: 300 investable names for cross-sectional factor claims.
- Maximum single-name target weight: 10% by default.
- Required benchmark reporting: TOPIX and N225.
- Required cost model: commission, slippage assumption, lot-size cash drag.
- Required multiple-testing note: count tested factors, grids, and optimizer trials.

Acceptance criteria:

- A research run with too few OOS windows fails approval even if Sharpe is high.
- A run with high raw return but poor beta-adjusted residual return is flagged.
- A run with excessive concentration fails unless explicitly configured as a concentrated active-stock-picking experiment.
- The approval CLI records gate results in the approved-params artifact.

Non-goals:

- Do not hard-code one universal institutional threshold as permanent truth. Gates should be configurable but strict by default.

### 5. Alpha Expansion After Infrastructure

Add new signals only after the platform can evaluate them properly.

Candidate factors:

- Value:
  - EV/EBIT;
  - EV/FCF;
  - earnings yield;
  - dividend yield plus buyback yield;
  - sector-normalized valuation composites.
- Quality:
  - ROE;
  - ROIC;
  - gross profitability;
  - accruals;
  - margin stability;
  - leverage and interest-coverage screens.
- Momentum:
  - 12_1 momentum;
  - 6_1 momentum;
  - residual momentum after beta/sector adjustment;
  - momentum quality filters.
- Low risk:
  - benchmark beta;
  - idiosyncratic volatility;
  - downside volatility;
  - drawdown stability.
- Revisions, if data is available:
  - earnings estimate revisions;
  - analyst breadth;
  - guidance surprise.

Acceptance criteria:

- Each new factor must include a factor definition document, point-in-time data source, missing-data policy, IC report, and portfolio impact report.
- New factors should be evaluated standalone before entering composite optimization.
- Factor additions should increase explanatory power or portfolio quality after costs, not only improve in-sample Sharpe.

## Artifact Design

Recommended new artifact tree:

```text
.research_artifacts/
  data_quality/
    <run_id>/
      metadata.json
      coverage.csv
      validation_errors.csv
      summary.json
  factor_analysis/
    <run_id>/
      metadata.json
      factor_panel.parquet
      forward_returns.parquet
      ic_summary.csv
      ic_by_period.csv
      factor_correlation.csv
      summary.json
  portfolio_research/
    <run_id>/
      metadata.json
      weights.csv
      equity_curve.csv
      trades.csv
      attribution.csv
      risk_summary.json
      research_report.json
      research_report.md
```

## CLI Design

Suggested commands:

```bash
uv run python -m src.research.data_quality \
  --universe-name topix500 \
  --start 2016-01-01 --end 2026-06-30

uv run python -m src.research.factor_analysis \
  --universe-name topix500 \
  --start 2016-01-01 --end 2026-06-30 \
  --momentum-definition 12_1 \
  --factors momentum,low_vol,value,quality

uv run python -m src.research.portfolio_research \
  --factor-run-id <factor_run_id> \
  --construction constrained-long-only \
  --max-name-weight 0.10 \
  --max-sector-active-weight 0.05 \
  --target-beta 1.0

uv run python -m src.research.gate \
  --portfolio-run-id <portfolio_run_id>
```

## Implementation Phases

### Phase 1: Data and Universe Credibility

- Add historical universe membership interfaces.
- Add lifecycle-aware symbol filtering.
- Add data-quality report artifacts.
- Add point-in-time fundamental availability checks.

Exit criteria:

- Broad-universe historical queries work for multiple dates.
- Data-quality artifacts can fail CI-style checks.

### Phase 2: Factor Evidence

- Build factor panel artifacts.
- Add forward-return and IC analysis.
- Add factor correlation and segmentation.

Exit criteria:

- Factor reports can show whether momentum, value, quality, low-vol, and reversal have stable IC before portfolio construction.

### Phase 3: Risk and Portfolio Attribution

- Add beta, sector, concentration, turnover, and cost attribution.
- Add constrained long-only portfolio construction.

Exit criteria:

- Every portfolio report separates raw return from benchmark, beta, cost, and concentration effects.

### Phase 4: Acceptance Gates and Approval Integration

- Add machine-readable research reports.
- Integrate gates into approval CLI.
- Require gate output for paper-trading parameter approval.

Exit criteria:

- A paper-trading parameter set cannot be approved without a gate result or explicit override.

### Phase 5: Factor Expansion

- Add stronger value, quality, low-risk, and revisions factors as data permits.

Exit criteria:

- New alpha factors are accepted only with standalone IC and portfolio-impact evidence.

## Testing Strategy

- Unit tests for point-in-time universe and fundamental queries.
- Fixture tests for delisted and newly listed names.
- Fixture tests for forward-return horizon alignment.
- Synthetic tests for beta adjustment and sector exposure.
- Regression tests for approval gates failing on insufficient OOS windows.
- Artifact schema tests for `metadata.json`, `research_report.json`, and required CSV/Parquet outputs.
- CLI smoke tests for data quality, factor analysis, portfolio research, and gate commands.

## Open Questions

- Which data source will provide historical TOPIX500/TOPIX1000 membership and lifecycle fields?
- Is shorting or benchmark hedging allowed for research-only beta-neutral tests?
- What liquidity and capacity assumptions should be used for Japanese equities?
- Should approval gates be one strict profile or multiple profiles, such as `exploratory`, `paper`, and `production`?
- Should paper trading remain long-only even if research supports beta-neutral evidence?

## Explicit Non-goals

- Do not continue tuning Optuna/grid weights on the current small sample as the main research path.
- Do not treat 2025-2026 gold buy-and-hold returns as a strategy without a dedicated asset-allocation research framework.
- Do not add many factors without point-in-time data and standalone IC evidence.
- Do not present long-only raw returns as alpha without benchmark and beta decomposition.
