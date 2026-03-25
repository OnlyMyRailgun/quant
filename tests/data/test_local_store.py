from __future__ import annotations

from datetime import date, datetime, timezone

import json
import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from src.data import local_store


def _make_manifest_record(
    symbol: str,
    last_synced: datetime,
    downloaded_start: date | None = None,
    downloaded_end: date | None = None,
    validated_start: date | None = date(2024, 1, 1),
    validated_end: date | None = date(2024, 1, 5),
    missing_count: int = 0,
    missing_date_samples: list[str] | None = None,
    status: str = "ok",
    issues: list[str] | None = None,
    trading_expected: int = 5,
    trading_actual: int = 5,
) -> local_store.ManifestRecord:
    return local_store.ManifestRecord(
        symbol=symbol,
        downloaded_start=downloaded_start or date(2024, 1, 1),
        downloaded_end=downloaded_end or date(2024, 1, 5),
        validated_start=validated_start,
        validated_end=validated_end,
        trading_days_expected=trading_expected,
        trading_days_actual=trading_actual,
        missing_count=missing_count,
        missing_date_samples=missing_date_samples or [],
        last_synced=last_synced,
        validation_status=status,
        validation_issues=issues or [],
    )


def test_write_raw_parquet_creates_file(tmp_path):
    df = pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=3, freq="B"),
            "Close": [100, 101, 102],
        }
    )

    path = local_store.write_raw_parquet("FOO", df, root=tmp_path)

    assert path.exists()
    loaded = pd.read_parquet(path)
    pdt.assert_frame_equal(loaded.reset_index(drop=True), df.sort_values("Date").reset_index(drop=True))


def test_write_raw_parquet_disallows_traversal(tmp_path):
    frame = pd.DataFrame(
        {"Date": pd.date_range("2024-01-01", periods=1, freq="B"), "Close": [1]}
    )

    with pytest.raises(ValueError):
        local_store.write_raw_parquet("../evil", frame, root=tmp_path)


def test_manifest_appends_to_shared_file(tmp_path):
    first = _make_manifest_record("SPY", datetime(2024, 3, 1, 9, 0, tzinfo=timezone.utc))
    second = _make_manifest_record("SPY", datetime(2024, 3, 2, 9, 0, tzinfo=timezone.utc))

    local_store.append_manifest_record(first, root=tmp_path)
    local_store.append_manifest_record(second, root=tmp_path)

    manifest = local_store.get_manifest_log_path(root=tmp_path)
    assert manifest.name == "manifest.jsonl"
    assert manifest.exists()
    assert manifest.read_text().count("\n") >= 2


def test_read_latest_manifest_prefers_last_synced_with_timezones(tmp_path):
    naive = _make_manifest_record("SPY", datetime(2024, 3, 1, 9, 0))
    aware = _make_manifest_record(
        "SPY", datetime(2024, 3, 2, 9, 0, tzinfo=timezone.utc)
    )

    local_store.append_manifest_record(naive, root=tmp_path)
    local_store.append_manifest_record(aware, root=tmp_path)

    latest = local_store.read_latest_manifest_record("SPY", root=tmp_path)

    assert latest is not None
    assert latest.last_synced == aware.last_synced
    assert latest.validation_status == aware.validation_status


def test_manifest_reads_skip_corrupt_lines(tmp_path):
    manifest_path = local_store.get_manifest_log_path(root=tmp_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    first = _make_manifest_record("SPY", datetime(2024, 3, 1, 9, 0, tzinfo=timezone.utc))
    second = _make_manifest_record("SPY", datetime(2024, 3, 2, 10, 0, tzinfo=timezone.utc))

    with manifest_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(first.to_dict(), ensure_ascii=False) + "\n")
        handle.write("{incomplete json\n")
        handle.write(json.dumps(second.to_dict(), ensure_ascii=False) + "\n")

    records = local_store.read_manifest_records("SPY", root=tmp_path)

    assert len(records) == 2
    assert records[0].last_synced < records[1].last_synced


def test_merge_symbol_frames_prefers_new_rows_on_overlap():
    existing = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "Close": [10, 20, 30],
        }
    )
    new = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "Close": [200, 300, 400],
        }
    )

    merged = local_store.merge_symbol_frames(existing, new)

    expected = pd.DataFrame(
        {
            "Date": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
            ),
            "Close": [10, 200, 300, 400],
        }
    )

    pdt.assert_frame_equal(merged.reset_index(drop=True), expected)


def test_build_validation_summary_detects_structural_issues():
    frame = pd.DataFrame(
        {
            "Date": ["2024-01-02", "2024-01-01", "2024-01-02"],
            "Close": [-1, np.nan, 5],
            "Volume": [100, 200, 300],
        }
    )

    summary = local_store.build_validation_summary(frame)

    assert summary["validation_status"] == "invalid"
    assert "duplicate_timestamps" in summary["validation_issues"]
    assert "non_monotonic_timestamps" in summary["validation_issues"]
    assert "non_finite_values" in summary["validation_issues"]
    assert "non_positive_close" in summary["validation_issues"]


def test_build_validation_summary_handles_bad_dates():
    frame = pd.DataFrame(
        {
            "Date": ["not-a-date", "2024-01-02"],
            "Close": [1, 2],
            "Volume": [10, 20],
        }
    )

    summary = local_store.build_validation_summary(frame)

    assert summary["validation_status"] == "invalid"
    assert "invalid_date_values" in summary["validation_issues"]


def test_build_validation_summary_warning_threshold():
    dates = pd.date_range("2024-01-01", periods=220, freq="B")
    missing = {dates[10], dates[20]}
    df = pd.DataFrame(
        {
            "Date": [d for d in dates if d not in missing],
            "Close": range(1, len(dates) - len(missing) + 1),
        }
    )

    summary = local_store.build_validation_summary(df)

    assert summary["missing_count"] == len(missing)
    assert summary["validation_status"] == "warning"


def test_build_validation_summary_invalid_ratio_threshold():
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    missing = dates[50]
    df = pd.DataFrame(
        {
            "Date": [d for d in dates if d != missing],
            "Close": range(1, len(dates)),
        }
    )
    summary = local_store.build_validation_summary(df)

    trading_expected = summary["trading_days_expected"]
    missing_ratio = summary["missing_count"] / trading_expected
    assert summary["missing_count"] == 1
    assert summary["validation_status"] == "invalid"
    assert missing_ratio >= 0.01


def test_build_validation_summary_handles_tz_aware_dates():
    dates = pd.date_range("2024-01-01", periods=50, freq="B", tz="UTC")
    missing = dates[10]
    frame = pd.DataFrame(
        {"Date": [d for d in dates if d != missing], "Close": range(len(dates) - 1)}
    )

    summary = local_store.build_validation_summary(frame)

    assert summary["missing_count"] == 1
    assert summary["missing_date_samples"][0] == missing.strftime("%Y-%m-%d")
