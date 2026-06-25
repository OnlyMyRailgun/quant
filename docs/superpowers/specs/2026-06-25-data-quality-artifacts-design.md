# Data Quality Artifacts Design

## Status

Approved implementation slice from `docs/superpowers/specs/2026-06-18-institutional-research-platform-evolution-design.md`.

## Goal

Add deterministic local data-quality reports for the existing Parquet research store so future point-in-time universe and factor research work has a machine-checkable data credibility baseline.

## Parent Scope

This implements the data-quality artifact portion of Phase 1: Data and Universe Credibility. It does not solve historical TOPIX membership, lifecycle metadata, or true fundamental filing timestamps. It creates the report structure and validation command that those later capabilities can extend.

## User Workflow

Run a data-quality report over a named universe or explicit symbols:

```bash
uv run python -m src.research.data_quality \
  --universe-name japan_large_30 \
  --start 2021-01-01 \
  --end 2026-04-30
```

The command writes a run directory under `.research_artifacts/data_quality/<timestamp>-<run-id>/` and exits non-zero when critical validation errors exceed configured thresholds.

## Artifact Contract

Each run writes:

- `metadata.json`: run id, run name, root path, requested dates, requested symbols, threshold configuration, creation timestamp.
- `coverage.csv`: one row per requested symbol with manifest coverage, raw data coverage, row counts, and status.
- `validation_errors.csv`: one row per detected issue with symbol, severity, issue code, and detail.
- `summary.json`: aggregate requested/passed/failed counts, critical/warning counts, and pass/fail status.

The artifact writer must support deterministic `run_id`, `timestamp`, and `created_at` injection for tests.

## Validation Rules

Critical errors:

- missing raw Parquet file;
- missing manifest record;
- manifest status is not in the allowed status list;
- manifest validated range does not cover the requested start/end;
- raw file has no usable rows in the requested range;
- duplicate dates in the requested range;
- missing `Close`;
- non-finite `Close`;
- non-positive `Close`.

Warnings:

- manifest `validation_issues` from the latest manifest record;
- raw file date range does not match manifest coverage exactly.

## Data Flow

1. Resolve symbols from `--symbols` or `--universe-name`.
2. For each symbol, read the latest manifest record from `src.data.local_store`.
3. Read raw Parquet from `src.data.local_store.get_raw_path`.
4. Normalize the local raw frame to a date index.
5. Validate the requested date slice with `src.research.data_validation.validate_price_frame`.
6. Build `coverage.csv`, `validation_errors.csv`, and `summary.json`.
7. Persist artifacts and append a registry entry through the existing research artifact registry.

## API Design

`src.research.data_quality` exposes:

- `DataQualityThresholds`: dataclass with `max_critical_errors`, `allowed_manifest_statuses`.
- `run_data_quality_report(...) -> dict[str, Path]`: programmatic artifact writer.
- `main(argv: list[str] | None = None) -> int`: CLI entry point.

The module should keep validation logic small and explicit. It should reuse `local_store` for path and manifest parsing instead of duplicating catalog logic.

## Testing

Focused tests live in `tests/research/test_data_quality.py`:

- normal symbol writes all four artifacts with a passing summary;
- missing raw or missing manifest produces a critical error and non-zero CLI exit;
- invalid prices and duplicate dates are surfaced in `validation_errors.csv`;
- deterministic run ids and timestamps produce stable artifact paths;
- named universe resolution works through a monkeypatched universe map.

## Non-goals

- Do not download data.
- Do not introduce external vendor dependencies.
- Do not validate historical constituent membership.
- Do not validate fundamental filing availability.
- Do not delete or rewrite existing local Parquet files.
