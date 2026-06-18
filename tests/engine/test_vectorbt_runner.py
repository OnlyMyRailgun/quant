import pytest
import pandas as pd
import numpy as np
from src.engine.vectorbt_runner import run_backtest_vectorbt


def make_price_df(symbols, n_days, seed=42):
    """Create synthetic price DataFrames for testing."""
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    result = {}
    for sym in symbols:
        returns = np.random.randn(n_days) * 0.01
        close = 1000.0 * np.exp(np.cumsum(returns))
        result[sym] = pd.DataFrame({"Close": close}, index=dates)
    return result


class TestRunBacktestVectorbt:
    """Smoke tests for run_backtest_vectorbt()."""

    def test_run_backtest_vectorbt_returns_metrics_dict(self):
        """Returns dict with all 5 required keys; sharpe and return_pct are floats."""
        symbols = ["AAPL", "GOOGL", "MSFT"]
        data = make_price_df(symbols, 120)

        result = run_backtest_vectorbt(
            data_dfs=data,
            start="2024-05-01",
            end="2024-06-10",
            weights=(1.0, 1.0, 1.0),
        )

        assert isinstance(result, dict)
        assert "return_pct" in result
        assert "sharpe" in result
        assert "drawdown" in result
        assert "symbol_returns" in result
        assert "scores" in result
        assert isinstance(result["sharpe"], float)
        assert isinstance(result["return_pct"], float)

    def test_run_backtest_vectorbt_respects_evaluation_window(self):
        """Evaluation window produces different return_pct than full period."""
        symbols = ["AAPL", "GOOGL", "MSFT"]
        data = make_price_df(symbols, 200)

        start, end = "2024-05-01", "2024-07-31"

        result_full = run_backtest_vectorbt(
            data_dfs=data,
            start=start,
            end=end,
            weights=(1.0, 1.0, 1.0),
        )

        result_eval = run_backtest_vectorbt(
            data_dfs=data,
            start=start,
            end=end,
            weights=(1.0, 1.0, 1.0),
            evaluation_start="2024-06-01",
            evaluation_end="2024-06-30",
        )

        assert result_full["return_pct"] != result_eval["return_pct"]

    def test_run_backtest_vectorbt_rejects_nonzero_slippage_until_side_aware_orders_exist(self):
        """Non-zero slippage must not be silently accepted if it is not modeled."""
        data = make_price_df(["AAPL", "GOOGL", "MSFT"], 120)

        with pytest.raises(NotImplementedError, match="slippage"):
            run_backtest_vectorbt(
                data_dfs=data,
                start="2024-05-01",
                end="2024-06-10",
                weights=(1.0, 1.0, 1.0),
                slippage_pct=0.001,
            )
