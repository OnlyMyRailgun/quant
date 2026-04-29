import pytest
import pandas as pd
from src.engine.order_builder import build_orders


def make_scored(symbols, scores, is_top_n_flags):
    return pd.DataFrame({
        "symbol": symbols,
        "total_score": scores,
        "rank": range(1, len(symbols) + 1),
        "is_top_n": is_top_n_flags,
        "price": [100.0] * len(symbols),
    })


class TestBuildOrders:
    """Tests for build_orders()."""

    def test_build_orders_single_period(self):
        """3 symbols, top_n=2 -> 2 orders, each size=0.475."""
        date = pd.Timestamp("2024-01-31")
        scored = make_scored(
            symbols=["A", "B", "C"],
            scores=[0.9, 0.7, 0.5],
            is_top_n_flags=[True, True, False],
        )
        result = build_orders(
            period_scores={date: scored},
            top_n=2,
            commission_rate=0.001,
            slippage_pct=0.0005,
        )
        assert len(result) == 2
        assert list(result["symbol"]) == ["A", "B"]
        assert list(result["date"]) == [date, date]

        expected_size = 0.95 / 2
        assert result["size"].iloc[0] == pytest.approx(expected_size)
        assert result["size"].iloc[1] == pytest.approx(expected_size)

        expected_price = 100.0 * (1 - 0.0005)
        assert result["price"].iloc[0] == pytest.approx(expected_price)

        # Fees are 0.0 in build_orders — commission is applied as a scalar
        # rate in vectorbt's Portfolio.from_orders(fees=commission_rate)
        assert result["fees"].iloc[0] == 0.0

    def test_build_orders_empty_input(self):
        """Empty dict -> empty DataFrame with correct columns."""
        result = build_orders(
            period_scores={},
            top_n=5,
            commission_rate=0.001,
            slippage_pct=0.0005,
        )
        assert isinstance(result, pd.DataFrame)
        assert result.empty
        assert list(result.columns) == ["symbol", "date", "size", "price", "fees"]

    def test_build_orders_top_n_exceeds_available(self):
        """top_n=5 but only 2 symbols -> 2 orders, weight=0.475."""
        date = pd.Timestamp("2024-01-31")
        scored = make_scored(
            symbols=["A", "B"],
            scores=[0.9, 0.7],
            is_top_n_flags=[True, True],
        )
        result = build_orders(
            period_scores={date: scored},
            top_n=5,
            commission_rate=0.001,
            slippage_pct=0.0005,
        )
        assert len(result) == 2
        expected_size = 0.95 / 2
        assert result["size"].iloc[0] == pytest.approx(expected_size)

    def test_build_orders_multi_period(self):
        """2 periods, second period has different top-N."""
        date1 = pd.Timestamp("2024-01-31")
        date2 = pd.Timestamp("2024-02-29")
        scored1 = make_scored(
            symbols=["A", "B", "C", "D", "E"],
            scores=[0.9, 0.8, 0.7, 0.6, 0.5],
            is_top_n_flags=[True, True, True, False, False],
        )
        scored2 = make_scored(
            symbols=["A", "B", "C"],
            scores=[0.8, 0.7, 0.6],
            is_top_n_flags=[True, True, False],
        )
        result = build_orders(
            period_scores={date1: scored1, date2: scored2},
            top_n=3,
            commission_rate=0.001,
            slippage_pct=0.0005,
        )
        assert len(result) == 5

        period1 = result[result["date"] == date1]
        period2 = result[result["date"] == date2]
        assert len(period1) == 3
        assert len(period2) == 2
        assert period1["size"].iloc[0] == pytest.approx(0.95 / 3)
        assert period2["size"].iloc[0] == pytest.approx(0.95 / 2)

    def test_build_orders_slippage_applied(self):
        """slippage_pct=0.01 -> price=99.0 (from 100.0)."""
        date = pd.Timestamp("2024-01-31")
        scored = make_scored(
            symbols=["A", "B"],
            scores=[0.9, 0.7],
            is_top_n_flags=[True, True],
        )
        result = build_orders(
            period_scores={date: scored},
            top_n=2,
            commission_rate=0.001,
            slippage_pct=0.01,
        )
        assert result["price"].iloc[0] == pytest.approx(99.0)

    def test_build_orders_no_top_n_rows(self):
        """No is_top_n=True rows -> skip that date."""
        date = pd.Timestamp("2024-01-31")
        scored = make_scored(
            symbols=["A", "B"],
            scores=[0.5, 0.4],
            is_top_n_flags=[False, False],
        )
        result = build_orders(
            period_scores={date: scored},
            top_n=2,
            commission_rate=0.001,
            slippage_pct=0.0005,
        )
        assert result.empty

    def test_build_orders_empty_scored_dataframe(self):
        """Empty DataFrame for a date -> skip that date."""
        date = pd.Timestamp("2024-01-31")
        scored = pd.DataFrame(
            columns=["symbol", "total_score", "rank", "is_top_n", "price"]
        )
        result = build_orders(
            period_scores={date: scored},
            top_n=2,
            commission_rate=0.001,
            slippage_pct=0.0005,
        )
        assert result.empty
