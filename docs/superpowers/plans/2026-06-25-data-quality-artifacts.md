# Data Quality Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic data-quality artifact generation for the local Parquet research store.

**Architecture:** Add a focused `src.research.data_quality` module that reads local store manifests and raw Parquet files, validates requested date slices, writes the four required artifacts, and exposes a CLI. Reuse existing `src.data.local_store`, `src.data.universe`, `src.research.data_validation`, and `src.research.registry` patterns.

**Tech Stack:** Python 3.12, pandas, pytest, local Parquet store, JSON/CSV research artifacts.

---

## File Map

| File | Role |
| --- | --- |
| `src/research/data_quality.py` | New validation/reporting module and CLI. |
| `src/research/artifacts.py` | Add a data-quality artifact writer following existing run-writer patterns. |
| `tests/research/test_data_quality.py` | New focused tests for report generation and CLI behavior. |
| `tests/research/test_artifacts.py` | Tests for deterministic data-quality artifact writing. |

## Task 1: Add Data-quality Artifact Writer

**Files:**
- Modify: `src/research/artifacts.py`
- Modify: `tests/research/test_artifacts.py`

- [ ] **Step 1: Write failing artifact writer test**

Add this test to `tests/research/test_artifacts.py`:

```python
def test_write_data_quality_run_persists_required_artifacts(tmp_path: Path):
    from src.research.artifacts import write_data_quality_run

    coverage = pd.DataFrame(
        [
            {
                "symbol": "AAA.T",
                "status": "pass",
                "manifest_status": "ok",
                "manifest_validated_start": "2024-01-01",
                "manifest_validated_end": "2024-01-31",
                "raw_start": "2024-01-01",
                "raw_end": "2024-01-31",
                "requested_start": "2024-01-01",
                "requested_end": "2024-01-31",
                "row_count": 23,
            }
        ]
    )
    validation_errors = pd.DataFrame(columns=["symbol", "severity", "issue_code", "detail"])
    summary = {
        "requested_symbol_count": 1,
        "passed_symbol_count": 1,
        "failed_symbol_count": 0,
        "critical_error_count": 0,
        "warning_count": 0,
        "status": "pass",
    }

    paths = write_data_quality_run(
        base_dir=tmp_path,
        metadata={"start": "2024-01-01", "end": "2024-01-31"},
        coverage=coverage,
        validation_errors=validation_errors,
        summary=summary,
        run_id="data_quality-20260625T010203Z-deadbeef",
        timestamp="20260625T010203Z",
        created_at="20260625T010203Z",
    )

    assert paths["run_dir"] == tmp_path / "data_quality" / "20260625T010203Z-20260625T010203Z-deadbeef"
    assert paths["metadata"].exists()
    assert paths["coverage"].exists()
    assert paths["validation_errors"].exists()
    assert paths["summary"].exists()

    metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    assert metadata["run_name"] == "data_quality"
    assert metadata["start"] == "2024-01-01"

    saved_coverage = pd.read_csv(paths["coverage"])
    assert saved_coverage["symbol"].tolist() == ["AAA.T"]

    saved_errors = pd.read_csv(paths["validation_errors"])
    assert saved_errors.columns.tolist() == ["symbol", "severity", "issue_code", "detail"]

    saved_summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert saved_summary["status"] == "pass"

    registry_entry = json.loads((tmp_path / "registry.jsonl").read_text(encoding="utf-8").strip())
    assert registry_entry["run_name"] == "data_quality"
    assert registry_entry["coverage"] == str(paths["coverage"])
    assert registry_entry["validation_errors"] == str(paths["validation_errors"])
```

- [ ] **Step 2: Run artifact test to verify RED**

Run:

```bash
uv run pytest tests/research/test_artifacts.py::test_write_data_quality_run_persists_required_artifacts -q
```

Expected: FAIL with `ImportError` for `write_data_quality_run`.

- [ ] **Step 3: Implement artifact writer**

Add this function to `src/research/artifacts.py`:

