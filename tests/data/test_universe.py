from src.data.universe import get_topix_top_10

def test_get_topix_top_10():
    symbols = get_topix_top_10()
    assert len(symbols) == 10
    
    for sym in symbols:
        assert isinstance(sym, str)
        assert sym.endswith(".T")  # Must have Yahoo Finance Japan suffix
