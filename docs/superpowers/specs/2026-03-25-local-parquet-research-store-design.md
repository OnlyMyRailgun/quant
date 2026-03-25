# Local Parquet Research Store Design

Date: 2026-03-25

## Goal

Build a local-first research data store so research runs can rely on pre-synced historical market data instead of fetching on demand during experiments.

The immediate target is:

- tens to hundreds of JP equity symbols
- daily OHLCV data
- reproducible research runs
- stable warmup coverage for momentum and walk-forward experiments

## Why This Slice

The current data path mixes two responsibilities:

- fetch missing Yahoo Finance data
- serve research-ready slices

That coupling causes a few problems:

- research runtime depends on network access
- the same symbols get fetched repeatedly across experiments
- requested windows may differ from required warmup windows
- cache files only imply raw date coverage, not validated research readiness

This slice separates data synchronization from research consumption.

## Non-Goals

This slice does not:

- introduce fundamentals or non-price datasets
- replace pandas-based factor calculations
- require DuckDB for the first implementation
- solve every data repair workflow inside the manifest itself
- build a full market calendar service beyond what is needed for validation

## Recommendation

Use a Parquet-first local data store with a validated manifest.

This is preferred over DuckDB right now because:

- the current workload is daily OHLCV for tens to hundreds of symbols
- the existing code already uses pandas and per-symbol dataframes
- the biggest need is stable local reuse, not relational querying
- implementation cost is much lower while preserving a later path to DuckDB

DuckDB can be reconsidered later if research expands to:

- larger universes
- multi-table joins
- fundamentals and event datasets
- SQL-heavy screening and feature engineering

## Architecture

### 1. Raw Store

Store raw historical price data locally as one Parquet file per symbol.

Example layout:

```text
.data_store/
  raw/
    7203.T.parquet
    6758.T.parquet
```

Each file stores normalized daily OHLCV data with a monotonic timestamp index.

This layer answers:

- what data was downloaded
- what raw rows are locally available

This layer does not, by itself, declare the data research-ready.

### 2. Validated Manifest

Maintain a manifest that records both downloaded coverage and validated coverage.

Recommended location:

```text
.data_store/catalog/manifest.jsonl
```

Manifest update semantics for the first implementation:

- treat the manifest as append-only on write
- write a new record for a symbol each time sync or re-validation updates its state
- on read, collapse records by symbol and keep only the latest record by `last_synced`

Why this choice:

- writes stay simple and cheap
- sync jobs do not need to rewrite the whole manifest file
- readers get deterministic symbol state as long as they explicitly select the latest record

The prepared loader and any manifest helpers must therefore implement "latest record wins" semantics.

Recommended record shape:

```json
{
  "symbol": "7203.T",
  "downloaded_start": "2021-01-04",
  "downloaded_end": "2024-12-30",
  "validated_start": "2021-01-04",
  "validated_end": "2024-12-30",
  "trading_days_expected": 972,
  "trading_days_actual": 968,
  "missing_count": 4,
  "missing_date_samples": ["2022-03-11", "2022-06-15"],
  "last_synced": "2026-03-25T05:00:00Z",
  "validation_status": "ok",
  "validation_issues": []
}
```

Key design decision:

- `downloaded_*` describes raw local coverage
- `validated_*` describes research-usable coverage

This distinction matters because a file can exist for a full span while still failing research quality checks.

### 3. Sync Job

Add an explicit sync path that fetches and refreshes local history ahead of research runs.

Responsibilities:

- download a broad requested range for a universe
- merge new rows into each symbol Parquet file
- normalize and persist raw data
- validate raw coverage against expected trading days and price rules
- update the manifest

The sync job becomes the only path that talks to the remote market data source in normal research operation.

### 4. Prepared Loader

Add a research-facing loader that reads only from local Parquet files plus the manifest.

Responsibilities:

- reject or skip symbols whose manifest status is not usable
- verify the requested research range is covered by validated data
- provide extra warmup history before the requested start date
- return symbol dataframes in the shape expected by existing scoring and backtest code

The prepared loader should not fetch from Yahoo Finance.

If data is missing, it should report what coverage is missing and instruct the caller to run sync first.

## Manifest Semantics

The manifest is for fast research-readiness decisions, not full forensic storage.

Because of that:

- store `missing_count`
- store only the first 5 `missing_date_samples`
- do not store the full list of all missing dates

Why:

