from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import Mock

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
    expected_dates_source: str | None = None,
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
        expected_dates_source=expected_dates_source,
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


def _make_fetch_frame(index_dates: list[str] | pd.DatetimeIndex) -> pd.DataFrame:
    idx = pd.to_datetime(index_dates)
    return pd.DataFrame(
        {"Close": [100.0 + i for i in range(len(idx))], "Volume": range(10, 10 + len(idx))},
        index=idx,
    )


def test_sync_symbol_history_creates_raw_and_manifest(tmp_path):
    fetched = _make_fetch_frame(pd.date_range("2024-01-01", periods=2, freq="B"))
    fetcher = Mock(return_value=fetched)

    record = local_store.sync_symbol_history(
        "FOO",
        "2024-01-01",
        "2024-01-02",
        root=tmp_path,
        fetcher=fetcher,
    )

    raw_path = local_store.get_raw_path("FOO", root=tmp_path)
    assert raw_path.exists()
    stored = pd.read_parquet(raw_path)
    assert len(stored) == len(fetched)
    assert "Date" in stored.columns
    assert record.validation_status == "ok"
    assert record.validation_issues == []
    records = local_store.read_manifest_records("FOO", root=tmp_path)
    assert len(records) == 1
    assert records[0].validation_status == "ok"
    fetcher.assert_called_once_with("FOO", "2024-01-01", "2024-01-02")


def test_sync_symbol_history_overlapping_range_replaces_overlap(tmp_path):
    existing = pd.DataFrame(
        {
            "Date": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-03"]
            ),
            "Close": [10, 20, 30],
            "Volume": [1, 2, 3],
        }
    )
    local_store.write_raw_parquet("FOO", existing, root=tmp_path)

    overlap = pd.DataFrame(
        {
            "Close": [200, 300, 400],
            "Volume": [20, 30, 40],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
    )
    fetcher = Mock(return_value=overlap)

    record = local_store.sync_symbol_history(
        "FOO",
        "2024-01-02",
        "2024-01-04",
        root=tmp_path,
        fetcher=fetcher,
    )

    stored = pd.read_parquet(local_store.get_raw_path("FOO", root=tmp_path))
    expected = pd.DataFrame(
        {
            "Date": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
            ),
            "Close": [10, 200, 300, 400],
            "Volume": [1, 20, 30, 40],
        }
    )
    pdt.assert_frame_equal(
        stored.sort_values("Date").reset_index(drop=True),
        expected.sort_values("Date").reset_index(drop=True),
    )
    assert record.validation_status == "ok"


def test_sync_symbol_history_invalid_data_preserves_existing(tmp_path):
    initial = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "Close": [10, 20],
            "Volume": [1, 2],
        }
    )
    local_store.write_raw_parquet("FOO", initial, root=tmp_path)

    invalid = pd.DataFrame(
        {"Close": [-5.0, -3.0], "Volume": [5, 6]},
        index=pd.to_datetime(["2024-01-03", "2024-01-04"]),
    )
    fetcher = Mock(return_value=invalid)

    record = local_store.sync_symbol_history(
        "FOO",
        "2024-01-03",
        "2024-01-04",
        root=tmp_path,
        fetcher=fetcher,
    )

    stored = pd.read_parquet(local_store.get_raw_path("FOO", root=tmp_path))
    expected_invalid = invalid.reset_index().rename(columns={"index": "Date"})
    expected = pd.concat([initial, expected_invalid], ignore_index=True)
    pdt.assert_frame_equal(
        stored.sort_values("Date").reset_index(drop=True),
        expected.sort_values("Date").reset_index(drop=True),
    )
    assert record.validation_status == "invalid"
    assert record.validated_start is None
    assert record.validated_end is None
    assert "non_positive_close" in record.validation_issues
    records = local_store.read_manifest_records("FOO", root=tmp_path)
    assert len(records) == 1


def test_sync_symbol_history_invalid_missing_data(tmp_path):
    dates = pd.date_range("2024-01-01", periods=50, freq="B")
    missing_dates = {dates[5], dates[15], dates[25]}
    provided = [dt for dt in dates if dt not in missing_dates]
    fetched = pd.DataFrame(
        {"Close": range(len(provided)), "Volume": range(len(provided))},
        index=pd.to_datetime(provided),
    )
    fetcher = Mock(return_value=fetched)

    record = local_store.sync_symbol_history(
        "BAR",
        dates[0],
        dates[-1],
        root=tmp_path,
        fetcher=fetcher,
    )

    stored = pd.read_parquet(local_store.get_raw_path("BAR", root=tmp_path))
    assert len(stored) == len(provided)
    assert record.validation_status == "invalid"
    assert record.validated_start is None
    assert record.validated_end is None
    assert "missing_data" in record.validation_issues


