# Local Parquet Research Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first Parquet research store with validated manifest metadata, an explicit sync path, and a prepared loader so research runs stop fetching market data on demand.

**Architecture:** Add a new local-store module under `src/data` that owns raw-file paths, append-only manifest writes, validation summaries, and warmup-aware local loads. Keep the existing `bulk_loader` network path working, then add a prepared local loader plus sync entry points and finally switch research callers to prefer local-only reads with clear sync-required failures.

**Tech Stack:** Python, pandas, parquet, pytest, existing yfinance-backed fetcher

---

## File Map

**Create:**

- `src/data/local_store.py`
  Responsibility: raw Parquet path helpers, manifest record model helpers, append-only manifest writes, latest-record reads, overlap merge behavior, and local sync/load entry points.
- `tests/data/test_local_store.py`
  Responsibility: unit tests for raw persistence, manifest latest-record semantics, validation thresholds, overlap merge behavior, and warmup-aware local loads.
- `tests/research/test_local_data_integration.py`
  Responsibility: integration tests proving research loaders can run locally without network once synced data exists.

**Modify:**

- `src/data/bulk_loader.py`
  Responsibility: narrow this module to network-backed fetch behavior and reuse local-store helpers where appropriate without changing its public caller contract yet.
- `src/data/universe.py`
  Responsibility: expose any small helper needed for syncing named universes without duplicating lookup logic in a CLI.
- `src/optimize.py`
  Responsibility: add a local-data-first research load path that can fail clearly when required local coverage is missing.
- `src/main.py`
  Responsibility: keep production/backtest entry behavior explicit if any local-store defaults are introduced.
- `tests/data/test_bulk_loader.py`
  Responsibility: preserve current fetch/cache behavior during migration and update assertions if shared helpers move.
- `tests/research/test_walk_forward.py`
  Responsibility: verify walk-forward can load local prepared data with warmup and without network fallback once enabled.

## Task 1: Build the Manifest and Raw Store Primitives

**Files:**

- Create: `src/data/local_store.py`
- Test: `tests/data/test_local_store.py`

- [ ] **Step 1: Write the failing raw-store and manifest tests**

Add tests covering:

- writing a raw Parquet file for one symbol
- appending two manifest records for the same symbol
- reading the latest manifest state by `last_synced`
- overlap merge behavior prefers new rows
- validation status thresholds for `ok`, `warning`, and `invalid`

Example test shapes:

```python
def test_read_latest_manifest_records_prefers_latest_last_synced():
    ...


def test_merge_symbol_frames_prefers_new_rows_on_overlap():
    ...


def test_build_validation_summary_marks_warning_for_small_gap_count():
    ...
```

- [ ] **Step 2: Run the targeted tests to verify RED**

Run:

```bash
uv run pytest -q tests/data/test_local_store.py
```

Expected:

- FAIL because `src/data/local_store.py` does not exist yet

- [ ] **Step 3: Implement the minimal local-store primitives**

Create `src/data/local_store.py` with:

- base directories such as `.data_store/raw` and `.data_store/catalog`
- raw file path helpers
- normalized manifest record serialization
- append-only manifest writes
- latest-record manifest reads keyed by symbol and ordered by `last_synced`
- frame merge logic where overlapping dates prefer newly fetched rows
- validation summary logic producing:
  - `missing_count`
  - `missing_date_samples` capped at 5
  - `validation_status`
  - `validation_issues`

- [ ] **Step 4: Re-run the targeted tests to verify GREEN**

Run:

```bash
uv run pytest -q tests/data/test_local_store.py
```

Expected:

- PASS

- [ ] **Step 5: Commit the primitive layer**

```bash
git add src/data/local_store.py tests/data/test_local_store.py
git commit -m "feat(data): add local parquet store primitives"
```

## Task 2: Add the Explicit Sync Path

**Files:**

- Modify: `src/data/local_store.py`
- Modify: `src/data/bulk_loader.py`
- Test: `tests/data/test_local_store.py`
- Test: `tests/data/test_bulk_loader.py`

- [ ] **Step 1: Write the failing sync tests**

Add tests covering:

- syncing a new symbol downloads, validates, and writes raw + manifest
- syncing a partially overlapping range keeps non-overlap rows and replaces overlap rows with new data
- syncing invalid fetched data records invalid manifest state and does not promote validated coverage incorrectly

Example test shapes:

```python
def test_sync_symbol_history_writes_raw_file_and_manifest_record(...):
    ...


def test_sync_symbol_history_replaces_overlapping_rows_with_new_data(...):
    ...
```

- [ ] **Step 2: Run the sync tests to verify RED**

Run:

```bash
uv run pytest -q tests/data/test_local_store.py tests/data/test_bulk_loader.py -k "sync or overlap"
```

Expected:

- FAIL until sync entry points exist

- [ ] **Step 3: Implement the sync path**

Add to `src/data/local_store.py`:

- `sync_symbol_history(...)`
- `sync_universe_history(...)`
- validation-after-sync flow
- append-only manifest update on every sync

Update `src/data/bulk_loader.py` only enough to reuse shared merge/normalize helpers if that reduces duplication, without changing the current public fetch semantics yet.

- [ ] **Step 4: Re-run the sync tests to verify GREEN**

Run:

```bash
uv run pytest -q tests/data/test_local_store.py tests/data/test_bulk_loader.py -k "sync or overlap"
```

Expected:

- PASS

- [ ] **Step 5: Commit the sync slice**

```bash
git add src/data/local_store.py src/data/bulk_loader.py tests/data/test_local_store.py tests/data/test_bulk_loader.py
git commit -m "feat(data): add explicit local sync workflow"
```

## Task 3: Add the Prepared Local Loader

**Files:**

