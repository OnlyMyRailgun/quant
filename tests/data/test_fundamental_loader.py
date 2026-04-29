from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.data.fundamental_loader import (
    _compute_book_value_per_share,
    get_book_values,
    FUNDAMENTAL_CACHE,
)


def test_compute_book_value_per_share_returns_dict():
    """Smoke test: Toyota should return BVPS for multiple fiscal years."""
    result = _compute_book_value_per_share("7203.T")
    assert isinstance(result, dict)
    assert len(result) >= 2  # at least 2 fiscal years
    for fy, bvps in result.items():
        pd.Timestamp(fy)  # valid date string
        assert isinstance(bvps, float)
        assert bvps > 0


def test_get_book_values_no_date_returns_latest():
    """Without as_of_date, returns the most recent fiscal year's BVPS."""
    result = get_book_values(["7203.T"], as_of_date=None)
    assert "7203.T" in result
    assert result["7203.T"] is not None
    assert result["7203.T"] > 0


def test_get_book_values_pit_filters_old_data():
    """With an old as_of_date, only old fiscal years should be available."""
    old_date = pd.Timestamp("2023-01-01")
    result = get_book_values(["7203.T"], as_of_date=old_date)
    # FY2022 (2022-03-31) + 60d = 2022-05-30, should be available
    # FY2023 (2023-03-31) + 60d = 2023-05-30, should NOT be available on 2023-01-01
    assert "7203.T" in result
    bv = result["7203.T"]
    if bv is not None:
        # The value should come from FY2022 since FY2023 wasn't published yet
        raw = _compute_book_value_per_share("7203.T")
        fy2022 = raw.get("2022-03-31")
        assert bv == fy2022


def test_get_book_values_unknown_symbol():
    """Unknown symbol returns None."""
    result = get_book_values(["ZZZZZZZZZZ.T"], as_of_date=pd.Timestamp("2024-01-01"))
    assert result["ZZZZZZZZZZ.T"] is None


def test_get_book_values_caches(tmp_path: Path, monkeypatch):
    """Results are cached to disk after first fetch."""
    monkeypatch.setattr(
        "src.data.fundamental_loader.FUNDAMENTAL_CACHE",
        tmp_path / "fundamentals.json",
    )

    # First call — should fetch from yfinance
    result1 = get_book_values(["7203.T"], as_of_date=None, force_refresh=True)
    assert result1["7203.T"] is not None

    # Verify cache file was written
    assert (tmp_path / "fundamentals.json").exists()
    with open(tmp_path / "fundamentals.json") as f:
        cached = json.load(f)
    assert "7203.T" in cached
    assert len(cached["7203.T"]) >= 2
