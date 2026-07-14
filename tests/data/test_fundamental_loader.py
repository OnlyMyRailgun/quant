from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.data.fundamental_loader import (
    _compute_book_value_per_share,
    _compute_roe,
    get_book_values,
    get_market_caps,
    _compute_shares_outstanding,
    get_ev_ebit,
)


def test_empty_result_is_not_cached_so_transient_failure_can_recover(
    tmp_path: Path, monkeypatch
):
    """A transient fetch failure returning {} must not be persisted as a
    permanent empty cache entry; a later successful fetch must be attempted."""
    monkeypatch.setattr(
        "src.data.fundamental_loader.FUNDAMENTAL_CACHE",
        tmp_path / "fundamentals.json",
    )

    calls = {"n": 0}

    def flaky_compute(symbol):
        calls["n"] += 1
        if calls["n"] == 1:
            return {}  # transient failure
        return {"2024-03-31": 1000.0}

    monkeypatch.setattr(
        "src.data.fundamental_loader._compute_book_value_per_share",
        flaky_compute,
    )

    first = get_book_values(["7203.T"], as_of_date=None)
    assert first["7203.T"] is None

    # Empty result must NOT have been persisted as a permanent entry.
    if (tmp_path / "fundamentals.json").exists():
        with open(tmp_path / "fundamentals.json") as f:
            cached = json.load(f)
        assert cached.get("7203.T") in (None, {}) and "7203.T" not in {
            k: v for k, v in cached.items() if v
        }

    # Second call (no force_refresh) must retry the fetch and now succeed.
    second = get_book_values(["7203.T"], as_of_date=None)
    assert second["7203.T"] == 1000.0


def test_compute_roe_rejects_ttm_window_that_spans_more_than_a_year(monkeypatch):
    """When income and balance-sheet quarters don't align, the 4-element
    intersection window can cover >4 calendar quarters; such a window must not
    be treated as a valid TTM figure."""
    # Income has a gap (missing 2024-06-30); balance sheet is complete.
    income_quarters = pd.to_datetime(
        ["2024-12-31", "2024-09-30", "2024-03-31", "2023-12-31"]
    )
    bs_quarters = pd.to_datetime(
        ["2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31", "2023-12-31"]
    )

    class FakeTicker:
        quarterly_financials = pd.DataFrame(
            [[10.0, 20.0, 30.0, 40.0]],
            index=["Net Income"],
            columns=income_quarters,
        )
        quarterly_balance_sheet = pd.DataFrame(
            [[500.0, 400.0, 350.0, 300.0, 200.0]],
            index=["Stockholders Equity"],
            columns=bs_quarters,
        )

    monkeypatch.setattr(
        "src.data.fundamental_loader.yf.Ticker", lambda ticker: FakeTicker()
    )

    result = _compute_roe("FAKE.T")

    # The newest window [2024-12-31, 2024-09-30, 2024-03-31, 2023-12-31] spans
    # a full year of gaps (missing Q ending 2024-06-30). It must NOT be emitted
    # as a valid TTM ROE, because the summed income is not a true trailing-12m.
    assert "2024-12-31" not in result


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


def test_compute_shares_outstanding_nets_treasury(monkeypatch):
    fiscal_years = pd.to_datetime(["2024-03-31"])

    class FakeTicker:
        balance_sheet = pd.DataFrame(
            [[100.0], [10.0]],
            index=["Ordinary Shares Number", "Treasury Shares Number"],
            columns=fiscal_years,
        )

    monkeypatch.setattr("src.data.fundamental_loader.yf.Ticker", lambda t: FakeTicker())
    assert _compute_shares_outstanding("7203.T") == {"2024-03-31": 90.0}


def test_get_market_caps_pit_and_price(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.data.fundamental_loader.MARKET_CAP_CACHE", tmp_path / "shares.json"
    )
    monkeypatch.setattr(
        "src.data.fundamental_loader._compute_shares_outstanding",
        lambda s: {"2022-03-31": 100.0, "2023-03-31": 200.0},
    )
    # as_of before 2023 fiscal publication -> uses 2022 shares (100) x price 5 = 500
    result = get_market_caps(
        ["7203.T"], prices={"7203.T": 5.0}, as_of_date=pd.Timestamp("2023-01-01")
    )
    assert result["7203.T"] == 500.0