- Modify: `src/data/local_store.py`
- Test: `tests/data/test_local_store.py`
- Test: `tests/research/test_local_data_integration.py`

- [ ] **Step 1: Write the failing prepared-loader tests**

Add tests proving:

- `load_local_universe(...)` returns the requested range plus warmup rows
- only the latest manifest record per symbol is used
- `invalid` symbols are rejected
- `warning` symbols are rejected by default but load when explicitly allowed
- missing validated coverage raises a clear sync-required error

Example test shapes:

```python
def test_load_local_universe_returns_requested_range_with_warmup_rows():
    ...


def test_load_local_universe_raises_when_validated_coverage_is_insufficient():
    ...
```

- [ ] **Step 2: Run the prepared-loader tests to verify RED**

Run:

```bash
uv run pytest -q tests/data/test_local_store.py tests/research/test_local_data_integration.py -k "load_local_universe or local_data"
```

Expected:

- FAIL until the loader exists

- [ ] **Step 3: Implement the prepared loader**

Extend `src/data/local_store.py` with:

- `load_local_symbol(...)`
- `load_local_universe(...)`
- warmup-aware slicing from validated local history
- allowed-status filtering with `("ok",)` default
- clear errors when validated coverage is insufficient

- [ ] **Step 4: Re-run the prepared-loader tests to verify GREEN**

Run:

```bash
uv run pytest -q tests/data/test_local_store.py tests/research/test_local_data_integration.py -k "load_local_universe or local_data"
```

Expected:

- PASS

- [ ] **Step 5: Commit the prepared-loader slice**

```bash
git add src/data/local_store.py tests/data/test_local_store.py tests/research/test_local_data_integration.py
git commit -m "feat(data): add prepared local research loader"
```

## Task 4: Thread Local-Only Loads Into Research

**Files:**

- Modify: `src/optimize.py`
- Modify: `tests/research/test_walk_forward.py`
- Test: `tests/research/test_local_data_integration.py`

- [ ] **Step 1: Write the failing research integration tests**

Add tests covering:

- walk-forward research can load local data without calling the network fetcher
- local loads include enough warmup for short validation windows
- missing local validated coverage raises a clear error telling the caller to sync first

Example test shapes:

```python
def test_run_walk_forward_optimization_uses_local_prepared_data_without_network(...):
    ...


def test_run_walk_forward_optimization_reports_sync_required_when_local_coverage_is_missing(...):
    ...
```

- [ ] **Step 2: Run the targeted research integration tests to verify RED**

Run:

```bash
uv run pytest -q tests/research/test_walk_forward.py tests/research/test_local_data_integration.py -k "local_prepared_data or sync_required"
```

Expected:

- FAIL until optimize is wired to the local loader

- [ ] **Step 3: Implement the local-first research path**

Update `src/optimize.py` so that:

- research callers can request local prepared loads explicitly
- local loads use `load_local_universe(...)`
- local coverage failures do not silently fetch from Yahoo
- existing callers that still pass `data_dfs` directly continue to work

Keep this slice research-only. Do not silently alter live or paper-trading paths.

- [ ] **Step 4: Re-run the targeted research integration tests to verify GREEN**

Run:

```bash
uv run pytest -q tests/research/test_walk_forward.py tests/research/test_local_data_integration.py -k "local_prepared_data or sync_required"
```

Expected:

- PASS

- [ ] **Step 5: Commit the research wiring**

```bash
git add src/optimize.py tests/research/test_walk_forward.py tests/research/test_local_data_integration.py
git commit -m "feat(research): use local prepared data store"
```

## Task 5: Add a Small Sync Entry Point and Final Verification

**Files:**

- Modify: `src/main.py`
- Modify: `src/data/universe.py`
- Test: `tests/research/test_local_data_integration.py`

- [ ] **Step 1: Write the failing entry-point tests**

Add tests proving:

- a named universe can be resolved and synced through a simple entry path
- the entry path reports what was synced and where data was written

- [ ] **Step 2: Run the entry-point tests to verify RED**

Run:

```bash
uv run pytest -q tests/research/test_local_data_integration.py -k "sync_entry"
```

Expected:

- FAIL until the entry point exists

- [ ] **Step 3: Implement the minimal sync entry point**

Add a simple callable or CLI-facing path that:

- resolves a named universe
- calls `sync_universe_history(...)`
- prints a short summary of synced symbols and manifest status

Keep it minimal. Do not build a large command surface in this slice.

- [ ] **Step 4: Re-run the entry-point tests to verify GREEN**

Run:

```bash
uv run pytest -q tests/research/test_local_data_integration.py -k "sync_entry"
```

Expected:

- PASS

- [ ] **Step 5: Run the full verification suite**

Run:

```bash
uv run pytest -q
```

Expected:

- PASS with only existing warnings

- [ ] **Step 6: Commit the final slice**

```bash
git add src/data/local_store.py src/data/bulk_loader.py src/data/universe.py src/optimize.py src/main.py tests/data/test_local_store.py tests/data/test_bulk_loader.py tests/research/test_local_data_integration.py tests/research/test_walk_forward.py
git commit -m "feat(data): add local parquet research store"
```

## Notes For Execution

- Keep the first storage format simple: per-symbol raw Parquet plus append-only manifest JSONL.
- Manifest readers must always collapse to the latest record per symbol using `last_synced`.
- Validation thresholds in this slice are fixed:
  - `ok`: `missing_count == 0` and no structural issues
  - `warning`: `0 < missing_count <= 5` and `missing_ratio < 1%` and no structural issues
  - `invalid`: otherwise
- Append-mode overlap semantics are fixed:
  - new rows replace old rows on overlapping dates
- Research prepared loads must not silently trigger network fetches.
- Keep production and paper-trading behavior unchanged unless explicitly switched to the local prepared loader in a later slice.