```python
def write_data_quality_run(
    base_dir: Path,
    metadata: dict,
    coverage: pd.DataFrame,
    validation_errors: pd.DataFrame,
    summary: dict,
    run_id: str | None = None,
    timestamp: str | None = None,
    created_at: str | None = None,
) -> dict[str, Path]:
    run_name = "data_quality"
    run_id = run_id or create_run_id(run_name)
    timestamp = timestamp or _timestamp()
    created_at = created_at or _timestamp()
    run_dir = base_dir / run_name / f"{timestamp}-{run_id.split('-', 1)[-1]}"
    run_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = run_dir / "metadata.json"
    coverage_path = run_dir / "coverage.csv"
    validation_errors_path = run_dir / "validation_errors.csv"
    summary_path = run_dir / "summary.json"

    metadata_payload = {"run_id": run_id, "run_name": run_name, **metadata}
    metadata_path.write_text(json.dumps(metadata_payload, indent=2, sort_keys=True), encoding="utf-8")
    coverage.to_csv(coverage_path, index=False)
    validation_errors.to_csv(validation_errors_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    registry_entry = {
        "run_id": run_id,
        "run_name": run_name,
        "run_dir": str(run_dir),
        "metadata": str(metadata_path),
        "coverage": str(coverage_path),
        "validation_errors": str(validation_errors_path),
        "summary": str(summary_path),
        "created_at": created_at,
    }
    append_run_record(base_dir / "registry.jsonl", registry_entry)

    return {
        "run_dir": run_dir,
        "metadata": metadata_path,
        "coverage": coverage_path,
        "validation_errors": validation_errors_path,
        "summary": summary_path,
    }
```

- [ ] **Step 4: Run artifact test to verify GREEN**

Run:

```bash
uv run pytest tests/research/test_artifacts.py::test_write_data_quality_run_persists_required_artifacts -q
```

Expected: PASS.

## Task 2: Build Programmatic Data-quality Report

**Files:**
- Create: `src/research/data_quality.py`
- Create: `tests/research/test_data_quality.py`

- [ ] **Step 1: Write failing passing-report test**

Create `tests/research/test_data_quality.py` with local-store fixture helpers and this test:

```python
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from src.data import local_store
from src.research.data_quality import DataQualityThresholds, run_data_quality_report


def _write_symbol(root: Path, symbol: str, closes: list[float], start: str = "2024-01-01") -> None:
    dates = pd.bdate_range(start, periods=len(closes))
    local_store.write_raw_parquet(
        symbol,
        pd.DataFrame({"Date": dates, "Close": closes}),
        root=root,
    )
    local_store.append_manifest_record(
        local_store.ManifestRecord(
            symbol=symbol,
            downloaded_start=date.fromisoformat(dates[0].strftime("%Y-%m-%d")),
            downloaded_end=date.fromisoformat(dates[-1].strftime("%Y-%m-%d")),
            validated_start=date.fromisoformat(dates[0].strftime("%Y-%m-%d")),
            validated_end=date.fromisoformat(dates[-1].strftime("%Y-%m-%d")),
            trading_days_expected=len(dates),
            trading_days_actual=len(dates),
            missing_count=0,
            missing_date_samples=[],
            last_synced=datetime(2024, 2, 1, tzinfo=timezone.utc),
            validation_status="ok",
            validation_issues=[],
            expected_dates_source="fixture",
        ),
        root=root,
    )


def test_run_data_quality_report_writes_passing_artifacts(tmp_path: Path):
    _write_symbol(tmp_path, "AAA.T", [100.0, 101.0, 102.0, 103.0, 104.0])

    paths = run_data_quality_report(
        symbols=["AAA.T"],
        start="2024-01-01",
        end="2024-01-05",
        root=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        thresholds=DataQualityThresholds(max_critical_errors=0),
        run_id="data_quality-20260625T010203Z-deadbeef",
        timestamp="20260625T010203Z",
        created_at="20260625T010203Z",
    )

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary == {
        "requested_symbol_count": 1,
        "passed_symbol_count": 1,
        "failed_symbol_count": 0,
        "critical_error_count": 0,
        "warning_count": 0,
        "status": "pass",
    }

    coverage = pd.read_csv(paths["coverage"])
    assert coverage.loc[0, "symbol"] == "AAA.T"
    assert coverage.loc[0, "status"] == "pass"
    assert coverage.loc[0, "row_count"] == 5

    errors = pd.read_csv(paths["validation_errors"])
    assert errors.empty
```

- [ ] **Step 2: Run passing-report test to verify RED**

Run:

```bash
uv run pytest tests/research/test_data_quality.py::test_run_data_quality_report_writes_passing_artifacts -q
```

