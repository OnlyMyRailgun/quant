import pandas as pd
import pytest

from src.research.screening import ScreeningRules, screen_universe


def make_frame(closes, start="2024-01-01"):
    index = pd.date_range(start, periods=len(closes), freq="D")
    return pd.DataFrame({"Close": closes}, index=index)


def make_frame_with_index(closes, index):
    return pd.DataFrame({"Close": closes}, index=pd.to_datetime(index))


def test_screen_universe_accepts_symbol_that_meets_phase1_rules():
    rules = ScreeningRules(
        min_history_days=5,
        max_missing_ratio=0.2,
        min_latest_close=10.0,
        recent_window_days=3,
        min_recent_trading_day_ratio=0.5,
        max_recent_inactive_day_ratio=0.8,
    )
    data_dfs = {"GOOD": make_frame([10.0, 11.0, 12.0, 13.0, 14.0])}

    result = screen_universe(
        candidate_symbols=["GOOD"],
        data_dfs=data_dfs,
        start="2024-01-01",
        end="2024-01-05",
        screen_as_of="2024-01-05",
        screening_rules=rules,
    )

    assert result["eligible_symbols"] == ["GOOD"]
    assert result["rejected_symbols"] == []
    assert result["by_symbol"]["GOOD"]["eligible"] is True
    assert result["by_symbol"]["GOOD"]["reasons"] == []
    assert result["by_symbol"]["GOOD"]["metrics"]["history_days"] == 5
    assert result["by_symbol"]["GOOD"]["metrics"]["missing_ratio"] == 0.0
    assert result["by_symbol"]["GOOD"]["metrics"]["latest_close"] == 14.0
    assert result["by_symbol"]["GOOD"]["metrics"]["recent_trading_day_ratio"] == 1.0
    assert result["by_symbol"]["GOOD"]["metrics"]["recent_inactive_day_ratio"] == 0.0
    assert result["summary"]["requested_symbol_count"] == 1
    assert result["summary"]["eligible_symbol_count"] == 1
    assert result["summary"]["screened_out_symbol_count"] == 0
    assert result["summary"]["eligibility_ratio"] == 1.0


def test_screen_universe_includes_rows_on_date_string_screen_as_of():
    rules = ScreeningRules(
        min_history_days=2,
        max_missing_ratio=0.2,
        min_latest_close=10.0,
        recent_window_days=2,
        min_recent_trading_day_ratio=0.5,
        max_recent_inactive_day_ratio=0.8,
    )
    data_dfs = {
        "SAME_DAY": make_frame_with_index(
            [9.0, 20.0],
            ["2024-01-04 15:00:00", "2024-01-05 10:30:00"],
        )
    }

    result = screen_universe(
        candidate_symbols=["SAME_DAY"],
        data_dfs=data_dfs,
        start="2024-01-04",
        end="2024-01-05",
        screen_as_of="2024-01-05",
        screening_rules=rules,
    )

    assert result["eligible_symbols"] == ["SAME_DAY"]
    assert result["rejected_symbols"] == []
    assert result["by_symbol"]["SAME_DAY"]["metrics"]["latest_close"] == 20.0


def test_screen_universe_treats_trailing_nan_latest_close_as_missing():
    rules = ScreeningRules(
        min_history_days=2,
        max_missing_ratio=0.5,
        min_latest_close=10.0,
        recent_window_days=2,
        min_recent_trading_day_ratio=0.5,
        max_recent_inactive_day_ratio=0.8,
    )
    data_dfs = {"TRAILING_NAN": make_frame([12.0, None])}

    result = screen_universe(
        candidate_symbols=["TRAILING_NAN"],
        data_dfs=data_dfs,
        start="2024-01-01",
        end="2024-01-02",
        screen_as_of="2024-01-02",
        screening_rules=rules,
    )

    assert result["eligible_symbols"] == []
    assert result["rejected_symbols"] == ["TRAILING_NAN"]
    assert result["by_symbol"]["TRAILING_NAN"]["metrics"]["latest_close"] is None
    assert result["by_symbol"]["TRAILING_NAN"]["reasons"] == ["low_latest_close"]


