import pytest
import pandas as pd
from src.engine.runner import run_backtest
from src.strategies.multi_factor import UniversalMultiFactor
from src.strategies.sma_crossover import SmaCross

def test_run_backtest_execution():
    # Create fake price data
    dates = pd.date_range("2023-01-01", periods=50)
    data = pd.DataFrame({
        'Open': range(100, 150),
        'High': range(101, 151),
        'Low': range(99, 149),
        'Close': range(100, 150),
        'Volume': [1000] * 50
    }, index=dates)
    
    # Run backtest with fake data wrapped in a dict
    results = run_backtest({"FAKE.T": data}, SmaCross, initial_cash=1000000.0)
    
    # Verify results dict contains metrics
    assert "metrics" in results
    assert "final_value" in results["metrics"]
    assert results["metrics"]["final_value"] > 0


def test_run_backtest_simple_uses_strategy_kwargs_for_factor_weights(monkeypatch):
    dates = pd.date_range("2023-01-01", periods=50, freq="B")
    data = pd.DataFrame({"Close": [100.0] * len(dates)}, index=dates)
    captured = {}

    def fake_run_backtest_simple(**kwargs):
        captured.update(kwargs)
        return {
            "return_pct": 2.0,
            "sharpe": 0.5,
            "drawdown": -1.0,
            "symbol_returns": [],
            "scores": pd.DataFrame(),
        }

    monkeypatch.setattr(
        "src.engine.simple_runner.run_backtest_simple",
        fake_run_backtest_simple,
    )

    result = run_backtest(
        {"FAKE.T": data},
        UniversalMultiFactor,
        initial_cash=1_000_000.0,
        engine="simple",
        start="2023-01-01",
        end="2023-03-10",
        strategy_kwargs={
            "weight_mom": 0.2,
            "weight_vol": 0.4,
            "weight_rev": 0.6,
            "weight_val": 0.8,
            "weight_qual": 1.0,
            "top_n": 5,
            "artifact_dir": "ignored-by-simple-runner",
        },
    )

    assert captured["start"] == "2023-01-01"
    assert captured["end"] == "2023-03-10"
    assert captured["weights"] == (0.2, 0.4, 0.6, 0.8, 1.0)
    assert captured["top_n"] == 5
    assert result["metrics"]["final_value"] == pytest.approx(1_020_000.0)