Expected: FAIL because `src.research.data_quality` does not exist.

- [ ] **Step 3: Implement report module skeleton**

Create `src/research/data_quality.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.data import local_store
from src.research.artifacts import DEFAULT_ARTIFACT_DIR, write_data_quality_run
from src.research.data_validation import validate_price_frame


@dataclass(frozen=True)
class DataQualityThresholds:
    max_critical_errors: int = 0
    allowed_manifest_statuses: tuple[str, ...] = ("ok", "warning")


def _date_string(value) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _load_raw_frame(symbol: str, root: Path) -> pd.DataFrame | None:
    raw_path = local_store.get_raw_path(symbol, root=root)
    if not raw_path.exists():
        return None
    frame = pd.read_parquet(raw_path)
    if "Date" in frame.columns:
        frame = frame.copy()
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
        frame = frame.dropna(subset=["Date"]).sort_values("Date", kind="mergesort")
        frame = frame.set_index("Date")
    return frame


def _coverage_row(symbol: str, status: str, manifest, frame: pd.DataFrame | None, start: str, end: str, row_count: int) -> dict:
    raw_start = _date_string(frame.index.min()) if frame is not None and len(frame) else None
    raw_end = _date_string(frame.index.max()) if frame is not None and len(frame) else None
    return {
        "symbol": symbol,
        "status": status,
        "manifest_status": manifest.validation_status if manifest else None,
        "manifest_validated_start": manifest.validated_start.isoformat() if manifest and manifest.validated_start else None,
        "manifest_validated_end": manifest.validated_end.isoformat() if manifest and manifest.validated_end else None,
        "raw_start": raw_start,
        "raw_end": raw_end,
        "requested_start": start,
        "requested_end": end,
        "row_count": row_count,
    }


def _error(symbol: str, severity: str, issue_code: str, detail: str) -> dict[str, str]:
    return {"symbol": symbol, "severity": severity, "issue_code": issue_code, "detail": detail}


def run_data_quality_report(
    symbols: Iterable[str],
    start: str,
    end: str,
    root: Path | str = ".",
    artifact_dir: Path | str = DEFAULT_ARTIFACT_DIR,
    thresholds: DataQualityThresholds | None = None,
    run_id: str | None = None,
    timestamp: str | None = None,
    created_at: str | None = None,
) -> dict[str, Path]:
    thresholds = thresholds or DataQualityThresholds()
    root_path = Path(root)
    artifact_path = Path(artifact_dir)
    requested_symbols = list(symbols)
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    coverage_rows: list[dict] = []
    error_rows: list[dict[str, str]] = []

    for symbol in requested_symbols:
        manifest = local_store.read_latest_manifest_record(symbol, root=root_path)
        frame = _load_raw_frame(symbol, root_path)
        row_count = 0

        if manifest is None:
            error_rows.append(_error(symbol, "critical", "missing_manifest", "no manifest record found"))
        else:
            if manifest.validation_status not in thresholds.allowed_manifest_statuses:
                error_rows.append(
                    _error(symbol, "critical", "manifest_status", f"status={manifest.validation_status}")
                )
            if manifest.validated_start is None or manifest.validated_end is None:
                error_rows.append(_error(symbol, "critical", "manifest_coverage", "validated range is missing"))
            elif start_ts.date() < manifest.validated_start or end_ts.date() > manifest.validated_end:
                error_rows.append(
                    _error(
                        symbol,
                        "critical",
                        "manifest_coverage",
                        f"validated={manifest.validated_start.isoformat()}..{manifest.validated_end.isoformat()}",
                    )
                )
            for issue in manifest.validation_issues:
                error_rows.append(_error(symbol, "warning", "manifest_validation_issue", issue))

        if frame is None:
            error_rows.append(_error(symbol, "critical", "missing_raw", "raw parquet file not found"))
        else:
            sliced = frame.loc[(frame.index >= start_ts) & (frame.index <= end_ts)]
            row_count = len(sliced)
            validation = validate_price_frame(sliced)
            for issue in validation.issues:
                error_rows.append(_error(symbol, "critical", issue.replace(" ", "_"), issue))

        symbol_errors = [row for row in error_rows if row["symbol"] == symbol and row["severity"] == "critical"]
        coverage_rows.append(
            _coverage_row(
                symbol=symbol,
                status="fail" if symbol_errors else "pass",
                manifest=manifest,
                frame=frame,
                start=start,
                end=end,
                row_count=row_count,
            )
        )

    coverage = pd.DataFrame(coverage_rows)
    validation_errors = pd.DataFrame(error_rows, columns=["symbol", "severity", "issue_code", "detail"])
    critical_error_count = int((validation_errors["severity"] == "critical").sum()) if not validation_errors.empty else 0
    warning_count = int((validation_errors["severity"] == "warning").sum()) if not validation_errors.empty else 0
    failed_symbol_count = int((coverage["status"] == "fail").sum()) if not coverage.empty else 0
    summary = {
        "requested_symbol_count": len(requested_symbols),
        "passed_symbol_count": len(requested_symbols) - failed_symbol_count,
        "failed_symbol_count": failed_symbol_count,
        "critical_error_count": critical_error_count,
        "warning_count": warning_count,
        "status": "pass" if critical_error_count <= thresholds.max_critical_errors else "fail",
    }

    metadata = {
        "root": str(root_path),
        "start": start,
        "end": end,
        "symbols": requested_symbols,
        "thresholds": {
            "max_critical_errors": thresholds.max_critical_errors,
            "allowed_manifest_statuses": list(thresholds.allowed_manifest_statuses),
        },
    }
    return write_data_quality_run(
        base_dir=artifact_path,
        metadata=metadata,
        coverage=coverage,
        validation_errors=validation_errors,
        summary=summary,
        run_id=run_id,
        timestamp=timestamp,
        created_at=created_at,
    )
```

