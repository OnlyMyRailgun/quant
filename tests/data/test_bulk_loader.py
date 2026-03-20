import pandas as pd
from unittest.mock import patch
from src.data.bulk_loader import fetch_universe, CACHE_DIR

@patch('src.data.bulk_loader.fetch_daily_data')
def test_fetch_universe(mock_fetch):
    # Setup mock dataframe
    mock_df = pd.DataFrame({"Close": [100, 101]}, index=pd.date_range("2023-01-01", periods=2))
    mock_fetch.return_value = mock_df

    # Test cache miss
    symbol = "TEST.T"
    cache_path = CACHE_DIR / f"{symbol}.parquet"
    if cache_path.exists():
        cache_path.unlink()

    dfs = fetch_universe([symbol], "2023-01-01", "2023-01-02")
    assert symbol in dfs
    assert not dfs[symbol].empty
    assert mock_fetch.call_count == 1
    assert cache_path.exists()

    # Test cache hit
    mock_fetch.reset_mock()
    dfs2 = fetch_universe([symbol], "2023-01-01", "2023-01-02")
    assert symbol in dfs2
    assert not dfs2[symbol].empty
    assert mock_fetch.call_count == 0  # Should not be called on cache hit

    # Cleanup
    if cache_path.exists():
        cache_path.unlink()


@patch('src.data.bulk_loader.fetch_daily_data')
def test_fetch_universe_refreshes_cache_when_left_side_of_requested_range_is_missing(mock_fetch):
    symbol = "TEST_LEFT.T"
    cache_path = CACHE_DIR / f"{symbol}.parquet"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cached_df = pd.DataFrame(
        {"Close": [110, 111]},
        index=pd.to_datetime(["2023-01-03", "2023-01-04"]),
    )
    cached_df.to_parquet(cache_path)

    fetched_df = pd.DataFrame(
        {"Close": [100, 101]},
        index=pd.to_datetime(["2023-01-01", "2023-01-02"]),
    )
    mock_fetch.return_value = fetched_df

    dfs = fetch_universe([symbol], "2023-01-01", "2023-01-04")

    assert symbol in dfs
    assert dfs[symbol].index.min() == pd.Timestamp("2023-01-01")
    assert dfs[symbol].index.max() == pd.Timestamp("2023-01-04")
    assert len(dfs[symbol]) == 4
    assert mock_fetch.call_count == 1
    assert mock_fetch.call_args[0] == (symbol, "2023-01-01", "2023-01-04")

    merged = pd.read_parquet(cache_path)
    assert merged.index.min() == pd.Timestamp("2023-01-01")
    assert merged.index.max() == pd.Timestamp("2023-01-04")
    assert len(merged) == 4

    if cache_path.exists():
        cache_path.unlink()


@patch('src.data.bulk_loader.fetch_daily_data')
def test_fetch_universe_refreshes_cache_when_right_side_of_requested_range_is_missing(mock_fetch):
    symbol = "TEST_RIGHT.T"
    cache_path = CACHE_DIR / f"{symbol}.parquet"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cached_df = pd.DataFrame(
        {"Close": [100, 101]},
        index=pd.to_datetime(["2023-01-01", "2023-01-02"]),
    )
    cached_df.to_parquet(cache_path)

    fetched_df = pd.DataFrame(
        {"Close": [110, 111]},
        index=pd.to_datetime(["2023-01-03", "2023-01-04"]),
    )
    mock_fetch.return_value = fetched_df

    dfs = fetch_universe([symbol], "2023-01-01", "2023-01-04")

    assert symbol in dfs
    assert dfs[symbol].index.min() == pd.Timestamp("2023-01-01")
    assert dfs[symbol].index.max() == pd.Timestamp("2023-01-04")
    assert len(dfs[symbol]) == 4
    assert mock_fetch.call_count == 1

    merged = pd.read_parquet(cache_path)
    assert merged.index.min() == pd.Timestamp("2023-01-01")
    assert merged.index.max() == pd.Timestamp("2023-01-04")
    assert len(merged) == 4

    if cache_path.exists():
        cache_path.unlink()


@patch('src.data.bulk_loader.fetch_daily_data')
def test_fetch_universe_skips_invalid_symbols_and_reports_reason(mock_fetch, capsys):
    valid_symbol = "VALID.T"
    invalid_symbol = "INVALID.T"
    valid_df = pd.DataFrame({"Close": [100.0, 101.0]}, index=pd.date_range("2024-01-01", periods=2))
    invalid_df = pd.DataFrame({"Close": [100.0, 101.0]}, index=pd.to_datetime(["2024-01-02", "2024-01-01"]))
    mock_fetch.side_effect = [valid_df, invalid_df]

    for symbol in (valid_symbol, invalid_symbol):
        cache_path = CACHE_DIR / f"{symbol}.parquet"
        if cache_path.exists():
            cache_path.unlink()

    dfs = fetch_universe([valid_symbol, invalid_symbol], "2024-01-01", "2024-01-02")
    captured = capsys.readouterr()

    assert valid_symbol in dfs
    assert invalid_symbol not in dfs
    assert "INVALID.T" in captured.out
    assert "unsorted timestamps" in captured.out


@patch('src.data.bulk_loader.fetch_daily_data')
def test_fetch_universe_does_not_persist_invalid_refresh_data_on_cache_hit(mock_fetch, capsys):
    symbol = "TEST_INVALID_REFRESH.T"
    cache_path = CACHE_DIR / f"{symbol}.parquet"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cached_df = pd.DataFrame(
        {"Close": [100.0, 101.0]},
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )
    cached_df.to_parquet(cache_path)

    fetched_df = pd.DataFrame(
        {"Close": [-1.0, 103.0]},
        index=pd.to_datetime(["2024-01-03", "2024-01-04"]),
    )
    mock_fetch.return_value = fetched_df

    dfs = fetch_universe([symbol], "2024-01-01", "2024-01-04")
    captured = capsys.readouterr()

    assert symbol not in dfs
    assert "non-positive close values" in captured.out

    persisted = pd.read_parquet(cache_path)
    pd.testing.assert_frame_equal(persisted, cached_df)

    if cache_path.exists():
        cache_path.unlink()
