import backtrader as bt
import pandas as pd

from src.strategies.multi_factor import UniversalMultiFactor


def make_df(closes):
    dates = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"Close": closes}, index=dates)


def run_strategy_with_history(data_dfs, **kwargs):
    cerebro = bt.Cerebro()
    cerebro.addstrategy(UniversalMultiFactor, **kwargs)

    for symbol, df in data_dfs.items():
        cerebro.adddata(bt.feeds.PandasData(dataname=df), name=symbol)

    cerebro.broker.setcash(1_000_000.0)
    cerebro.run(runonce=False, preload=True)
    return cerebro.runstrats[0][0]


def make_ranked(symbols):
    rows = []
    for index, symbol in enumerate(symbols, start=1):
        rows.append(
            {
                "symbol": symbol,
                "total_score": float(len(symbols) - index),
                "rank": index,
            }
        )
    return pd.DataFrame(rows)


class PositionStub:
    def __init__(self, size):
        self.size = size


def test_rebalance_keeps_existing_holdings_inside_sell_threshold():
    strategy = run_strategy_with_history(
        {"AAA.T": make_df([100] * 100), "BBB.T": make_df([100] * 100), "CCC.T": make_df([100] * 100)},
        top_n=2,
        buy_rank_threshold=2,
        sell_rank_threshold=3,
    )
    strategy._score_visible_universe = lambda: make_ranked(["CCC.T", "BBB.T", "AAA.T"])
    strategy.getposition = lambda data: PositionStub(10 if data._name == "AAA.T" else 0)

    closes = []
    targets = []
    strategy.close = lambda data=None: closes.append(data._name if data is not None else None)
    strategy.order_target_percent = lambda data=None, target=0.0: targets.append((data._name, round(target, 4)))

    strategy.rebalance()

    assert closes == []
    assert [symbol for symbol, _ in targets] == ["AAA.T", "CCC.T"]


def test_rebalance_does_not_buy_non_holding_outside_buy_threshold():
    strategy = run_strategy_with_history(
        {
            "AAA.T": make_df([100] * 100),
            "BBB.T": make_df([100] * 100),
            "CCC.T": make_df([100] * 100),
            "DDD.T": make_df([100] * 100),
        },
        top_n=2,
        buy_rank_threshold=2,
        sell_rank_threshold=4,
    )
    strategy._score_visible_universe = lambda: make_ranked(["CCC.T", "DDD.T", "BBB.T", "AAA.T"])
    strategy.getposition = lambda data: PositionStub(10 if data._name == "AAA.T" else 0)

    closes = []
    targets = []
    strategy.close = lambda data=None: closes.append(data._name if data is not None else None)
    strategy.order_target_percent = lambda data=None, target=0.0: targets.append((data._name, round(target, 4)))

    strategy.rebalance()

    assert closes == []
    assert [symbol for symbol, _ in targets] == ["AAA.T", "CCC.T"]
    assert "BBB.T" not in [symbol for symbol, _ in targets]


def test_rebalance_exits_holding_below_sell_threshold():
    strategy = run_strategy_with_history(
        {
            "AAA.T": make_df([100] * 100),
            "BBB.T": make_df([100] * 100),
            "CCC.T": make_df([100] * 100),
            "DDD.T": make_df([100] * 100),
        },
        top_n=2,
        buy_rank_threshold=2,
        sell_rank_threshold=3,
    )
    strategy._score_visible_universe = lambda: make_ranked(["CCC.T", "DDD.T", "BBB.T", "AAA.T"])
    strategy.getposition = lambda data: PositionStub(10 if data._name == "AAA.T" else 0)

    closes = []
    targets = []
    strategy.close = lambda data=None: closes.append(data._name if data is not None else None)
    strategy.order_target_percent = lambda data=None, target=0.0: targets.append((data._name, round(target, 4)))

    strategy.rebalance()

    assert closes == ["AAA.T"]
    assert [symbol for symbol, _ in targets] == ["CCC.T", "DDD.T"]


def test_rebalance_caps_target_holdings_at_top_n():
    strategy = run_strategy_with_history(
        {
            "AAA.T": make_df([100] * 100),
            "BBB.T": make_df([100] * 100),
            "CCC.T": make_df([100] * 100),
            "DDD.T": make_df([100] * 100),
        },
        top_n=2,
        buy_rank_threshold=2,
        sell_rank_threshold=4,
    )
    strategy._score_visible_universe = lambda: make_ranked(["CCC.T", "DDD.T", "BBB.T", "AAA.T"])
    strategy.getposition = lambda data: PositionStub(10 if data._name in {"AAA.T", "BBB.T"} else 0)

    targets = []
    strategy.close = lambda data=None: None
    strategy.order_target_percent = lambda data=None, target=0.0: targets.append((data._name, round(target, 4)))

    strategy.rebalance()

    assert len(targets) == 2
    assert [symbol for symbol, _ in targets] == ["BBB.T", "AAA.T"]
