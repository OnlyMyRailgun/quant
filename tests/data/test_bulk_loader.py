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
