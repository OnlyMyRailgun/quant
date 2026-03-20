import backtrader as bt
import pandas as pd

from src.engine.runner import run_backtest
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


def test_rebalance_tracks_turnover_metrics_from_position_changes():
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
    strategy.rebalance_count = 0
    strategy.position_change_count = 0
    strategy.turnover_ratio = 0.0

    strategy.close = lambda data=None: None
    strategy.order_target_percent = lambda data=None, target=0.0: None

    strategy.rebalance()

    assert strategy.rebalance_count == 1
    assert strategy.position_change_count == 3
    assert strategy.turnover_ratio == 3.0


def test_buffered_strategy_has_lower_turnover_than_default_path():
    data_by_symbol = {
        "AAA.T": make_df([100] * 100),
        "BBB.T": make_df([100] * 100),
        "CCC.T": make_df([100] * 100),
        "DDD.T": make_df([100] * 100),
    }
    default_strategy = run_strategy_with_history(data_by_symbol, top_n=2)
    default_strategy._score_visible_universe = lambda: make_ranked(["CCC.T", "DDD.T", "AAA.T", "BBB.T"])
    default_strategy.getposition = lambda data: PositionStub(10 if data._name == "AAA.T" else 0)
    default_strategy.rebalance_count = 0
    default_strategy.position_change_count = 0
    default_strategy.turnover_ratio = 0.0
    default_strategy.close = lambda data=None: None
    default_strategy.order_target_percent = lambda data=None, target=0.0: None

    buffered_strategy = run_strategy_with_history(
        data_by_symbol,
        top_n=2,
        buy_rank_threshold=2,
        sell_rank_threshold=3,
    )
    buffered_strategy._score_visible_universe = lambda: make_ranked(["CCC.T", "DDD.T", "AAA.T", "BBB.T"])
    buffered_strategy.getposition = lambda data: PositionStub(10 if data._name == "AAA.T" else 0)
    buffered_strategy.rebalance_count = 0
    buffered_strategy.position_change_count = 0
    buffered_strategy.turnover_ratio = 0.0
    buffered_strategy.close = lambda data=None: None
    buffered_strategy.order_target_percent = lambda data=None, target=0.0: None

    default_strategy.rebalance()
    buffered_strategy.rebalance()

    assert buffered_strategy.position_change_count < default_strategy.position_change_count


def test_runner_metrics_include_turnover_fields():
    result = run_backtest(
        data_dfs={
            "AAA.T": make_df([100] * 100),
            "BBB.T": make_df([100] * 100),
            "CCC.T": make_df([100] * 100),
        },
        strategy_class=UniversalMultiFactor,
    )

    metrics = result["metrics"]

    assert "rebalance_count" in metrics
    assert "position_change_count" in metrics
    assert "turnover_ratio" in metrics
