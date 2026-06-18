from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.data.fundamental_loader import (
    _compute_book_value_per_share,
    _compute_roe,
    get_book_values,
)


def test_compute_book_value_per_share_returns_dict(monkeypatch):
    """BVPS is computed from equity divided by shares net of treasury stock."""
    fiscal_years = pd.to_datetime(["2024-03-31", "2023-03-31"])

    class FakeTicker:
        balance_sheet = pd.DataFrame(
            [
                [1_000.0, 900.0],
                [100.0, 100.0],
                [10.0, 0.0],
            ],
            index=[
                "Stockholders Equity",
                "Ordinary Shares Number",
                "Treasury Shares Number",
            ],
            columns=fiscal_years,
        )

    monkeypatch.setattr("src.data.fundamental_loader.yf.Ticker", lambda ticker: FakeTicker())

    result = _compute_book_value_per_share("7203.T")

    assert result == {
        "2024-03-31": 11.1111,
        "2023-03-31": 9.0,
    }


def test_get_book_values_no_date_returns_latest(tmp_path: Path, monkeypatch):
    """Without as_of_date, returns the most recent fiscal year's BVPS."""
    monkeypatch.setattr(
        "src.data.fundamental_loader.FUNDAMENTAL_CACHE",
        tmp_path / "fundamentals.json",
    )
    monkeypatch.setattr(
        "src.data.fundamental_loader._compute_book_value_per_share",
        lambda symbol: {"2022-03-31": 800.0, "2024-03-31": 1000.0},
    )

    result = get_book_values(["7203.T"], as_of_date=None)

    assert result["7203.T"] == 1000.0


def test_get_book_values_pit_filters_old_data(tmp_path: Path, monkeypatch):
    """With an old as_of_date, only old fiscal years should be available."""
    monkeypatch.setattr(
        "src.data.fundamental_loader.FUNDAMENTAL_CACHE",
        tmp_path / "fundamentals.json",
    )
    monkeypatch.setattr(
        "src.data.fundamental_loader._compute_book_value_per_share",
        lambda symbol: {"2022-03-31": 800.0, "2023-03-31": 900.0},
    )

    old_date = pd.Timestamp("2023-01-01")
    result = get_book_values(["7203.T"], as_of_date=old_date)

    assert result["7203.T"] == 800.0


def test_get_book_values_unknown_symbol(tmp_path: Path, monkeypatch):
    """Unknown symbol returns None."""
    monkeypatch.setattr(
        "src.data.fundamental_loader.FUNDAMENTAL_CACHE",
        tmp_path / "fundamentals.json",
    )
    monkeypatch.setattr(
        "src.data.fundamental_loader._compute_book_value_per_share",
        lambda symbol: {},
    )

    result = get_book_values(["ZZZZZZZZZZ.T"], as_of_date=pd.Timestamp("2024-01-01"))

    assert result["ZZZZZZZZZZ.T"] is None


def test_get_book_values_caches(tmp_path: Path, monkeypatch):
    """Results are cached to disk after first fetch."""
    monkeypatch.setattr(
        "src.data.fundamental_loader.FUNDAMENTAL_CACHE",
        tmp_path / "fundamentals.json",
    )

    monkeypatch.setattr(
        "src.data.fundamental_loader._compute_book_value_per_share",
        lambda symbol: {"2023-03-31": 900.0, "2024-03-31": 1000.0},
    )

    # First call should fetch through the compute function and write the cache.
    result1 = get_book_values(["7203.T"], as_of_date=None, force_refresh=True)
    assert result1["7203.T"] == 1000.0

    # Verify cache file was written
    assert (tmp_path / "fundamentals.json").exists()
    with open(tmp_path / "fundamentals.json") as f:
        cached = json.load(f)
    assert "7203.T" in cached
    assert cached["7203.T"] == {"2023-03-31": 900.0, "2024-03-31": 1000.0}


def test_compute_roe_uses_trailing_four_quarter_net_income(monkeypatch):
    quarter_ends = pd.to_datetime(
        ["2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31"]
    )

    class FakeTicker:
        quarterly_financials = pd.DataFrame(
            [[10.0, 20.0, 30.0, 40.0]],
            index=["Net Income"],
            columns=quarter_ends,
        )
        quarterly_balance_sheet = pd.DataFrame(
            [[500.0, 400.0, 300.0, 200.0]],
            index=["Stockholders Equity"],
            columns=quarter_ends,
        )

    monkeypatch.setattr("src.data.fundamental_loader.yf.Ticker", lambda ticker: FakeTicker())

    result = _compute_roe("FAKE.T")

    assert result == {"2024-12-31": 0.2}