def test_screen_universe_rejects_symbol_for_insufficient_history():
    rules = ScreeningRules(min_history_days=5, max_missing_ratio=1.0, min_latest_close=1.0)
    data_dfs = {"SHORT": make_frame([10.0, 11.0, 12.0])}

    result = screen_universe(
        candidate_symbols=["SHORT"],
        data_dfs=data_dfs,
        start="2024-01-01",
        end="2024-01-03",
        screen_as_of="2024-01-03",
        screening_rules=rules,
    )

    assert result["eligible_symbols"] == []
    assert result["rejected_symbols"] == ["SHORT"]
    assert result["by_symbol"]["SHORT"]["eligible"] is False
    assert result["by_symbol"]["SHORT"]["reasons"] == ["insufficient_history"]
    assert result["by_symbol"]["SHORT"]["metrics"]["history_days"] == 3


def test_screen_universe_uses_requested_window_for_missing_ratio_and_recent_activity():
    rules = ScreeningRules(
        min_history_days=1,
        max_missing_ratio=0.25,
        min_latest_close=1.0,
        recent_window_days=2,
        min_recent_trading_day_ratio=1.0,
        max_recent_inactive_day_ratio=0.0,
    )
    data_dfs = {"WINDOWED": make_frame([None, 10.0, None, 30.0])}

    result = screen_universe(
        candidate_symbols=["WINDOWED"],
        data_dfs=data_dfs,
        start="2024-01-02",
        end="2024-01-02",
        screen_as_of="2024-01-04",
        screening_rules=rules,
    )

    assert result["eligible_symbols"] == ["WINDOWED"]
    assert result["rejected_symbols"] == []
    assert result["by_symbol"]["WINDOWED"]["metrics"]["missing_ratio"] == 0.0
    assert result["by_symbol"]["WINDOWED"]["metrics"]["recent_trading_day_ratio"] == 1.0
    assert result["by_symbol"]["WINDOWED"]["metrics"]["recent_inactive_day_ratio"] == 0.0
    assert result["summary"]["requested_symbol_count"] == 1
    assert result["summary"]["eligible_symbol_count"] == 1
    assert result["summary"]["screened_out_symbol_count"] == 0
    assert result["summary"]["eligibility_ratio"] == 1.0
    assert "screened_out_high_missing_ratio_count" not in result["summary"]
    assert "screened_out_weak_recent_trading_activity_count" not in result["summary"]


def test_screen_universe_rejects_symbol_for_high_missing_ratio():
    rules = ScreeningRules(
        min_history_days=1,
        max_missing_ratio=0.25,
        min_latest_close=1.0,
        min_recent_trading_day_ratio=0.0,
        max_recent_inactive_day_ratio=1.0,
    )
    data_dfs = {"SPARSE": make_frame([10.0, None, None, 13.0])}

    result = screen_universe(
        candidate_symbols=["SPARSE"],
        data_dfs=data_dfs,
        start="2024-01-01",
        end="2024-01-04",
        screen_as_of="2024-01-04",
        screening_rules=rules,
    )

    assert result["eligible_symbols"] == []
    assert result["rejected_symbols"] == ["SPARSE"]
    assert result["by_symbol"]["SPARSE"]["reasons"] == ["high_missing_ratio"]
    assert result["by_symbol"]["SPARSE"]["metrics"]["missing_ratio"] == 0.5


def test_screen_universe_rejects_symbol_for_low_latest_close():
    rules = ScreeningRules(min_history_days=1, max_missing_ratio=1.0, min_latest_close=10.0)
    data_dfs = {"CHEAP": make_frame([50.0, 5.0])}

    result = screen_universe(
        candidate_symbols=["CHEAP"],
        data_dfs=data_dfs,
        start="2024-01-01",
        end="2024-01-02",
        screen_as_of="2024-01-02",
        screening_rules=rules,
    )

    assert result["eligible_symbols"] == []
    assert result["rejected_symbols"] == ["CHEAP"]
    assert result["by_symbol"]["CHEAP"]["reasons"] == ["low_latest_close"]
    assert result["by_symbol"]["CHEAP"]["metrics"]["latest_close"] == 5.0