def test_load_local_symbol_returns_range_with_warmup(tmp_path):
    dates = pd.date_range("2024-01-01", periods=12, freq="B")
    frame = pd.DataFrame({"Date": dates, "Close": range(len(dates))})
    local_store.write_raw_parquet("FOO", frame, root=tmp_path)

    manifest = _make_manifest_record(
        "FOO",
        datetime(2024, 3, 1, 9, 0, tzinfo=timezone.utc),
        validated_start=dates[0].date(),
        validated_end=dates[-1].date(),
    )
    local_store.append_manifest_record(manifest, root=tmp_path)

    start = dates[5]
    end = dates[8]
    loaded = local_store.load_local_symbol("FOO", start.date(), end.date(), warmup=2, root=tmp_path)

    expected = dates[3:9]
    actual = pd.to_datetime(loaded["Date"]).dt.tz_convert(timezone.utc).dt.tz_localize(None).dt.normalize()
    assert len(loaded) == len(expected)
    assert actual.tolist() == expected.normalize().tolist()


def test_load_local_symbol_prefers_latest_manifest_record(tmp_path):
    dates = pd.date_range("2024-01-01", periods=6, freq="B")
    frame = pd.DataFrame({"Date": dates, "Close": range(len(dates))})
    local_store.write_raw_parquet("FOO", frame, root=tmp_path)

    old_manifest = _make_manifest_record(
        "FOO",
        datetime(2024, 3, 1, 9, 0, tzinfo=timezone.utc),
        validated_start=dates[0].date(),
        validated_end=dates[2].date(),
    )
    new_manifest = _make_manifest_record(
        "FOO",
        datetime(2024, 3, 2, 9, 0, tzinfo=timezone.utc),
        validated_start=dates[0].date(),
        validated_end=dates[-1].date(),
    )
    local_store.append_manifest_record(old_manifest, root=tmp_path)
    local_store.append_manifest_record(new_manifest, root=tmp_path)

    loaded = local_store.load_local_symbol(
        "FOO",
        dates[3].date(),
        dates[-1].date(),
        root=tmp_path,
    )

    assert not loaded.empty
    assert pd.to_datetime(loaded["Date"]).dt.date.max() == dates[-1].date()


def test_load_local_universe_rejects_invalid_symbols(tmp_path):
    with pytest.raises(ValueError):
        local_store.load_local_universe(
            ["../evil"],
            "2024-01-01",
            "2024-01-02",
            root=tmp_path,
        )


def test_load_local_universe_returns_requested_range_with_warmup(tmp_path):
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    frame = pd.DataFrame({"Date": dates, "Close": range(len(dates))})
    local_store.write_raw_parquet("FOO", frame, root=tmp_path)

    manifest = _make_manifest_record(
        "FOO",
        datetime(2024, 3, 1, 9, 0, tzinfo=timezone.utc),
        validated_start=dates[0].date(),
        validated_end=dates[-1].date(),
    )
    local_store.append_manifest_record(manifest, root=tmp_path)

    universe = local_store.load_local_universe(
        ["FOO"],
        dates[3].date(),
        dates[5].date(),
        warmup=1,
        root=tmp_path,
    )

    assert "FOO" in universe
    loaded = universe["FOO"]
    expected = dates[2:6]
    actual = pd.to_datetime(loaded["Date"]).dt.tz_convert(timezone.utc).dt.tz_localize(None).dt.normalize()
    assert len(loaded) == len(expected)
    assert actual.tolist() == expected.normalize().tolist()


def test_load_local_symbol_enforces_validation_status(tmp_path):
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    frame = pd.DataFrame({"Date": dates, "Close": range(len(dates))})
    local_store.write_raw_parquet("FOO", frame, root=tmp_path)

    warning_manifest = _make_manifest_record(
        "FOO",
        datetime(2024, 3, 1, 9, 0, tzinfo=timezone.utc),
        validated_start=dates[0].date(),
        validated_end=dates[-1].date(),
        status="warning",
    )
    local_store.append_manifest_record(warning_manifest, root=tmp_path)

    with pytest.raises(ValueError):
        local_store.load_local_symbol(
            "FOO",
            dates[1].date(),
            dates[3].date(),
            root=tmp_path,
        )

    allowed = local_store.load_local_symbol(
        "FOO",
        dates[1].date(),
        dates[3].date(),
        allowed_validation_statuses=("ok", "warning"),
        root=tmp_path,
    )
    assert not allowed.empty


def test_load_local_symbol_requires_validated_coverage(tmp_path):
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    frame = pd.DataFrame({"Date": dates, "Close": range(len(dates))})
    local_store.write_raw_parquet("FOO", frame, root=tmp_path)

    minimal_manifest = _make_manifest_record(
        "FOO",
        datetime(2024, 3, 1, 9, 0, tzinfo=timezone.utc),
        validated_start=None,
        validated_end=None,
        status="invalid",
    )
    local_store.append_manifest_record(minimal_manifest, root=tmp_path)

    with pytest.raises(local_store.LocalDataSyncRequiredError):
        local_store.load_local_symbol(
            "FOO",
            dates[1].date(),
            dates[3].date(),
            root=tmp_path,
        )


