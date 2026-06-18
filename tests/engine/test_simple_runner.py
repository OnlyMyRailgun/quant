import pandas as pd
import pytest

from src.engine.simple_runner import run_backtest_simple


def test_simple_runner_evaluation_return_uses_first_evaluation_equity_as_base():
    dates = pd.bdate_range("2024-01-01", "2024-08-02")
    prices = []
    for date in dates:
        if date < pd.Timestamp("2024-07-01"):
            prices.append(100.0)
        elif date < pd.Timestamp("2024-08-01"):
            prices.append(200.0)
        else:
            prices.append(100.0)

    data = {
        "AAA.T": pd.DataFrame({"Close": prices}, index=dates),
    }

    result = run_backtest_simple(
        data_dfs=data,
        start="2024-06-03",
        end="2024-08-02",
        evaluation_start="2024-07-01",
        evaluation_end="2024-08-02",
        weights=(1.0, 0.0, 0.0),
        top_n=1,
        fee_rate=0.0,
    )

    # 2024-07-01 equity: 1,950,000 after the warmup-month position doubles.
    # 2024-08-01 equity: 1,030,000 after the validation-month price halves.
    expected_return = (1_030_000.0 / 1_950_000.0 - 1.0) * 100.0
    assert result["return_pct"] == pytest.approx(expected_return, abs=0.0001)


def test_simple_runner_resolves_book_values_by_execution_date():
    dates = pd.bdate_range("2024-01-01", "2024-07-03")
    data = {
        "AAA.T": pd.DataFrame({"Close": [100.0] * len(dates)}, index=dates),
        "BBB.T": pd.DataFrame({"Close": [100.0] * len(dates)}, index=dates),
    }

    def book_values_as_of(as_of_date):
        if as_of_date < pd.Timestamp("2024-07-01"):
            return {"AAA.T": 100.0, "BBB.T": 50.0}
        return {"AAA.T": 50.0, "BBB.T": 100.0}

    result = run_backtest_simple(
        data_dfs=data,
        start="2024-06-03",
        end="2024-07-03",
        weights=(0.0, 0.0, 0.0, 1.0),
        top_n=1,
        fee_rate=0.0,
        book_values=book_values_as_of,
    )

    assert result["scores"].iloc[0]["symbol"] == "BBB.T"