def test_get_market_caps_force_refresh_total_failure_preserves_cache(
    tmp_path: Path, monkeypatch
):
    """When force_refresh=True and every symbol's fetch fails, the existing
    cache file on disk must NOT be overwritten with an empty dict."""
    cache_path = tmp_path / "shares.json"
    monkeypatch.setattr(
        "src.data.fundamental_loader.MARKET_CAP_CACHE", cache_path
    )

    # Pre-write a valid cache file for 7203.T
    valid_cache = {"7203.T": {"2024-03-31": 100.0}}
    cache_path.write_text(json.dumps(valid_cache))

    # Simulate total fetch failure for every symbol
    monkeypatch.setattr(
        "src.data.fundamental_loader._compute_shares_outstanding",
        lambda s: {},
    )

    get_market_caps(
        ["7203.T"],
        prices={"7203.T": 5.0},
        as_of_date=None,
        force_refresh=True,
    )

    # The cache file must still contain the original valid data
    with open(cache_path) as f:
        on_disk = json.load(f)
    assert on_disk.get("7203.T") == {"2024-03-31": 100.0}, (
        "Cache was wiped to {} on total fetch failure — existing data must be preserved"
    )


def test_get_ev_ebit_negative_ebit_returns_none(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.data.fundamental_loader.EV_EBIT_CACHE", tmp_path / "evebit.json"
    )
    monkeypatch.setattr(
        "src.data.fundamental_loader._compute_ev_ebit_inputs",
        lambda s: {"2024-03-31": {"ebit": -50.0, "debt": 100.0, "cash": 10.0, "shares": 100.0}},
    )
    result = get_ev_ebit(["X.T"], prices={"X.T": 5.0}, as_of_date=None)
    assert result["X.T"] is None


def test_get_ev_ebit_computes_ratio(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.data.fundamental_loader.EV_EBIT_CACHE", tmp_path / "evebit.json"
    )
    monkeypatch.setattr(
        "src.data.fundamental_loader._compute_ev_ebit_inputs",
        lambda s: {"2024-03-31": {"ebit": 100.0, "debt": 200.0, "cash": 50.0, "shares": 100.0}},
    )
    # EV = price*shares + debt - cash = 5*100 + 200 - 50 = 650; EV/EBIT = 6.5
    result = get_ev_ebit(["X.T"], prices={"X.T": 5.0}, as_of_date=None)
    assert result["X.T"] == 6.5


from src.data.fundamental_loader import get_dividend_yields


def test_get_dividend_yields_excludes_future_and_sums_ttm(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.data.fundamental_loader.DIVIDEND_CACHE", tmp_path / "divs.json"
    )
    monkeypatch.setattr(
        "src.data.fundamental_loader._fetch_dividends",
        lambda s: {"2023-06-30": 10.0, "2023-12-31": 10.0, "2024-09-30": 99.0},
    )
    # as_of 2024-01-31: count only ex-dates in (2023-01-31, 2024-01-31] -> 10 + 10 = 20
    # price 400 -> yield = 20/400 = 0.05; future 2024-09-30 excluded
    result = get_dividend_yields(
        ["X.T"], prices={"X.T": 400.0}, as_of_date=pd.Timestamp("2024-01-31")
    )
    assert result["X.T"] == 0.05


def test_get_dividend_yields_no_dividends_is_zero(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.data.fundamental_loader.DIVIDEND_CACHE", tmp_path / "divs.json"
    )
    monkeypatch.setattr("src.data.fundamental_loader._fetch_dividends", lambda s: {})
    result = get_dividend_yields(
        ["X.T"], prices={"X.T": 400.0}, as_of_date=pd.Timestamp("2024-01-31")
    )
    assert result["X.T"] == 0.0