- research consumers mainly need a quick pass/fail signal
- a few samples are enough to show whether gaps are clustered or random
- detailed investigation can still be done by comparing Parquet rows against the trading calendar when needed

## Validation Policy

Validation should happen after sync, not repeatedly during every experiment.

Suggested checks:

- monotonic increasing timestamps
- no duplicate timestamps
- positive close values
- finite numeric values
- expected trading-day coverage over the validated span
- acceptable missing-count or missing-ratio threshold

Suggested status values:

- `ok`
- `warning`
- `invalid`

Suggested initial thresholds:

| Condition | Status |
|------|--------|
| `missing_count == 0` and no structural validation issues | `ok` |
| `0 < missing_count <= 5` and `missing_ratio < 0.01` and no structural validation issues | `warning` |
| `missing_count > 5` or `missing_ratio >= 0.01` or any structural validation issue exists | `invalid` |

Structural validation issues include:

- unsorted timestamps
- duplicate timestamps
- non-finite numeric values
- non-positive close values

The first implementation should use these concrete thresholds rather than leaving `warning` ambiguous.

Research defaults:

- load only `ok` symbols
- optionally allow `warning` with an explicit flag
- never auto-load `invalid`

## Warmup Behavior

The prepared loader should support warmup-aware reads.

Example:

- user requests `2022-01-01 -> 2022-03-31`
- momentum requires 252 prior bars plus a 21-bar skip for `12_1`

The loader should return:

- requested research window
- enough validated prior history before `2022-01-01`

This avoids:

- empty validation runs
- indicator warmup failures
- misleading zero-return windows caused by incomplete local slicing

## Interfaces

### Sync interface

Examples:

- sync one named universe across a broad range
- refresh the right edge for already-synced symbols
- sync with a configurable overwrite or append mode

Append-mode merge semantics:

- if newly fetched data overlaps an already stored date range, the new rows win
- overlapping rows from the existing Parquet file should be replaced by the newly fetched rows
- non-overlapping rows on either side should be preserved

Why:

- this allows later sync runs to repair stale or dirty source rows
- it matches the most intuitive "refresh with latest source truth" behavior
- it keeps append mode useful even when users resync a partially overlapping range

Possible API shape:

```python
sync_universe_history(
    symbols: list[str],
    start_date: str,
    end_date: str,
    *,
    source: str = "yfinance",
) -> dict[str, object]
```

### Prepared loader interface

Possible API shape:

```python
load_local_universe(
    symbols: list[str],
    start_date: str,
    end_date: str,
    *,
    warmup_bars: int = 0,
    allowed_statuses: tuple[str, ...] = ("ok",),
) -> dict[str, pd.DataFrame]
```

## File Layout

Recommended initial layout:

```text
.data_store/
  raw/
    <symbol>.parquet
  catalog/
    manifest.jsonl
```

This keeps the first slice simple while leaving room for future additions such as:

- benchmarks
- alternative data sources
- derived feature caches
- market calendar snapshots

## Testing Strategy

### Unit tests

Add tests for:

- syncing a new symbol writes raw Parquet and manifest entry
- refreshing existing coverage extends the right edge correctly
- manifest differentiates downloaded coverage from validated coverage
- missing-count and missing-date samples are recorded correctly
- prepared loader rejects invalid or insufficiently validated symbols
- prepared loader returns requested range plus warmup rows

### Integration tests

Add tests proving:

- research paths can run without network once local data exists
- a walk-forward request with short validation windows still receives enough warmup data from local storage
- stale or partial local coverage produces a clear sync-required failure

## Migration Strategy

Implement this in-place without breaking current research entry points immediately.

Suggested rollout:

1. add the local store and manifest primitives
2. add a sync command
3. add a prepared local loader
4. switch research-only paths to prefer prepared local loads
5. keep current on-demand fetch path only as a temporary fallback, then remove or demote it

## Acceptance Criteria

This slice is complete when:

1. a universe can be synced locally across a broad date range
2. local Parquet data is persisted per symbol
3. a validated manifest records usable coverage and data-quality state
4. research loaders can serve local data with warmup history and no network calls
5. research runs fail clearly when required coverage is not already synced

## Expected Next Slice

After this slice, the next likely improvements are:

- switching walk-forward and other research paths fully to the prepared local loader
- adding a small market-calendar helper for stronger trading-day validation
- later, reconsidering DuckDB only if research expands into multi-table or SQL-heavy workflows