- [ ] **Step 4: Run passing-report test to verify GREEN**

Run:

```bash
uv run pytest tests/research/test_data_quality.py::test_run_data_quality_report_writes_passing_artifacts -q
```

Expected: PASS.

## Task 3: Validate Critical Error Cases

**Files:**
- Modify: `tests/research/test_data_quality.py`
- Modify: `src/research/data_quality.py`

- [ ] **Step 1: Add failing tests for missing and invalid data**

Add tests:

```python
def test_run_data_quality_report_records_missing_raw_and_manifest(tmp_path: Path):
    paths = run_data_quality_report(
        symbols=["MISSING.T"],
        start="2024-01-01",
        end="2024-01-05",
        root=tmp_path,
        artifact_dir=tmp_path / "artifacts",
    )

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["status"] == "fail"
    assert summary["critical_error_count"] == 2

    errors = pd.read_csv(paths["validation_errors"])
    assert set(errors["issue_code"]) == {"missing_manifest", "missing_raw"}


def test_run_data_quality_report_records_bad_price_slice(tmp_path: Path):
    dates = pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02"])
    local_store.write_raw_parquet(
        "BAD.T",
        pd.DataFrame({"Date": dates, "Close": [100.0, -1.0, float("nan")]}),
        root=tmp_path,
    )
    local_store.append_manifest_record(
        local_store.ManifestRecord(
            symbol="BAD.T",
            downloaded_start=date(2024, 1, 1),
            downloaded_end=date(2024, 1, 2),
            validated_start=date(2024, 1, 1),
            validated_end=date(2024, 1, 2),
            trading_days_expected=2,
            trading_days_actual=2,
            missing_count=0,
            missing_date_samples=[],
            last_synced=datetime(2024, 2, 1, tzinfo=timezone.utc),
            validation_status="ok",
            validation_issues=[],
            expected_dates_source="fixture",
        ),
        root=tmp_path,
    )

    raw_path = local_store.get_raw_path("BAD.T", root=tmp_path)
    pd.DataFrame({"Date": dates, "Close": [100.0, -1.0, float("nan")]}).to_parquet(raw_path, index=False)

    paths = run_data_quality_report(
        symbols=["BAD.T"],
        start="2024-01-01",
        end="2024-01-02",
        root=tmp_path,
        artifact_dir=tmp_path / "artifacts",
    )

    errors = pd.read_csv(paths["validation_errors"])
    assert "duplicate_timestamps" in set(errors["issue_code"])
    assert "non-finite_close_values" in set(errors["issue_code"])
    assert "non-positive_close_values" in set(errors["issue_code"])
```

- [ ] **Step 2: Run critical error tests to verify RED/GREEN**

Run:

```bash
uv run pytest tests/research/test_data_quality.py -q
```

