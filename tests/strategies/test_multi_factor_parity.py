import backtrader as bt
import pandas as pd

from src.paper.bot import calculate_current_signals
from src.scoring.multi_factor import score_universe
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


def test_collect_visible_history_returns_symbol_dataframes():
    data = {
        "AAA.T": make_df([100 + i for i in range(8)]),
        "BBB.T": make_df([200 + i for i in range(8)]),
    }

    strategy = run_strategy_with_history(
        data,
        lookback_mom=3,
        lookback_vol=2,
        lookback_rev=2,
        top_n=2,
    )

    history = strategy._collect_visible_history()

    assert set(history) == {"AAA.T", "BBB.T"}
    assert list(history["AAA.T"].columns) == ["Close"]
    assert history["AAA.T"]["Close"].tolist() == data["AAA.T"]["Close"].tolist()


def test_strategy_adapter_ranking_matches_shared_scorer():
    data = {
        "AAA.T": make_df([100] * 70 + list(range(100, 110)) + list(range(150, 130, -1))),
        "BBB.T": make_df([120] * 70 + list(range(120, 110, -1)) + [80] * 20),
        "CCC.T": make_df([100] * 100),
    }

    strategy = run_strategy_with_history(
        data,
        lookback_mom=90,
        lookback_vol=20,
        lookback_rev=20,
        weight_mom=0.5,
        weight_vol=1.0,
        weight_rev=0.5,
        top_n=2,
    )

    ranked = strategy._score_visible_universe()
    expected = score_universe(
        data,
        top_n=2,
        weight_mom=0.5,
        weight_vol=1.0,
        weight_rev=0.5,
        lookback_mom=90,
        lookback_vol=20,
        lookback_rev=20,
    )

    assert ranked["symbol"].tolist() == expected["symbol"].tolist()
    assert ranked["total_score"].tolist() == expected["total_score"].tolist()


def test_rebalance_uses_shared_ranked_top_n():
    data = {
        "AAA.T": make_df([100] * 70 + list(range(100, 110)) + list(range(150, 130, -1))),
        "BBB.T": make_df([120] * 70 + list(range(120, 110, -1)) + [80] * 20),
        "CCC.T": make_df([100] * 100),
    }

    strategy = run_strategy_with_history(
        data,
        lookback_mom=90,
        lookback_vol=20,
        lookback_rev=20,
        weight_mom=0.5,
        weight_vol=1.0,
        weight_rev=0.5,
        top_n=2,
    )

    closes = []
    targets = []
    strategy.close = lambda data=None: closes.append(data._name if data is not None else None)
    strategy.order_target_percent = lambda data=None, target=0.0: targets.append((data._name, round(target, 4)))

    strategy.rebalance()

    expected = score_universe(
        data,
        top_n=2,
        weight_mom=0.5,
        weight_vol=1.0,
        weight_rev=0.5,
        lookback_mom=90,
        lookback_vol=20,
        lookback_rev=20,
    ).head(2)

    assert [symbol for symbol, _ in targets] == expected["symbol"].tolist()
    assert targets == [(symbol, 0.475) for symbol in expected["symbol"].tolist()]
    assert set(closes).isdisjoint(set(expected["symbol"].tolist()))


def test_shared_strategy_and_paper_paths_match_under_same_weights():
    data = {
        "AAA.T": make_df([100] * 70 + list(range(100, 110)) + list(range(150, 130, -1))),
        "BBB.T": make_df([120] * 70 + list(range(120, 110, -1)) + [80] * 20),
        "CCC.T": make_df([100] * 100),
    }

    strategy = run_strategy_with_history(
        data,
        lookback_mom=90,
        lookback_vol=20,
        lookback_rev=20,
        weight_mom=0.5,
        weight_vol=1.0,
        weight_rev=0.5,
        top_n=2,
    )

    shared = score_universe(
        data,
        top_n=2,
        weight_mom=0.5,
        weight_vol=1.0,
        weight_rev=0.5,
        lookback_mom=90,
        lookback_vol=20,
        lookback_rev=20,
    )
    strategy_ranked = strategy._score_visible_universe()
    paper = calculate_current_signals(
        data,
        top_n=2,
        weight_mom=0.5,
        weight_vol=1.0,
        weight_rev=0.5,
    )

    assert strategy_ranked["symbol"].tolist() == shared["symbol"].tolist()
    assert paper["symbol"].tolist() == shared.head(2)["symbol"].tolist()
    assert paper["total_score"].tolist() == shared.head(2)["total_score"].tolist()
