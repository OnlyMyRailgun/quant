import pytest

from src.data.universe import get_topix_top_10, get_universe, list_universe_names


def test_list_universe_names_returns_stable_registry_order():
    assert list_universe_names() == ["topix_top_10"]


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