def test_screen_universe_rejects_symbol_for_weak_recent_trading_activity():
    rules = ScreeningRules(
        min_history_days=1,
        max_missing_ratio=0.8,
        min_latest_close=1.0,
        recent_window_days=5,
        min_recent_trading_day_ratio=0.7,
        max_recent_inactive_day_ratio=0.9,
    )
    data_dfs = {"QUIET": make_frame([10.0, None, None, None, 12.0])}

    result = screen_universe(
        candidate_symbols=["QUIET"],
        data_dfs=data_dfs,
        start="2024-01-01",
        end="2024-01-05",
        screen_as_of="2024-01-05",
        screening_rules=rules,
    )

    assert result["eligible_symbols"] == []
    assert result["rejected_symbols"] == ["QUIET"]
    assert result["by_symbol"]["QUIET"]["reasons"] == ["weak_recent_trading_activity"]
    assert result["by_symbol"]["QUIET"]["metrics"]["recent_trading_day_ratio"] == 0.4
    assert result["by_symbol"]["QUIET"]["metrics"]["recent_inactive_day_ratio"] == 0.6


def test_screen_universe_rejects_symbol_with_multiple_reasons():
    rules = ScreeningRules(
        min_history_days=5,
        max_missing_ratio=0.5,
        min_latest_close=10.0,
        recent_window_days=4,
        min_recent_trading_day_ratio=0.8,
        max_recent_inactive_day_ratio=0.2,
    )
    data_dfs = {"MIXED": make_frame([None, None, None, 4.0])}

    result = screen_universe(
        candidate_symbols=["MIXED"],
        data_dfs=data_dfs,
        start="2024-01-01",
        end="2024-01-04",
        screen_as_of="2024-01-04",
        screening_rules=rules,
    )

    assert result["eligible_symbols"] == []
    assert result["rejected_symbols"] == ["MIXED"]
    assert set(result["by_symbol"]["MIXED"]["reasons"]) >= {
        "insufficient_history",
        "high_missing_ratio",
        "low_latest_close",
        "weak_recent_trading_activity",
        "high_recent_inactive_day_ratio",
    }


def test_screen_universe_summary_aggregates_requested_eligible_screened_out_and_reason_counts():
    rules = ScreeningRules(
        min_history_days=3,
        max_missing_ratio=0.25,
        min_latest_close=10.0,
        recent_window_days=3,
        min_recent_trading_day_ratio=0.5,
        max_recent_inactive_day_ratio=0.5,
    )
    data_dfs = {
        "GOOD": make_frame([10.0, 11.0, 12.0]),
        "SHORT": make_frame([10.0, 11.0]),
        "SPARSE": make_frame([10.0, None, 12.0]),
    }

    result = screen_universe(
        candidate_symbols=["GOOD", "SHORT", "SPARSE", "MISSING"],
        data_dfs=data_dfs,
        start="2024-01-01",
        end="2024-01-03",
        screen_as_of="2024-01-03",
        screening_rules=rules,
    )

    assert result["eligible_symbols"] == ["GOOD"]
    assert result["rejected_symbols"] == ["SHORT", "SPARSE", "MISSING"]
    assert result["by_symbol"]["MISSING"]["eligible"] is False
    assert result["by_symbol"]["MISSING"]["reasons"] == ["missing_data"]
    assert result["summary"]["requested_symbol_count"] == 4
    assert result["summary"]["eligible_symbol_count"] == 1
    assert result["summary"]["screened_out_symbol_count"] == 3
    assert result["summary"]["eligibility_ratio"] == pytest.approx(0.25)
    assert result["summary"]["screened_out_insufficient_history_count"] == 1
    assert result["summary"]["screened_out_high_missing_ratio_count"] == 1
    assert result["summary"]["screened_out_missing_data_count"] == 1
