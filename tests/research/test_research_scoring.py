import pandas as pd
import pytest
import numpy as np
from src.research.research_scoring import score_research_universe

def test_score_research_universe_exists():
    assert score_research_universe is not None

def test_score_research_universe_supports_12_1_momentum_definition():
    # 12-1 momentum: (Close_t / Close_{t-251}) - 1, but we skip the last 21 days
    # So it uses t-251 and t-21
    # Total history needed: min 252 days if we want 12-1
    dates = pd.date_range("2021-01-01", periods=300)
    
    # We want to check 12-1 momentum:
    # Latest day (t): 251
    # Skip recent month (21 days): 251 - 21 = 230
    # Lookback 12 months (252 days) from start: 251 - 251 = 0
    # momentum = (Price[230] / Price[0]) - 1
    
    prices = [100.0] * 300
    prices[0] = 100.0   # t-251
    prices[230] = 150.0  # t-21
    prices[251] = 160.0  # latest (t)
    
    df = pd.DataFrame({"Close": prices}, index=dates)
    # We pass the full 252 days slice
    data_dfs = {"TEST": df.iloc[:252]}
    
    # Calculate expected 12-1 momentum: (150 - 100) / 100 = 0.5
    results = score_research_universe(data_dfs, momentum_definition="12_1")
    
    assert results is not None
    assert not results.empty
    assert results.iloc[0]["symbol"] == "TEST"
    assert results.iloc[0]["mom_raw"] == pytest.approx(0.5)

def test_score_research_universe_skips_symbols_without_12_1_history():
    dates = pd.date_range("2021-01-01", periods=200) # Less than 252
    df = pd.DataFrame({"Close": [100.0] * 200}, index=dates)
    data_dfs = {"SHORT": df}
    
    results = score_research_universe(data_dfs, momentum_definition="12_1")
    assert results.empty

def test_score_research_universe_preserves_multi_factor_score_shape():
    dates = pd.date_range("2021-01-01", periods=300)
    df = pd.DataFrame({"Close": [100.0] * 300}, index=dates)
    data_dfs = {"T1": df, "T2": df}
    
    results = score_research_universe(data_dfs, momentum_definition="12_1")
    
    expected_columns = [
        "symbol", "price", "mom_raw", "vol_raw", "rev_raw",
        "mom_z", "vol_z", "rev_z",
        "mom_contribution", "vol_contribution", "rev_contribution",
        "total_score", "rank", "is_top_n"
    ]
    for col in expected_columns:
        assert col in results.columns
