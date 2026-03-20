import pandas as pd

from src.research.data_validation import validate_price_frame


def make_frame(closes, index=None):
    if index is None:
        index = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"Close": closes}, index=index)


def test_validate_price_frame_returns_summary_for_clean_frame():
    df = make_frame([100.0, 101.5, 102.25])

    result = validate_price_frame(df)

    assert result.is_valid is True
    assert result.issues == []
    assert result.row_count == 3
    assert result.start == "2024-01-01"
    assert result.end == "2024-01-03"


def test_validate_price_frame_flags_duplicate_timestamps():
    df = make_frame(
        [100.0, 101.0, 102.0],
        index=pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02"]),
    )

    result = validate_price_frame(df)

    assert result.is_valid is False
    assert "duplicate timestamps" in result.issues
    assert result.row_count == 3


def test_validate_price_frame_flags_missing_close_column():
    df = pd.DataFrame({"Open": [100.0, 101.0]}, index=pd.date_range("2024-01-01", periods=2, freq="D"))

    result = validate_price_frame(df)

    assert result.is_valid is False
    assert "missing Close" in result.issues
    assert result.row_count == 2


def test_validate_price_frame_flags_non_finite_and_non_positive_closes():
    df = make_frame([100.0, float("nan"), 0.0, float("inf"), -1.0])

    result = validate_price_frame(df)

    assert result.is_valid is False
    assert "non-finite close values" in result.issues
    assert "non-positive close values" in result.issues
    assert result.row_count == 5


def test_validate_price_frame_flags_unsorted_timestamps_and_empty_slices():
    unsorted = make_frame(
        [100.0, 101.0, 102.0],
        index=pd.to_datetime(["2024-01-03", "2024-01-01", "2024-01-02"]),
    )

    unsorted_result = validate_price_frame(unsorted)

    assert unsorted_result.is_valid is False
    assert "unsorted timestamps" in unsorted_result.issues
    assert unsorted_result.start == "2024-01-03"
    assert unsorted_result.end == "2024-01-02"

    empty_result = validate_price_frame(pd.DataFrame(columns=["Close"]))

    assert empty_result.is_valid is False
    assert "empty slice" in empty_result.issues
    assert empty_result.row_count == 0
