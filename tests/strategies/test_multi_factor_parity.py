import json
from pathlib import Path

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


def test_universal_multi_factor_default_top_n_is_broader_than_three_names():
    assert UniversalMultiFactor.params.top_n == 10


def test_universal_multi_factor_default_reversion_weight_is_disabled():
    assert UniversalMultiFactor.params.weight_rev == 0.0


def _build_month_change_data():
    dates = pd.date_range("2024-01-01", periods=240, freq="D")
    return {
        "AAA.T": pd.DataFrame({"Close": [100 + i * 0.5 for i in range(len(dates))]}, index=dates),
        "BBB.T": pd.DataFrame({"Close": [220 - i * 0.3 for i in range(len(dates))]}, index=dates),
        "CCC.T": pd.DataFrame({"Close": [150 + ((i % 14) - 7) * 0.25 for i in range(len(dates))]}, index=dates),
    }


def test_collect_visible_history_excludes_current_execution_bar():
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
    assert history["AAA.T"]["Close"].tolist() == data["AAA.T"]["Close"].iloc[:-1].tolist()


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
        {symbol: df.iloc[:-1] for symbol, df in data.items()},
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
        {symbol: df.iloc[:-1] for symbol, df in data.items()},
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


def test_rebalance_is_noop_when_visible_universe_is_not_rankable():
    data = {
        "AAA.T": make_df([100 + i for i in range(50)]),
        "BBB.T": make_df([200 + i for i in range(50)]),
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

    assert strategy._score_visible_universe().empty

    strategy.rebalance()

    assert closes == []
    assert targets == []


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


def test_rebalance_writes_one_artifact_per_month_change_with_explainability(tmp_path: Path):
    data = _build_month_change_data()

    strategy = run_strategy_with_history(
        data,
        lookback_mom=90,
        lookback_vol=20,
        lookback_rev=20,
        weight_mom=0.5,
        weight_vol=1.0,
        weight_rev=0.5,
        top_n=2,
        artifact_dir=tmp_path,
        artifact_run_name="multi_factor_rebalance",
        universe_name="demo_universe",
    )

    run_root = tmp_path / "multi_factor_rebalance"
    run_dirs = sorted(path for path in run_root.iterdir() if path.is_dir())

    assert strategy.rebalance_count == len(run_dirs)
    assert strategy.rebalance_count >= 3

    for run_dir in run_dirs:
        metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        scores = pd.read_csv(run_dir / "scores.csv")
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

        assert metadata["universe_name"] == "demo_universe"
        assert metadata["rebalance_date"]
        assert summary["winner_count"] <= summary["top_n"]
        assert {"mom_contribution", "vol_contribution", "rev_contribution"}.issubset(scores.columns)
