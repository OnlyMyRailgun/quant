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


def test_score_research_universe_defaults_use_broader_portfolio_and_disable_reversion():
    dates = pd.date_range("2021-01-01", periods=300)
    data_dfs = {
        f"{idx:03d}.T": pd.DataFrame({"Close": [100.0 + idx] * 300}, index=dates)
        for idx in range(12)
    }

    results = score_research_universe(data_dfs, momentum_definition="12_1")

    assert int(results["is_top_n"].sum()) == 10
    assert results["rev_contribution"].tolist() == [0.0] * len(results)


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


def test_score_research_universe_applies_quality_factor_when_roe_values_are_supplied():
    dates = pd.date_range("2021-01-01", periods=300)
    flat = pd.DataFrame({"Close": [100.0] * 300}, index=dates)
    data_dfs = {
        "LOW_ROE.T": flat.copy(),
        "HIGH_ROE.T": flat.copy(),
    }

    results = score_research_universe(
        data_dfs,
        top_n=1,
        weight_mom=0.0,
        weight_vol=0.0,
        weight_rev=0.0,
        weight_qual=1.0,
        momentum_definition="12_1",
        roe_values={"LOW_ROE.T": 0.05, "HIGH_ROE.T": 0.20},
    )

    assert results["symbol"].tolist() == ["HIGH_ROE.T", "LOW_ROE.T"]
    assert "qual_z" in results.columns
    assert "qual_contribution" in results.columns
    assert results.loc[0, "qual_contribution"] > results.loc[1, "qual_contribution"]
    assert bool(results.loc[0, "is_top_n"]) is True
