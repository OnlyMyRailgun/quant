import pytest

from src.data.universe import get_topix_top_10, get_universe, list_universe_names


def test_list_universe_names_returns_stable_registry_order():
    assert list_universe_names() == [
        "topix_top_10",
        "japan_large_30",
        "japan_broad_50",
    ]


def test_get_universe_returns_stable_japan_large_30_symbols():
    symbols = get_universe("japan_large_30")

    assert len(symbols) == 30
    assert symbols == [
        "7203.T",
        "6758.T",
        "8306.T",
        "6861.T",
        "9984.T",
        "9432.T",
        "8035.T",
        "8316.T",
        "6098.T",
        "7974.T",
        "4063.T",
        "6501.T",
        "7741.T",
        "4519.T",
        "4502.T",
        "8411.T",
        "6954.T",
        "6981.T",
        "9433.T",
        "6367.T",
        "4543.T",
        "8058.T",
        "8766.T",
        "6273.T",
        "7267.T",
        "6902.T",
        "2413.T",
        "7733.T",
        "8031.T",
        "6702.T",
    ]


def test_get_universe_returns_stable_japan_broad_50_symbols():
    symbols = get_universe("japan_broad_50")

    assert len(symbols) == 50
    assert symbols == [
        "7203.T",
        "6758.T",
        "8306.T",
        "6861.T",
        "9984.T",
        "9432.T",
        "8035.T",
        "8316.T",
        "6098.T",
        "7974.T",
        "4063.T",
        "6501.T",
        "7741.T",
        "4519.T",
        "4502.T",
        "8411.T",
        "6954.T",
        "6981.T",
        "9433.T",
        "6367.T",
        "4543.T",
        "8058.T",
        "8766.T",
        "6273.T",
        "7267.T",
        "6902.T",
        "2413.T",
        "7733.T",
        "8031.T",
        "6702.T",
        "7731.T",
        "8001.T",
        "8015.T",
        "8053.T",
        "8591.T",
        "9101.T",
        "9104.T",
        "9107.T",
        "9020.T",
        "9021.T",
        "9022.T",
        "8801.T",
        "8308.T",
        "8750.T",
        "3382.T",
        "2502.T",
        "5108.T",
        "4901.T",
        "2802.T",
        "2269.T",
    ]


def test_get_universe_returns_stable_topix_10_symbols():
    symbols = get_universe("topix_top_10")

    assert symbols == get_topix_top_10()
    assert len(symbols) == 10
    assert symbols == [
        "7203.T",
        "6758.T",
        "8306.T",
        "6861.T",
        "9984.T",
        "9432.T",
        "8035.T",
        "8316.T",
        "6098.T",
        "7974.T",
    ]


def test_get_universe_rejects_unknown_names():
    with pytest.raises(KeyError):
        get_universe("unknown")


def test_get_topix_top_10_keeps_compatibility():
    symbols = get_topix_top_10()

    assert symbols == get_universe("topix_top_10")
    assert len(symbols) == 10
    for sym in symbols:
        assert isinstance(sym, str)
        assert sym.endswith(".T")
