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
