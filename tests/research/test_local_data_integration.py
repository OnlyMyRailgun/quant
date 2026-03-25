from __future__ import annotations

from datetime import date

import pandas as pd

import src.main as app_main
from src.data import local_store


def _make_fetch_frame(start: str, periods: int) -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="B")
    return pd.DataFrame(
        {"Close": [100.0 + i for i in range(len(index))], "Volume": range(100, 100 + len(index))},
        index=index,
    )


def _make_fetcher(frames: dict[str, pd.DataFrame]) -> local_store.Fetcher:
    def fetcher(symbol: str, start: str, end: str) -> pd.DataFrame:
        return frames[symbol].copy()

    return fetcher


def test_sync_universe_history_records_universe_union_expected_dates(tmp_path):
    frames = {
        "AAA": _make_fetch_frame("2024-01-01", 3),
        "BBB": _make_fetch_frame("2024-01-02", 4),
    }
    fetcher = _make_fetcher(frames)

    records = local_store.sync_universe_history(
        list(frames.keys()),
        "2024-01-01",
        "2024-01-05",
        root=tmp_path,
        fetcher=fetcher,
    )

    expected_union = {
        pd.Timestamp("2024-01-01"),
        pd.Timestamp("2024-01-02"),
        pd.Timestamp("2024-01-03"),
        pd.Timestamp("2024-01-04"),
        pd.Timestamp("2024-01-05"),
    }
    for record in records.values():
        assert record.expected_dates_source == "universe_union"
        assert record.trading_days_expected == len(expected_union)
        rows = len(frames[record.symbol])
        assert record.trading_days_actual == rows
        expected_missing = len(expected_union) - rows
        assert record.missing_count == expected_missing


def test_load_local_universe_integration_uses_cached_manifests(tmp_path):
    frames = {
        "AAA": _make_fetch_frame("2024-01-01", 7),
        "BBB": _make_fetch_frame("2024-01-01", 7),
    }
    fetcher = _make_fetcher(frames)

    local_store.sync_universe_history(
        list(frames.keys()),
        "2024-01-01",
        "2024-01-07",
        root=tmp_path,
        fetcher=fetcher,
    )

    universe = local_store.load_local_universe(
        list(frames.keys()),
        date(2024, 1, 2),
        date(2024, 1, 4),
        warmup=1,
        root=tmp_path,
    )

    assert set(universe) == set(frames.keys())
    for df in universe.values():
        assert not df.empty


def test_sync_entry_point_can_resolve_named_universe_and_sync(tmp_path):
    universe_name = "topix_top_10"
    symbols = set(app_main.get_universe(universe_name))

    def fetcher(symbol: str, start: str, end: str) -> pd.DataFrame:
        del start, end
        assert symbol in symbols
        return _make_fetch_frame("2024-01-01", 7)

    records = app_main.sync_named_universe(
        universe_name=universe_name,
        start_date="2024-01-01",
        end_date="2024-01-09",
        root=tmp_path,
        fetcher=fetcher,
    )

    assert set(records) == symbols
    assert local_store.get_manifest_log_path(root=tmp_path).exists()