def test_load_local_symbol_rejects_invalid_symbol(tmp_path):
    with pytest.raises(ValueError):
        local_store.load_local_symbol("../evil", "2024-01-01", "2024-01-02", root=tmp_path)


def test_load_local_symbol_requires_manifest(tmp_path):
    dates = pd.date_range("2024-01-01", periods=3, freq="B")
    frame = pd.DataFrame({"Date": dates, "Close": range(len(dates))})
    local_store.write_raw_parquet("FOO", frame, root=tmp_path)

    with pytest.raises(local_store.LocalDataSyncRequiredError):
        local_store.load_local_symbol("FOO", dates[0].date(), dates[-1].date(), root=tmp_path)


def test_load_local_symbol_request_outside_validated_range(tmp_path):
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    frame = pd.DataFrame({"Date": dates, "Close": range(len(dates))})
    local_store.write_raw_parquet("FOO", frame, root=tmp_path)

    manifest = _make_manifest_record(
        "FOO",
        datetime(2024, 3, 1, 9, 0, tzinfo=timezone.utc),
        validated_start=dates[1].date(),
        validated_end=dates[3].date(),
    )
    local_store.append_manifest_record(manifest, root=tmp_path)

    with pytest.raises(local_store.LocalDataSyncRequiredError):
        local_store.load_local_symbol("FOO", dates[0].date(), dates[3].date(), root=tmp_path)

    with pytest.raises(local_store.LocalDataSyncRequiredError):
        local_store.load_local_symbol("FOO", dates[1].date(), dates[-1].date(), root=tmp_path)


def test_load_local_symbol_handles_tz_aware_dates(tmp_path):
    dates = pd.date_range("2024-01-01", periods=5, freq="B", tz="Asia/Tokyo")
    frame = pd.DataFrame({"Date": dates, "Close": range(len(dates))})
    local_store.write_raw_parquet("FOO", frame, root=tmp_path)

    manifest = _make_manifest_record(
        "FOO",
        datetime(2024, 3, 1, 9, 0, tzinfo=timezone.utc),
        validated_start=dates[0].date(),
        validated_end=dates[-1].date(),
    )
    local_store.append_manifest_record(manifest, root=tmp_path)

    loaded = local_store.load_local_symbol("FOO", dates[1].date(), dates[3].date(), root=tmp_path)
    assert not loaded.empty
    assert pd.to_datetime(loaded["Date"]).dt.tz_convert(timezone.utc).dt.date.max() == dates[3].date()


def test_load_local_symbol_latest_invalid_manifest_blocks_load(tmp_path):
    dates = pd.date_range("2024-01-01", periods=4, freq="B")
    frame = pd.DataFrame({"Date": dates, "Close": range(len(dates))})
    local_store.write_raw_parquet("FOO", frame, root=tmp_path)

    first = _make_manifest_record(
        "FOO",
        datetime(2024, 3, 1, 9, 0, tzinfo=timezone.utc),
        validated_start=dates[0].date(),
        validated_end=dates[-1].date(),
    )
    second = _make_manifest_record(
        "FOO",
        datetime(2024, 3, 2, 9, 0, tzinfo=timezone.utc),
        validated_start=None,
        validated_end=None,
        status="invalid",
    )
    local_store.append_manifest_record(first, root=tmp_path)
    local_store.append_manifest_record(second, root=tmp_path)

    with pytest.raises(local_store.LocalDataSyncRequiredError):
        local_store.load_local_symbol("FOO", dates[0].date(), dates[-1].date(), root=tmp_path)


def test_load_local_symbol_handles_non_trading_start(tmp_path):
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    frame = pd.DataFrame({"Date": dates, "Close": [1, 2, 3]})
    local_store.write_raw_parquet("FOO", frame, root=tmp_path)

    manifest = _make_manifest_record(
        "FOO",
        datetime(2024, 3, 1, 9, 0, tzinfo=timezone.utc),
        validated_start=date(2024, 1, 1),
        validated_end=date(2024, 1, 5),
    )
    local_store.append_manifest_record(manifest, root=tmp_path)

    loaded = local_store.load_local_symbol(
        "FOO",
        date(2024, 1, 1),
        date(2024, 1, 4),
        warmup=1,
        root=tmp_path,
    )

    actual_dates = pd.to_datetime(loaded["Date"]).dt.tz_convert(timezone.utc).dt.tz_localize(None).dt.normalize()
    assert actual_dates.iloc[0] == pd.Timestamp("2024-01-02")
    assert actual_dates.iloc[1] == pd.Timestamp("2024-01-03")