Expected after Task 2 implementation: first test may pass; bad price test should reveal any normalization gaps. Fix only the reported gaps.

- [ ] **Step 3: Fix raw loading if duplicate dates are collapsed**

If `local_store.write_raw_parquet` removed duplicates in the fixture, keep the explicit `to_parquet` overwrite from the test. Ensure `_load_raw_frame()` does not drop duplicate dates after reading.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
uv run pytest tests/research/test_data_quality.py -q
```

Expected: PASS.

## Task 4: Add CLI Symbol and Universe Entry Points

**Files:**
- Modify: `src/research/data_quality.py`
- Modify: `tests/research/test_data_quality.py`

- [ ] **Step 1: Write failing CLI tests**

Add tests:

```python
def test_data_quality_cli_returns_nonzero_when_threshold_fails(tmp_path: Path, monkeypatch):
    from src.research import data_quality

    exit_code = data_quality.main(
        [
            "--symbols",
            "MISSING.T",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-05",
            "--root",
            str(tmp_path),
            "--artifact-dir",
            str(tmp_path / "artifacts"),
            "--max-critical-errors",
            "0",
        ]
    )

    assert exit_code == 1


def test_data_quality_cli_resolves_named_universe(tmp_path: Path, monkeypatch):
    from src.research import data_quality

    _write_symbol(tmp_path, "AAA.T", [100.0, 101.0, 102.0, 103.0, 104.0])
    monkeypatch.setattr(data_quality, "get_universe", lambda name: ["AAA.T"])

    exit_code = data_quality.main(
        [
            "--universe-name",
            "fixture",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-05",
            "--root",
            str(tmp_path),
            "--artifact-dir",
            str(tmp_path / "artifacts"),
        ]
    )

    assert exit_code == 0
```

- [ ] **Step 2: Run CLI tests to verify RED**

Run:

```bash
uv run pytest tests/research/test_data_quality.py::test_data_quality_cli_returns_nonzero_when_threshold_fails tests/research/test_data_quality.py::test_data_quality_cli_resolves_named_universe -q
```

Expected: FAIL because `main()` is not implemented.

- [ ] **Step 3: Implement CLI**

Add to `src/research/data_quality.py`:

```python
import argparse

from src.data.universe import get_universe


def _parse_symbols(value: str | None) -> list[str]:
    if not value:
        return []
    return [symbol.strip() for symbol in value.split(",") if symbol.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local research data-quality checks.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--symbols", help="Comma-separated symbols to validate")
    source.add_argument("--universe-name", help="Named universe from src.data.universe")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--max-critical-errors", type=int, default=0)
    args = parser.parse_args(argv)

    symbols = _parse_symbols(args.symbols) if args.symbols else get_universe(args.universe_name)
    paths = run_data_quality_report(
        symbols=symbols,
        start=args.start,
        end=args.end,
        root=args.root,
        artifact_dir=args.artifact_dir,
        thresholds=DataQualityThresholds(max_critical_errors=args.max_critical_errors),
    )

    summary = pd.read_json(paths["summary"], typ="series")
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI tests to verify GREEN**

Run:

```bash
uv run pytest tests/research/test_data_quality.py::test_data_quality_cli_returns_nonzero_when_threshold_fails tests/research/test_data_quality.py::test_data_quality_cli_resolves_named_universe -q
```

Expected: PASS.

## Task 5: Focused and Full Verification

**Files:**
- All touched files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
uv run pytest tests/research/test_artifacts.py::test_write_data_quality_run_persists_required_artifacts tests/research/test_data_quality.py -q
```

Expected: PASS.

- [ ] **Step 2: Run relevant existing tests**

Run:

```bash
uv run pytest tests/data/test_local_store.py tests/research/test_data_validation.py tests/research/test_artifacts.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full tests**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 4: Run diff checks**

Run:

```bash
git diff --check
git diff --stat
```

Expected: no whitespace errors; diff limited to data-quality module, artifact writer, tests, and docs.

- [ ] **Step 5: Commit implementation branch**

Run:

```bash
git add src/research/artifacts.py src/research/data_quality.py tests/research/test_artifacts.py tests/research/test_data_quality.py
git commit -m "feat: add local data quality artifacts"
```

Expected: commit succeeds.

- [ ] **Step 6: Finish branch**

Merge to `main`, remove the `codex/*` worktree, and delete the branch unless verification fails.
