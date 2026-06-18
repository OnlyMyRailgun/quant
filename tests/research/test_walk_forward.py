import json
from pathlib import Path

import backtrader as bt
import pandas as pd
import pytest

import src.optimize as optimize
from src.data import local_store
from src.research.walk_forward import (
    aggregate_universe_participation_summary,
    build_walk_forward_windows,
    run_walk_forward_experiment,
    select_best_weights,
)
from src.research.artifacts import write_walk_forward_run


def test_build_walk_forward_windows_returns_rolling_train_and_validation_ranges():
    windows = build_walk_forward_windows(
        start="2021-01-01",
        end="2021-12-31",
        train_months=6,
        validation_months=3,
        step_months=3,
    )

    assert windows == [
        {
            "train_start": "2021-01-01",
            "train_end": "2021-06-30",
            "validation_start": "2021-07-01",
            "validation_end": "2021-09-30",
        },
        {
            "train_start": "2021-04-01",
            "train_end": "2021-09-30",
            "validation_start": "2021-10-01",
            "validation_end": "2021-12-31",
        },
    ]


def test_build_walk_forward_windows_returns_empty_when_range_is_too_short():
    windows = build_walk_forward_windows(
        start="2021-01-01",
        end="2021-06-30",
        train_months=6,
        validation_months=3,
        step_months=3,
    )

    assert windows == []


def test_select_best_weights_picks_highest_sharpe_weight_tuple():
    leaderboard = select_best_weights(
        weight_grid=[(0.0, 0.0, 1.0, 0.0), (1.0, 0.5, 0.0, 0.0), (1.0, 1.0, 1.0, 0.0)],
        evaluate=lambda weights: {
            (0.0, 0.0, 1.0, 0.0): {"return_pct": 1.0, "sharpe": 0.1},
            (1.0, 0.5, 0.0, 0.0): {"return_pct": 4.0, "sharpe": 0.2},
            (1.0, 1.0, 1.0, 0.0): {"return_pct": 3.0, "sharpe": 0.5},
        }[weights],
    )

    assert leaderboard["best"]["weights"] == {"mom": 1.0, "vol": 1.0, "rev": 1.0, "val": 0.0}
    assert leaderboard["rows"][0]["sharpe"] == 0.5


def test_select_best_weights_prefers_higher_sharpe_over_higher_return():
    leaderboard = select_best_weights(
        weight_grid=[(1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0)],
        evaluate=lambda weights: {
            (1.0, 0.0, 0.0, 0.0): {"return_pct": 6.0, "sharpe": 0.2},
            (0.0, 1.0, 0.0, 0.0): {"return_pct": 4.0, "sharpe": 0.6},
        }[weights],
    )

    assert leaderboard["best"]["weights"] == {"mom": 0.0, "vol": 1.0, "rev": 0.0, "val": 0.0}
    assert leaderboard["rows"][0]["sharpe"] == 0.6


def test_select_best_weights_uses_return_pct_when_sharpe_is_tied():
    leaderboard = select_best_weights(
        weight_grid=[(1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0)],
        evaluate=lambda weights: {
            (1.0, 0.0, 0.0, 0.0): {"return_pct": 5.0, "sharpe": 0.5},
            (0.0, 1.0, 0.0, 0.0): {"return_pct": 3.0, "sharpe": 0.5},
        }[weights],
    )

    assert leaderboard["best"]["weights"] == {"mom": 1.0, "vol": 0.0, "rev": 0.0, "val": 0.0}
    assert leaderboard["rows"][0]["return_pct"] == 5.0


def test_default_weight_grid_excludes_all_zero_tuple():
    assert (0.0, 0.0, 0.0, 0.0) not in optimize.DEFAULT_WEIGHT_GRID


def test_default_weight_grid_excludes_positive_momentum_and_reversion_mix():
    assert all(
        not (weights[0] > 0.0 and weights[2] > 0.0)
        for weights in optimize.DEFAULT_WEIGHT_GRID
    )


def test_select_best_weights_preserves_quality_weight():
    leaderboard = select_best_weights(
        weight_grid=[
            (1.0, 0.0, 0.0, 0.5, 0.0),
            (0.0, 1.0, 0.0, 0.5, 1.0),
        ],
        evaluate=lambda weights: {
            (1.0, 0.0, 0.0, 0.5, 0.0): {"return_pct": 1.0, "sharpe": 0.1},
            (0.0, 1.0, 0.0, 0.5, 1.0): {"return_pct": 2.0, "sharpe": 0.2},
        }[weights],
    )

    assert leaderboard["best"]["weights"] == {
        "mom": 0.0,
        "vol": 1.0,
        "rev": 0.0,
        "val": 0.5,
        "qual": 1.0,
    }


def test_write_walk_forward_run_persists_weights_and_summary(tmp_path: Path):
    weights = pd.DataFrame(
        [
            {
                "rebalance_date": "2021-07-01",
                "weight_mom": 1.0,
                "weight_vol": 0.5,
                "weight_rev": 0.0,
            }
        ]
    )

    paths = write_walk_forward_run(
        base_dir=tmp_path,
        metadata={"train_months": 6, "validation_months": 3},
        weights=weights,
        summary={"window_count": 1, "baseline_return_pct": 2.5, "walk_forward_return_pct": 3.1},
    )

    assert paths["metadata"].exists()
    assert paths["weights"].exists()
    assert paths["summary"].exists()

    metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    saved_weights = pd.read_csv(paths["weights"])
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))

    assert metadata["train_months"] == 6
    assert metadata["validation_months"] == 3
    assert saved_weights["rebalance_date"].tolist() == ["2021-07-01"]
    assert summary["walk_forward_return_pct"] == 3.1


def test_evaluate_weight_tuple_returns_symbol_diagnostics_from_real_backtest_path(monkeypatch):
    class BuyAndHoldBoth(bt.Strategy):
        params = dict(weight_mom=1.0, weight_vol=1.0, weight_rev=1.0)

        def __init__(self):
            self._ordered = False

        def next(self):
            if self._ordered:
                return
            self._ordered = True
            for data in self.datas:
                self.order_target_percent(data=data, target=0.4)

    monkeypatch.setattr(optimize, "UniversalMultiFactor", BuyAndHoldBoth)

    data_dfs = {
        "AAA.T": pd.DataFrame({"Close": [100.0, 110.0, 130.0]}, index=pd.date_range("2021-01-01", periods=3)),
        "BBB.T": pd.DataFrame({"Close": [100.0, 95.0, 90.0]}, index=pd.date_range("2021-01-01", periods=3)),
    }

    metrics = optimize.evaluate_weight_tuple(
        data_dfs=data_dfs,
        start="2021-01-01",
        end="2021-01-03",
        weights=(1.0, 1.0, 1.0),
    )

    assert "symbol_returns" in metrics
    assert metrics["symbol_returns"] == [
        {"symbol": "AAA.T", "return_pct": 12.0},
        {"symbol": "BBB.T", "return_pct": -4.0},
    ]


def test_evaluate_weight_tuple_handles_short_windows_without_runonce_crash():
    index = pd.bdate_range("2022-01-03", periods=59)
    data_dfs = {
        f"S{i}.T": pd.DataFrame(
            {"Close": [100.0 + i + j * 0.1 for j in range(len(index))]},
            index=index,
        )
        for i in range(10)
    }

    metrics = optimize.evaluate_weight_tuple(
        data_dfs=data_dfs,
        start="2022-01-03",
        end="2022-03-31",
        weights=(1.0, 1.0, 1.0),
    )

    assert metrics["return_pct"] == 0.0
    assert metrics["symbol_returns"] == []


def test_evaluate_weight_tuple_uses_prior_history_to_warm_up_short_evaluation_windows():
    index = pd.bdate_range("2021-09-01", "2022-03-31")
    data_dfs = {
        f"S{i}.T": pd.DataFrame(
            {"Close": [100.0 + i + j * 0.1 for j in range(len(index))]},
            index=index,
        )
        for i in range(10)
    }

    metrics = optimize.evaluate_weight_tuple(
        data_dfs=data_dfs,
        start="2022-01-01",
        end="2022-03-31",
        weights=(1.0, 1.0, 1.0),
    )

    assert metrics["return_pct"] > 0.0
    assert metrics["symbol_returns"]


def test_evaluate_weight_tuple_accepts_book_value_provider_for_simple_engine():
    index = pd.bdate_range("2024-01-01", "2024-07-03")
    data_dfs = {
        "AAA.T": pd.DataFrame({"Close": [100.0] * len(index)}, index=index),
        "BBB.T": pd.DataFrame({"Close": [100.0] * len(index)}, index=index),
    }

    def book_values_as_of(as_of_date):
        if pd.Timestamp(as_of_date) < pd.Timestamp("2024-07-01"):
            return {"AAA.T": 100.0, "BBB.T": 50.0}
        return {"AAA.T": 50.0, "BBB.T": 100.0}

    metrics = optimize.evaluate_weight_tuple(
        data_dfs=data_dfs,
        start="2024-06-03",
        end="2024-07-03",
        weights=(0.0, 0.0, 0.0, 1.0),
        engine="simple",
        book_values=book_values_as_of,
    )

    assert metrics["scores"].iloc[0]["symbol"] == "BBB.T"


def test_evaluate_weight_tuple_forwards_top_n_to_simple_engine():
    index = pd.bdate_range("2024-01-01", "2024-07-03")
    data_dfs = {
        "AAA.T": pd.DataFrame({"Close": [100.0] * len(index)}, index=index),
        "BBB.T": pd.DataFrame({"Close": [100.0] * len(index)}, index=index),
        "CCC.T": pd.DataFrame({"Close": [100.0] * len(index)}, index=index),
    }

    metrics = optimize.evaluate_weight_tuple(
        data_dfs=data_dfs,
        start="2024-06-03",
        end="2024-07-03",
        weights=(0.0, 0.0, 0.0, 0.0),
        engine="simple",
        top_n=2,
    )

    assert int(metrics["scores"]["is_top_n"].sum()) == 2


def test_evaluate_weight_tuple_uses_research_momentum_definition_in_execution(monkeypatch):
    class RankingStrategy(bt.Strategy):
        params = dict(
            weight_mom=1.0,
            weight_vol=0.0,
            weight_rev=0.0,
            top_n=1,
        )

        def __init__(self):
            self._ordered = False

        def _collect_visible_history(self):
            history = {}
            for data in self.datas:
                closes = list(data.close.get(size=len(data)))
                datetimes = [
                    bt.num2date(value).replace(tzinfo=None)
                    for value in data.datetime.get(size=len(data))
                ]
                history[data._name] = pd.DataFrame(
                    {"Close": closes},
                    index=pd.DatetimeIndex(datetimes),
                )
            return history

        def _score_visible_universe(self):
            return optimize.score_universe(
                self._collect_visible_history(),
                top_n=self.p.top_n,
                weight_mom=self.p.weight_mom,
                weight_vol=self.p.weight_vol,
                weight_rev=self.p.weight_rev,
            )

        def next(self):
            if self._ordered or len(self) < 252:
                return
            ranked = self._score_visible_universe()
            if ranked.empty:
                return
            top_symbol = ranked.iloc[0]["symbol"]
            for data in self.datas:
                target = 0.95 if data._name == top_symbol else 0.0
                self.order_target_percent(data=data, target=target)
            self._ordered = True

    monkeypatch.setattr(optimize, "UniversalMultiFactor", RankingStrategy)

    index = pd.bdate_range("2021-01-01", periods=320)
    data_dfs = {
        "A.T": pd.DataFrame(
            {"Close": [100.0] * 200 + [100.0 + i * 1.2 for i in range(120)]},
            index=index,
        ),
        "B.T": pd.DataFrame(
            {"Close": [100.0 + i * 0.6 for i in range(250)] + [250.0 - i * 0.2 for i in range(70)]},
            index=index,
        ),
        "C.T": pd.DataFrame({"Close": [100.0] * 320}, index=index),
    }

    metrics_90d = optimize.evaluate_weight_tuple(
        data_dfs=data_dfs,
        start="2021-01-01",
        end=index[-1].strftime("%Y-%m-%d"),
        weights=(1.0, 0.0, 0.0, 0.0),
        momentum_definition="90d",
    )
    metrics_12_1 = optimize.evaluate_weight_tuple(
        data_dfs=data_dfs,
        start="2021-01-01",
        end=index[-1].strftime("%Y-%m-%d"),
        weights=(1.0, 0.0, 0.0, 0.0),
        momentum_definition="12_1",
    )

    assert metrics_90d["return_pct"] > metrics_12_1["return_pct"]


def test_run_walk_forward_experiment_returns_rebalance_weights_and_summary():
    weight_grid = [(1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0)]
    one_shot_weights = (0.0, 1.0, 0.0, 0.0)
    training_scores = {
        ("2021-01-01", "2021-06-30", (1.0, 0.0, 0.0, 0.0)): {"return_pct": 5.0, "sharpe": 0.5},
        ("2021-01-01", "2021-06-30", (0.0, 1.0, 0.0, 0.0)): {"return_pct": 3.0, "sharpe": 0.2},
        ("2021-04-01", "2021-09-30", (1.0, 0.0, 0.0, 0.0)): {"return_pct": 2.0, "sharpe": 0.1},
        ("2021-04-01", "2021-09-30", (0.0, 1.0, 0.0, 0.0)): {"return_pct": 4.0, "sharpe": 0.3},
    }
    validation_scores = {
        ("2021-07-01", "2021-09-30", (1.0, 0.0, 0.0, 0.0)): {
            "return_pct": 1.5,
            "sharpe": 0.15,
            "symbol_returns": [
                {"symbol": "AAA.T", "return_pct": 2.0},
                {"symbol": "BBB.T", "return_pct": -0.5},
            ],
        },
        ("2021-10-01", "2021-12-31", (0.0, 1.0, 0.0, 0.0)): {
            "return_pct": 2.5,
            "sharpe": 0.25,
            "symbol_returns": [
                {"symbol": "AAA.T", "return_pct": 1.5},
                {"symbol": "CCC.T", "return_pct": 1.0},
            ],
        },
    }
    baseline_scores = {
        ("2021-07-01", "2021-09-30"): {"return_pct": 1.0, "sharpe": 0.1},
        ("2021-10-01", "2021-12-31"): {"return_pct": 1.2, "sharpe": 0.12},
    }
    one_shot_training_scores = {
        ("2021-01-01", "2021-06-30", (1.0, 0.0, 0.0, 0.0)): {"return_pct": 2.0, "sharpe": 0.2},
        ("2021-01-01", "2021-06-30", (0.0, 1.0, 0.0, 0.0)): {"return_pct": 3.5, "sharpe": 0.35},
    }
    one_shot_validation_scores = {
        ("2021-07-01", "2021-09-30", one_shot_weights): {"return_pct": 1.8, "sharpe": 0.18},
        ("2021-10-01", "2021-12-31", one_shot_weights): {"return_pct": 1.4, "sharpe": 0.14},
    }
    benchmark_topx_scores = {
        ("2021-07-01", "2021-09-30"): {"return_pct": 0.8},
        ("2021-10-01", "2021-12-31"): {"return_pct": 1.1},
    }
    benchmark_n225_scores = {
        ("2021-07-01", "2021-09-30"): {"return_pct": 0.5},
        ("2021-10-01", "2021-12-31"): {"return_pct": 1.6},
    }

    result = run_walk_forward_experiment(
        start="2021-01-01",
        end="2021-12-31",
        train_months=6,
        validation_months=3,
        step_months=3,
        weight_grid=weight_grid,
        evaluate_training_window=lambda window, weights: training_scores[
            (window["train_start"], window["train_end"], weights)
        ],
        evaluate_validation_window=lambda window, weights: validation_scores[
            (window["validation_start"], window["validation_end"], weights)
        ],
        evaluate_baseline_window=lambda window: baseline_scores[
            (window["validation_start"], window["validation_end"])
        ],
        evaluate_one_shot_training_window=lambda weights: one_shot_training_scores[
            ("2021-01-01", "2021-06-30", weights)
        ],
        evaluate_one_shot_validation_window=lambda window, weights: one_shot_validation_scores[
            (window["validation_start"], window["validation_end"], weights)
        ],
        evaluate_benchmark_windows={
            "topx": lambda window: benchmark_topx_scores[
                (window["validation_start"], window["validation_end"])
            ],
            "n225": lambda window: benchmark_n225_scores[
                (window["validation_start"], window["validation_end"])
            ],
        },
    )

    assert result["weights"]["rebalance_date"].tolist() == ["2021-07-01", "2021-10-01"]
    assert result["weights"]["weight_mom"].tolist() == [1.0, 0.0]
    assert result["weights"]["weight_vol"].tolist() == [0.0, 1.0]
    assert result["weights"]["one_shot_return_pct"].tolist() == [1.8, 1.4]
    assert result["weights"]["topx_return_pct"].tolist() == [0.8, 1.1]
    assert result["weights"]["n225_return_pct"].tolist() == [0.5, 1.6]
    assert result["weights"]["hit_rate"].tolist() == [0.5, 1.0]
    assert result["weights"]["top_contributors"].tolist() == [
        [
            {"symbol": "AAA.T", "return_pct": 2.0},
            {"symbol": "BBB.T", "return_pct": -0.5},
        ],
        [
            {"symbol": "AAA.T", "return_pct": 1.5},
            {"symbol": "CCC.T", "return_pct": 1.0},
        ],
    ]
    assert result["weights"]["bottom_contributors"].tolist() == [
        [
            {"symbol": "BBB.T", "return_pct": -0.5},
            {"symbol": "AAA.T", "return_pct": 2.0},
        ],
        [
            {"symbol": "CCC.T", "return_pct": 1.0},
            {"symbol": "AAA.T", "return_pct": 1.5},
        ],
    ]
    assert result["summary"] == {
        "window_count": 2,
        "baseline_return_pct": 2.212,
        "one_shot_return_pct": 3.2252,
        "walk_forward_return_pct": 4.0375,
        "one_shot_active_return_pct": 1.0132,
        "active_return_pct": 1.8255,
        "topx_return_pct": 1.9088,
        "n225_return_pct": 2.108,
        "walk_forward_excess_vs_topx_pct": 2.1287,
        "walk_forward_excess_vs_n225_pct": 1.9295,
        "avg_hit_rate": 0.75,
        "top_contributors": [
            {"symbol": "AAA.T", "return_pct": 3.5},
            {"symbol": "CCC.T", "return_pct": 1.0},
            {"symbol": "BBB.T", "return_pct": -0.5},
        ],
        "bottom_contributors": [
            {"symbol": "BBB.T", "return_pct": -0.5},
            {"symbol": "CCC.T", "return_pct": 1.0},
            {"symbol": "AAA.T", "return_pct": 3.5},
        ],
    }


def test_run_walk_forward_experiment_compounds_summary_returns():
    result = run_walk_forward_experiment(
        start="2021-01-01",
        end="2021-12-31",
        train_months=6,
        validation_months=3,
        step_months=3,
        weight_grid=[(1.0, 0.0, 0.0, 0.0)],
        evaluate_training_window=lambda window, weights: {"return_pct": 1.0, "sharpe": 0.1},
        evaluate_validation_window=lambda window, weights: {
            "return_pct": {
                "2021-07-01": 10.0,
                "2021-10-01": -10.0,
            }[window["validation_start"]],
            "sharpe": 0.1,
        },
        evaluate_baseline_window=lambda window: {
            "return_pct": {
                "2021-07-01": 5.0,
                "2021-10-01": -5.0,
            }[window["validation_start"]],
            "sharpe": 0.1,
        },
        evaluate_one_shot_training_window=lambda weights: {"return_pct": 1.0, "sharpe": 0.1},
        evaluate_one_shot_validation_window=lambda window, weights: {
            "return_pct": {
                "2021-07-01": 20.0,
                "2021-10-01": -10.0,
            }[window["validation_start"]],
            "sharpe": 0.1,
        },
        evaluate_benchmark_windows={
            "topx": lambda window: {
                "return_pct": {
                    "2021-07-01": 2.0,
                    "2021-10-01": -1.0,
                }[window["validation_start"]]
            },
        },
    )

    assert result["summary"]["walk_forward_return_pct"] == pytest.approx(-1.0)
    assert result["summary"]["baseline_return_pct"] == pytest.approx(-0.25)
    assert result["summary"]["active_return_pct"] == pytest.approx(-0.75)
    assert result["summary"]["one_shot_return_pct"] == pytest.approx(8.0)
    assert result["summary"]["one_shot_active_return_pct"] == pytest.approx(8.25)
    assert result["summary"]["topx_return_pct"] == pytest.approx(0.98)
    assert result["summary"]["walk_forward_excess_vs_topx_pct"] == pytest.approx(-1.98)


def test_run_walk_forward_experiment_passes_quality_weight_to_validation():
    captured_validation_weights = []

    result = run_walk_forward_experiment(
        start="2021-01-01",
        end="2021-09-30",
        train_months=6,
        validation_months=3,
        step_months=3,
        weight_grid=[(0.0, 1.0, 0.0, 0.5, 1.0)],
        evaluate_training_window=lambda window, weights: {"return_pct": 1.0, "sharpe": 0.1},
        evaluate_validation_window=lambda window, weights: (
            captured_validation_weights.append(weights)
            or {"return_pct": 2.0, "sharpe": 0.2}
        ),
        evaluate_baseline_window=lambda window: {"return_pct": 1.0, "sharpe": 0.1},
    )

    assert captured_validation_weights == [(0.0, 1.0, 0.0, 0.5, 1.0)]
    assert result["weights"]["weight_qual"].tolist() == [1.0]


def test_run_walk_forward_experiment_aggregates_summary_contributors_from_full_symbol_returns():
    weight_grid = [(1.0, 0.0, 0.0, 0.0)]
    validation_scores = {
        ("2021-07-01", "2021-09-30", (1.0, 0.0, 0.0, 0.0)): {
            "return_pct": 1.0,
            "sharpe": 0.1,
            "symbol_returns": [
                {"symbol": "AAA.T", "return_pct": 7.0},
                {"symbol": "BBB.T", "return_pct": 6.0},
                {"symbol": "CCC.T", "return_pct": 5.0},
                {"symbol": "DDD.T", "return_pct": 4.0},
                {"symbol": "EEE.T", "return_pct": 3.0},
                {"symbol": "FFF.T", "return_pct": 2.0},
                {"symbol": "GGG.T", "return_pct": 1.0},
            ],
        },
        ("2021-10-01", "2021-12-31", (1.0, 0.0, 0.0, 0.0)): {
            "return_pct": 1.0,
            "sharpe": 0.1,
            "symbol_returns": [
                {"symbol": "AAA.T", "return_pct": 0.0},
                {"symbol": "BBB.T", "return_pct": 0.0},
                {"symbol": "CCC.T", "return_pct": 0.0},
                {"symbol": "DDD.T", "return_pct": 4.0},
                {"symbol": "EEE.T", "return_pct": 0.0},
                {"symbol": "FFF.T", "return_pct": 0.0},
                {"symbol": "GGG.T", "return_pct": 0.0},
            ],
        },
    }

    result = run_walk_forward_experiment(
        start="2021-01-01",
        end="2021-12-31",
        train_months=6,
        validation_months=3,
        step_months=3,
        weight_grid=weight_grid,
        evaluate_training_window=lambda window, weights: {"return_pct": 1.0, "sharpe": 0.1},
        evaluate_validation_window=lambda window, weights: validation_scores[
            (window["validation_start"], window["validation_end"], weights)
        ],
        evaluate_baseline_window=lambda window: {"return_pct": 0.5, "sharpe": 0.05},
    )

    assert result["summary"]["top_contributors"] == [
        {"symbol": "DDD.T", "return_pct": 8.0},
        {"symbol": "AAA.T", "return_pct": 7.0},
        {"symbol": "BBB.T", "return_pct": 6.0},
    ]


def test_run_walk_forward_experiment_aggregates_universe_participation_summary():
    weight_grid = [(1.0, 0.0, 0.0, 0.0)]
    validation_scores = {
        ("2021-07-01", "2021-09-30", (1.0, 0.0, 0.0, 0.0)): {
            "return_pct": 1.0,
            "sharpe": 0.1,
            "requested_symbol_count": 10,
            "loaded_symbol_count": 8,
            "skipped_symbol_count": 2,
            "coverage_ratio": 0.8,
        },
        ("2021-10-01", "2021-12-31", (1.0, 0.0, 0.0, 0.0)): {
            "return_pct": 2.0,
            "sharpe": 0.2,
            "requested_symbol_count": 10,
            "loaded_symbol_count": 6,
            "skipped_symbol_count": 4,
            "coverage_ratio": 0.6,
        },
    }

    result = run_walk_forward_experiment(
        start="2021-01-01",
        end="2021-12-31",
        train_months=6,
        validation_months=3,
        step_months=3,
        weight_grid=weight_grid,
        evaluate_training_window=lambda window, weights: {"return_pct": 1.0, "sharpe": 0.1},
        evaluate_validation_window=lambda window, weights: validation_scores[
            (window["validation_start"], window["validation_end"], weights)
        ],
        evaluate_baseline_window=lambda window: {"return_pct": 0.5, "sharpe": 0.05},
    )

    assert result["summary"]["window_count"] == 2
    assert result["summary"]["avg_loaded_symbol_count"] == 7.0
    assert result["summary"]["avg_skipped_symbol_count"] == 3.0
    assert result["summary"]["avg_coverage_ratio"] == 0.7
    assert result["summary"]["min_loaded_symbol_count"] == 6
    assert result["summary"]["min_coverage_ratio"] == 0.6


def test_run_walk_forward_experiment_threads_universe_participation_fields_into_rows():
    weight_grid = [(1.0, 0.0, 0.0, 0.0)]
    validation_scores = {
        ("2021-07-01", "2021-09-30", (1.0, 0.0, 0.0, 0.0)): {
            "return_pct": 1.0,
            "sharpe": 0.1,
            "requested_symbol_count": 10,
            "loaded_symbol_count": 8,
            "skipped_symbol_count": 2,
            "coverage_ratio": 0.8,
        },
        ("2021-10-01", "2021-12-31", (1.0, 0.0, 0.0, 0.0)): {
            "return_pct": 2.0,
            "sharpe": 0.2,
            "requested_symbol_count": 10,
            "loaded_symbol_count": 6,
            "skipped_symbol_count": 4,
            "coverage_ratio": 0.6,
        },
    }

    result = run_walk_forward_experiment(
        start="2021-01-01",
        end="2021-12-31",
        train_months=6,
        validation_months=3,
        step_months=3,
        weight_grid=weight_grid,
        evaluate_training_window=lambda window, weights: {"return_pct": 1.0, "sharpe": 0.1},
        evaluate_validation_window=lambda window, weights: validation_scores[
            (window["validation_start"], window["validation_end"], weights)
        ],
        evaluate_baseline_window=lambda window: {"return_pct": 0.5, "sharpe": 0.05},
    )

    assert result["weights"]["requested_symbol_count"].tolist() == [10, 10]
    assert result["weights"]["loaded_symbol_count"].tolist() == [8, 6]
    assert result["weights"]["skipped_symbol_count"].tolist() == [2, 4]
    assert result["weights"]["coverage_ratio"].tolist() == [0.8, 0.6]


def test_run_walk_forward_experiment_omits_universe_participation_summary_when_not_provided():
    weight_grid = [(1.0, 0.0, 0.0, 0.0)]
    validation_scores = {
        ("2021-07-01", "2021-09-30", (1.0, 0.0, 0.0, 0.0)): {
            "return_pct": 1.0,
            "sharpe": 0.1,
        },
        ("2021-10-01", "2021-12-31", (1.0, 0.0, 0.0, 0.0)): {
            "return_pct": 2.0,
            "sharpe": 0.2,
        },
    }

    result = run_walk_forward_experiment(
        start="2021-01-01",
        end="2021-12-31",
        train_months=6,
        validation_months=3,
        step_months=3,
        weight_grid=weight_grid,
        evaluate_training_window=lambda window, weights: {"return_pct": 1.0, "sharpe": 0.1},
        evaluate_validation_window=lambda window, weights: validation_scores[
            (window["validation_start"], window["validation_end"], weights)
        ],
        evaluate_baseline_window=lambda window: {"return_pct": 0.5, "sharpe": 0.05},
    )

    for key in [
        "avg_loaded_symbol_count",
        "avg_skipped_symbol_count",
        "avg_coverage_ratio",
        "min_loaded_symbol_count",
        "min_coverage_ratio",
    ]:
        assert key not in result["summary"]


def test_run_walk_forward_experiment_omits_universe_participation_row_columns_when_not_provided():
    weight_grid = [(1.0, 0.0, 0.0, 0.0)]
    validation_scores = {
        ("2021-07-01", "2021-09-30", (1.0, 0.0, 0.0, 0.0)): {
            "return_pct": 1.0,
            "sharpe": 0.1,
        },
        ("2021-10-01", "2021-12-31", (1.0, 0.0, 0.0, 0.0)): {
            "return_pct": 2.0,
            "sharpe": 0.2,
        },
    }

    result = run_walk_forward_experiment(
        start="2021-01-01",
        end="2021-12-31",
        train_months=6,
        validation_months=3,
        step_months=3,
        weight_grid=weight_grid,
        evaluate_training_window=lambda window, weights: {"return_pct": 1.0, "sharpe": 0.1},
        evaluate_validation_window=lambda window, weights: validation_scores[
            (window["validation_start"], window["validation_end"], weights)
        ],
        evaluate_baseline_window=lambda window: {"return_pct": 0.5, "sharpe": 0.05},
    )

    for key in [
        "requested_symbol_count",
        "loaded_symbol_count",
        "skipped_symbol_count",
        "coverage_ratio",
    ]:
        assert key not in result["weights"].columns


def test_aggregate_universe_participation_summary_accepts_partial_window_metrics():
    summary = aggregate_universe_participation_summary(
        [
            {
                "loaded_symbol_count": 8,
                "skipped_symbol_count": 2,
                "coverage_ratio": 0.8,
            },
            {
                "requested_symbol_count": 10,
                "loaded_symbol_count": 6,
                "skipped_symbol_count": 4,
                "coverage_ratio": 0.6,
            },
        ]
    )

    assert summary == {
        "avg_loaded_symbol_count": 7.0,
        "avg_skipped_symbol_count": 3.0,
        "avg_coverage_ratio": 0.7,
        "min_loaded_symbol_count": 6,
        "min_coverage_ratio": 0.6,
    }


def test_run_walk_forward_optimization_prints_one_shot_comparison(monkeypatch, capsys):
    captured = {}

    def fake_run_walk_forward_experiment(**kwargs):
        captured["kwargs"] = kwargs
        return {
            "weights": pd.DataFrame(
                [
                    {
                        "rebalance_date": "2021-07-01",
                        "weight_mom": 1.0,
                        "weight_vol": 0.5,
                        "weight_rev": 0.0,
                    }
                ]
            ),
            "summary": {
                "window_count": 1,
                "baseline_return_pct": 1.0,
                "one_shot_return_pct": 1.4,
                "walk_forward_return_pct": 1.8,
                "one_shot_active_return_pct": 0.4,
                "active_return_pct": 0.8,
                "topx_return_pct": 0.9,
                "n225_return_pct": 1.1,
                "walk_forward_excess_vs_topx_pct": 0.9,
                "walk_forward_excess_vs_n225_pct": 0.7,
                "avg_hit_rate": 0.5,
                "avg_loaded_symbol_count": 28.0,
                "avg_skipped_symbol_count": 22.0,
                "avg_coverage_ratio": 0.56,
                "min_loaded_symbol_count": 24,
                "min_coverage_ratio": 0.48,
                "top_contributors": [{"symbol": "AAA.T", "return_pct": 1.2}],
                "bottom_contributors": [{"symbol": "BBB.T", "return_pct": -0.4}],
            },
        }

    monkeypatch.setattr(optimize, "run_walk_forward_experiment", fake_run_walk_forward_experiment)

    optimize.run_walk_forward_optimization(
        data_dfs={},
        start="2021-01-01",
        end="2021-12-31",
        artifact_dir=None,
    )

    assert captured["kwargs"]["evaluate_one_shot_training_window"] is not None
    assert captured["kwargs"]["evaluate_one_shot_validation_window"] is not None

    output = capsys.readouterr().out
    assert "One-shot optimized return total %" in output
    assert "Walk-forward return total %" in output
    assert "TOPX benchmark return total %" in output
    assert "N225 benchmark return total %" in output
    assert "Average window hit rate" in output
    assert "Top contributors" in output
    assert "Average loaded symbols" in output
    assert "Average skipped symbols" in output
    assert "Average coverage ratio" in output
    assert "Minimum coverage ratio" in output
    assert "28.0000" in output
    assert "0.4800" in output


def test_run_walk_forward_optimization_skips_universe_participation_section_when_absent(
    monkeypatch,
    capsys,
):
    def fake_run_walk_forward_experiment(**kwargs):
        del kwargs
        return {
            "weights": pd.DataFrame(
                [
                    {
                        "rebalance_date": "2021-07-01",
                        "weight_mom": 1.0,
                        "weight_vol": 0.5,
                        "weight_rev": 0.0,
                    }
                ]
            ),
            "summary": {
                "window_count": 1,
                "baseline_return_pct": 1.0,
                "walk_forward_return_pct": 1.8,
                "avg_hit_rate": 0.5,
                "top_contributors": [{"symbol": "AAA.T", "return_pct": 1.2}],
                "bottom_contributors": [{"symbol": "BBB.T", "return_pct": -0.4}],
            },
        }

    monkeypatch.setattr(optimize, "run_walk_forward_experiment", fake_run_walk_forward_experiment)

    optimize.run_walk_forward_optimization(
        data_dfs={},
        start="2021-01-01",
        end="2021-12-31",
        artifact_dir=None,
    )

    output = capsys.readouterr().out
    assert "Average loaded symbols" not in output
    assert "Average skipped symbols" not in output
    assert "Average coverage ratio" not in output
    assert "Minimum coverage ratio" not in output


def test_run_walk_forward_optimization_computes_partial_universe_coverage(monkeypatch):
    captured = {}

    def fake_run_walk_forward_experiment(**kwargs):
        captured["validation_metrics"] = kwargs["evaluate_validation_window"](
            {
                "validation_start": "2021-07-01",
                "validation_end": "2021-09-30",
            },
            (1.0, 0.0, 0.0, 0.0),
        )
        return {
            "weights": pd.DataFrame(),
            "summary": {
                "window_count": 1,
                "baseline_return_pct": 0.0,
                "walk_forward_return_pct": 0.0,
            },
        }

    monkeypatch.setattr(optimize, "run_walk_forward_experiment", fake_run_walk_forward_experiment)
    monkeypatch.setattr(
        optimize,
        "evaluate_weight_tuple",
        lambda data_dfs, start, end, weights: {"return_pct": 1.0, "sharpe": 0.1},
    )

    data_dfs = {
        "AAA.T": pd.DataFrame({"Close": [100.0, 101.0]}, index=pd.to_datetime(["2021-07-01", "2021-09-30"])),
        "BBB.T": pd.DataFrame({"Close": [99.0, 98.0]}, index=pd.to_datetime(["2021-05-01", "2021-05-31"])),
    }

    optimize.run_walk_forward_optimization(
        data_dfs=data_dfs,
        start="2021-01-01",
        end="2021-12-31",
        artifact_dir=None,
        universe_name="japan_large_30",
        universe_symbols=["AAA.T", "BBB.T", "CCC.T"],
    )

    assert captured["validation_metrics"]["requested_symbol_count"] == 3
    assert captured["validation_metrics"]["loaded_symbol_count"] == 1
    assert captured["validation_metrics"]["skipped_symbol_count"] == 2
    assert captured["validation_metrics"]["coverage_ratio"] == 0.3333


def test_run_walk_forward_optimization_forwards_top_n_to_all_evaluators(monkeypatch):
    captured_kwargs = []

    def fake_evaluate_weight_tuple(*args, **kwargs):
        del args
        captured_kwargs.append(kwargs)
        return {"return_pct": 1.0, "sharpe": 0.1, "drawdown": 0.0}

    def fake_run_walk_forward_experiment(**kwargs):
        window = {
            "train_start": "2021-01-01",
            "train_end": "2021-06-30",
            "validation_start": "2021-07-01",
            "validation_end": "2021-12-31",
        }
        kwargs["evaluate_training_window"](window, (1.0, 0.0, 0.0, 0.0))
        kwargs["evaluate_validation_window"](window, (1.0, 0.0, 0.0, 0.0))
        kwargs["evaluate_baseline_window"](window)
        kwargs["evaluate_one_shot_training_window"]((1.0, 0.0, 0.0, 0.0))
        kwargs["evaluate_one_shot_validation_window"](window, (1.0, 0.0, 0.0, 0.0))
        return {
            "weights": pd.DataFrame(),
            "summary": {
                "window_count": 1,
                "baseline_return_pct": 0.0,
                "walk_forward_return_pct": 0.0,
            },
        }

    monkeypatch.setattr(optimize, "evaluate_weight_tuple", fake_evaluate_weight_tuple)
    monkeypatch.setattr(optimize, "run_walk_forward_experiment", fake_run_walk_forward_experiment)
    book_values = lambda as_of_date: {"AAA.T": 100.0}

    optimize.run_walk_forward_optimization(
        data_dfs={"AAA.T": pd.DataFrame({"Close": [100.0]}, index=[pd.Timestamp("2021-07-01")])},
        start="2021-01-01",
        end="2021-12-31",
        artifact_dir=None,
        universe_symbols=["AAA.T"],
        top_n=2,
        book_values=book_values,
    )

    assert [kwargs.get("top_n") for kwargs in captured_kwargs] == [2, 2, 2, 2, 2]
    assert [kwargs.get("book_values") for kwargs in captured_kwargs] == [book_values] * 5


def test_run_walk_forward_optimization_forwards_roe_values_to_all_evaluators(monkeypatch):
    captured_kwargs = []

    def fake_evaluate_weight_tuple(*args, **kwargs):
        del args
        captured_kwargs.append(kwargs)
        return {"return_pct": 1.0, "sharpe": 0.1, "drawdown": 0.0}

    def fake_run_walk_forward_experiment(**kwargs):
        window = {
            "train_start": "2021-01-01",
            "train_end": "2021-06-30",
            "validation_start": "2021-07-01",
            "validation_end": "2021-12-31",
        }
        kwargs["evaluate_training_window"](window, (0.0, 1.0, 0.0, 0.5, 1.0))
        kwargs["evaluate_validation_window"](window, (0.0, 1.0, 0.0, 0.5, 1.0))
        kwargs["evaluate_baseline_window"](window)
        kwargs["evaluate_one_shot_training_window"]((0.0, 1.0, 0.0, 0.5, 1.0))
        kwargs["evaluate_one_shot_validation_window"](window, (0.0, 1.0, 0.0, 0.5, 1.0))
        return {
            "weights": pd.DataFrame(),
            "summary": {
                "window_count": 1,
                "baseline_return_pct": 0.0,
                "walk_forward_return_pct": 0.0,
            },
        }

    monkeypatch.setattr(optimize, "evaluate_weight_tuple", fake_evaluate_weight_tuple)
    monkeypatch.setattr(optimize, "run_walk_forward_experiment", fake_run_walk_forward_experiment)
    roe_values = {"AAA.T": 0.2}

    optimize.run_walk_forward_optimization(
        data_dfs={"AAA.T": pd.DataFrame({"Close": [100.0]}, index=[pd.Timestamp("2021-07-01")])},
        start="2021-01-01",
        end="2021-12-31",
        artifact_dir=None,
        universe_symbols=["AAA.T"],
        roe_values=roe_values,
        n_factors=5,
    )

    assert [kwargs.get("roe_values") for kwargs in captured_kwargs] == [roe_values] * 5


def test_run_walk_forward_optimization_smoke_test_with_offline_stubbed_evaluator(
    monkeypatch,
    tmp_path: Path,
):
    def fake_evaluate_weight_tuple(data_dfs, start, end, weights, **kwargs):
        del data_dfs
        if (start, end) == ("2021-01-01", "2021-12-31"):
            if weights == (1.0, 0.0, 0.0, 0.0):
                return {"return_pct": 2.0, "sharpe": 0.2, "drawdown": 1.0}
            return {"return_pct": 3.0, "sharpe": 0.3, "drawdown": 1.0}
        if (start, end) == ("2021-01-01", "2021-06-30"):
            if weights == (1.0, 0.0, 0.0, 0.0):
                return {"return_pct": 5.0, "sharpe": 0.5, "drawdown": 1.0}
            return {"return_pct": 3.0, "sharpe": 0.3, "drawdown": 1.0}
        if (start, end) == ("2021-07-01", "2021-12-31"):
            if weights == (1.0, 0.0, 0.0, 0.0):
                return {"return_pct": 1.8, "sharpe": 0.18, "drawdown": 1.0}
            if weights == (1.0, 1.0, 1.0):
                return {"return_pct": 1.0, "sharpe": 0.1, "drawdown": 1.0}
            return {"return_pct": 1.4, "sharpe": 0.14, "drawdown": 1.0}
        raise AssertionError(f"Unexpected window: {(start, end, weights)}")

    monkeypatch.setattr(optimize, "DEFAULT_WEIGHT_GRID", [(1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0)])
    monkeypatch.setattr(optimize, "DEFAULT_BASELINE_WEIGHTS", (1.0, 1.0, 1.0))
    monkeypatch.setattr(optimize, "evaluate_weight_tuple", fake_evaluate_weight_tuple)

    result = optimize.run_walk_forward_optimization(
        data_dfs={"AAA.T": pd.DataFrame()},
        start="2021-01-01",
        end="2021-12-31",
        train_months=6,
        validation_months=6,
        step_months=6,
        artifact_dir=tmp_path,
        universe_name="topix_top_10",
        universe_symbols=["AAA.T"],
    )

    assert result["summary"] == {
        "window_count": 1,
        "baseline_return_pct": 1.0,
        "one_shot_return_pct": 1.4,
        "walk_forward_return_pct": 1.8,
        "one_shot_active_return_pct": 0.4,
        "active_return_pct": 0.8,
        "avg_hit_rate": None,
        "avg_loaded_symbol_count": 0.0,
        "avg_skipped_symbol_count": 1.0,
        "avg_coverage_ratio": 0.0,
        "min_loaded_symbol_count": 0,
        "min_coverage_ratio": 0.0,
        "top_contributors": [],
        "bottom_contributors": [],
    }

    artifacts = result["artifacts"]
    assert artifacts["run_dir"].exists()
    metadata = json.loads(artifacts["metadata"].read_text(encoding="utf-8"))
    summary = json.loads(artifacts["summary"].read_text(encoding="utf-8"))
    saved_weights = pd.read_csv(artifacts["weights"])

    assert metadata["start"] == "2021-01-01"
    assert metadata["end"] == "2021-12-31"
    assert metadata["one_shot_weights"] == {"mom": 0.0, "vol": 1.0, "rev": 0.0}
    assert metadata["universe_name"] == "topix_top_10"
    assert metadata["universe_symbols"] == ["AAA.T"]
    assert summary == result["summary"]
    assert saved_weights["rebalance_date"].tolist() == ["2021-07-01"]


def test_run_walk_forward_optimization_omits_universe_participation_without_universe_symbols(monkeypatch):
    def fake_run_walk_forward_experiment(**kwargs):
        return {
            "weights": pd.DataFrame(),
            "summary": {
                "window_count": 1,
                "baseline_return_pct": 1.0,
                "walk_forward_return_pct": 1.8,
            },
        }

    monkeypatch.setattr(optimize, "run_walk_forward_experiment", fake_run_walk_forward_experiment)

    result = optimize.run_walk_forward_optimization(
        data_dfs={"AAA.T": pd.DataFrame()},
        start="2021-01-01",
        end="2021-12-31",
        artifact_dir=None,
        universe_name=None,
        universe_symbols=None,
    )

    for key in (
        "avg_loaded_symbol_count",
        "avg_skipped_symbol_count",
        "avg_coverage_ratio",
        "min_loaded_symbol_count",
        "min_coverage_ratio",
    ):
        assert key not in result["summary"]


def test_optimize_main_prints_friendly_error_when_walk_forward_run_fails(monkeypatch, capsys):
    monkeypatch.setattr(optimize, "get_topix_top_10", lambda: ["AAA.T"])
    monkeypatch.setattr(optimize, "fetch_universe", lambda *args, **kwargs: {"AAA.T": pd.DataFrame()})

    def fail_run_walk_forward_optimization(**kwargs):
        del kwargs
        raise ValueError("bad walk-forward configuration")

    monkeypatch.setattr(optimize, "run_walk_forward_optimization", fail_run_walk_forward_optimization)

    exit_code = optimize.main()

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Walk-forward optimization failed:" in output
    assert "bad walk-forward configuration" in output


def test_optimize_main_uses_default_research_window_and_cli_defaults(monkeypatch):
    captured = {"fetch_calls": []}

    monkeypatch.setattr(optimize, "get_topix_top_10", lambda: ["AAA.T"])

    def fake_fetch_universe(symbols, start, end):
        captured["fetch_calls"].append({
            "symbols": symbols,
            "start": start,
            "end": end,
        })
        if symbols == ["AAA.T"]:
            return {"AAA.T": pd.DataFrame()}
        return {
            "1306.T": pd.DataFrame(),
            "1321.T": pd.DataFrame(),
        }

    def fake_run_walk_forward_optimization(**kwargs):
        captured["run"] = kwargs
        return {"weights": pd.DataFrame(), "summary": {"window_count": 0, "baseline_return_pct": 0.0, "walk_forward_return_pct": 0.0}}

    monkeypatch.setattr(optimize, "fetch_universe", fake_fetch_universe)
    monkeypatch.setattr(optimize, "run_walk_forward_optimization", fake_run_walk_forward_optimization)

    exit_code = optimize.main([])

    assert exit_code == 0
    assert captured["fetch_calls"][0]["symbols"] == ["AAA.T"]
    assert captured["fetch_calls"][0]["start"] == "2021-01-01"
    assert captured["fetch_calls"][0]["end"] == "2024-01-01"
    assert captured["fetch_calls"][1]["symbols"] == ["1306.T", "1321.T"]
    assert captured["fetch_calls"][1]["start"] == "2021-01-01"
    assert captured["fetch_calls"][1]["end"] == "2024-01-01"
    assert captured["run"]["start"] == "2021-01-01"
    assert captured["run"]["end"] == "2024-01-01"
    assert captured["run"]["train_months"] == 12
    assert captured["run"]["validation_months"] == 6
    assert captured["run"]["step_months"] == 6
    assert captured["run"]["top_n"] == 10
    assert set(captured["run"]["benchmark_data_dfs"]) == {"topx", "n225"}


def test_optimize_main_can_select_a_named_universe(monkeypatch):
    captured = {"fetch_calls": []}

    def fake_get_universe(name):
        assert name == "growth_universe"
        return ["AAA.T", "BBB.T"]

    def fake_fetch_universe(symbols, start, end):
        captured["fetch_calls"].append({
            "symbols": symbols,
            "start": start,
            "end": end,
        })
        if symbols == ["AAA.T", "BBB.T"]:
            return {
                "AAA.T": pd.DataFrame(),
                "BBB.T": pd.DataFrame(),
            }
        return {
            "1306.T": pd.DataFrame(),
            "1321.T": pd.DataFrame(),
        }

    def fake_run_walk_forward_optimization(**kwargs):
        captured["run"] = kwargs
        return {"weights": pd.DataFrame(), "summary": {"window_count": 0, "baseline_return_pct": 0.0, "walk_forward_return_pct": 0.0}}

    monkeypatch.setattr(optimize, "get_universe", fake_get_universe)
    monkeypatch.setattr(optimize, "fetch_universe", fake_fetch_universe)
    monkeypatch.setattr(optimize, "run_walk_forward_optimization", fake_run_walk_forward_optimization)

    exit_code = optimize.main(["--universe-name", "growth_universe"])

    assert exit_code == 0
    assert captured["fetch_calls"][0]["symbols"] == ["AAA.T", "BBB.T"]
    assert captured["run"]["universe_name"] == "growth_universe"
    assert captured["run"]["universe_symbols"] == ["AAA.T", "BBB.T"]


def test_optimize_main_rejects_unknown_named_universe_with_friendly_error(capsys):
    exit_code = optimize.main(["--universe-name", "unknown_universe"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Invalid universe name: unknown_universe" in output
    assert "Available universes: topix_top_10" in output


def test_optimize_main_accepts_cli_overrides_for_window_parameters(monkeypatch):
    captured = {"fetch_calls": []}

    monkeypatch.setattr(optimize, "get_topix_top_10", lambda: ["AAA.T"])

    def fake_fetch_universe(symbols, start, end):
        captured["fetch_calls"].append({
            "symbols": symbols,
            "start": start,
            "end": end,
        })
        if symbols == ["AAA.T"]:
            return {"AAA.T": pd.DataFrame()}
        return {
            "1306.T": pd.DataFrame(),
            "1321.T": pd.DataFrame(),
        }

    def fake_run_walk_forward_optimization(**kwargs):
        captured["run"] = kwargs
        return {"weights": pd.DataFrame(), "summary": {"window_count": 0, "baseline_return_pct": 0.0, "walk_forward_return_pct": 0.0}}

    monkeypatch.setattr(optimize, "fetch_universe", fake_fetch_universe)
    monkeypatch.setattr(optimize, "run_walk_forward_optimization", fake_run_walk_forward_optimization)

    exit_code = optimize.main(
        [
            "--start",
            "2024-01-04",
            "--end",
            "2025-12-30",
            "--train-months",
            "9",
            "--validation-months",
            "3",
            "--step-months",
            "3",
            "--artifact-dir",
            "/tmp/custom-artifacts",
        ]
    )

    assert exit_code == 0
    assert captured["fetch_calls"][0]["start"] == "2024-01-04"
    assert captured["fetch_calls"][0]["end"] == "2025-12-30"
    assert captured["fetch_calls"][1]["symbols"] == ["1306.T", "1321.T"]
    assert captured["fetch_calls"][1]["start"] == "2024-01-04"
    assert captured["fetch_calls"][1]["end"] == "2025-12-30"
    assert captured["run"]["start"] == "2024-01-04"
    assert captured["run"]["end"] == "2025-12-30"
    assert captured["run"]["train_months"] == 9
    assert captured["run"]["validation_months"] == 3
    assert captured["run"]["step_months"] == 3
    assert str(captured["run"]["artifact_dir"]) == "/tmp/custom-artifacts"


def test_run_walk_forward_optimization_passes_benchmark_evaluators(monkeypatch):
    captured = {}

    def fake_run_walk_forward_experiment(**kwargs):
        captured["kwargs"] = kwargs
        return {
            "weights": pd.DataFrame(),
            "summary": {
                "window_count": 0,
                "baseline_return_pct": 0.0,
                "walk_forward_return_pct": 0.0,
            },
        }

    monkeypatch.setattr(optimize, "run_walk_forward_experiment", fake_run_walk_forward_experiment)

    result = optimize.run_walk_forward_optimization(
        data_dfs={},
        start="2021-01-01",
        end="2021-12-31",
        artifact_dir=None,
        benchmark_data_dfs={
            "topx": pd.DataFrame({"Close": [100, 101]}, index=pd.to_datetime(["2021-07-01", "2021-12-31"])),
            "n225": pd.DataFrame({"Close": [200, 210]}, index=pd.to_datetime(["2021-07-01", "2021-12-31"])),
        },
    )

    assert result["summary"]["window_count"] == 0
    assert set(captured["kwargs"]["evaluate_benchmark_windows"]) == {"topx", "n225"}


def test_optimize_main_continues_when_benchmark_fetch_fails(monkeypatch, capsys):
    monkeypatch.setattr(optimize, "get_topix_top_10", lambda: ["AAA.T"])

    def fake_fetch_universe(symbols, start, end):
        del start, end
        if symbols == ["AAA.T"]:
            return {"AAA.T": pd.DataFrame()}
        raise RuntimeError("benchmark source unavailable")

    def fake_run_walk_forward_optimization(**kwargs):
        return {
            "weights": pd.DataFrame(),
            "summary": {
                "window_count": 0,
                "baseline_return_pct": 0.0,
                "walk_forward_return_pct": 0.0,
            },
            "captured_benchmarks": kwargs["benchmark_data_dfs"],
        }

    monkeypatch.setattr(optimize, "fetch_universe", fake_fetch_universe)
    monkeypatch.setattr(optimize, "run_walk_forward_optimization", fake_run_walk_forward_optimization)

    exit_code = optimize.main([])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Benchmark data fetch skipped:" in output


def test_run_walk_forward_experiment_records_momentum_definition_in_metadata():
    result = run_walk_forward_experiment(
        start="2021-01-01",
        end="2021-12-31",
        train_months=6,
        validation_months=6,
        step_months=6,
        weight_grid=[(1.0, 0.0, 0.0, 0.0)],
        evaluate_training_window=lambda window, weights: {"return_pct": 1.0, "sharpe": 0.1},
        evaluate_validation_window=lambda window, weights: {"return_pct": 1.1, "sharpe": 0.1},
        evaluate_baseline_window=lambda window: {"return_pct": 0.9, "sharpe": 0.1},
        momentum_definition="12_1",
    )

    assert result["metadata"]["momentum_definition"] == "12_1"


def _make_local_frame(start: str, periods: int) -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="B")
    return pd.DataFrame(
        {
            "Close": [100.0 + i for i in range(len(index))],
            "Volume": [1000 for _ in range(len(index))],
        },
        index=index,
    )


def test_walk_forward_research_can_load_local_data_without_calling_network_fetcher(
    monkeypatch,
    tmp_path: Path,
):
    symbols = ["AAA.T", "BBB.T"]
    frames = {symbol: _make_local_frame("2023-07-03", 280) for symbol in symbols}

    def fetcher(symbol: str, start: str, end: str) -> pd.DataFrame:
        del start, end
        return frames[symbol].copy()

    local_store.sync_universe_history(
        symbols,
        "2023-07-03",
        "2024-05-31",
        root=tmp_path,
        fetcher=fetcher,
    )

    monkeypatch.setattr(
        optimize,
        "fetch_universe",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network fetcher called")),
    )

    def fake_eval(
        data_dfs,
        start,
        end,
        weights,
        momentum_definition="90d",
        evaluation_start=None,
        evaluation_end=None,
        reversal_filter_params=None,
        engine="backtrader",
        book_values=None,
    ):
        del start, end, weights, evaluation_start, evaluation_end, engine, book_values
        assert set(data_dfs) == set(symbols)
        assert momentum_definition == "90d"
        return {"return_pct": 0.0, "sharpe": 0.0, "drawdown": 0.0, "symbol_returns": []}

    monkeypatch.setattr(optimize, "evaluate_weight_tuple", fake_eval)

    result = optimize.run_walk_forward_optimization(
        data_dfs=None,
        start="2024-01-01",
        end="2024-05-31",
        train_months=2,
        validation_months=1,
        step_months=1,
        artifact_dir=None,
        universe_name="local_test",
        universe_symbols=symbols,
        local_store_root=tmp_path,
    )

    assert int(result["summary"]["window_count"]) >= 1


def test_walk_forward_local_optimize_defaults_to_current_directory_root(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.chdir(tmp_path)

    symbols = ["AAA.T"]
    frames = {symbol: _make_local_frame("2023-07-03", 280) for symbol in symbols}

    def fetcher(symbol: str, start: str, end: str) -> pd.DataFrame:
        del start, end
        return frames[symbol].copy()

    # Root omitted intentionally: should resolve to current directory (tmp_path).
    local_store.sync_universe_history(
        symbols,
        "2023-07-03",
        "2024-05-31",
        fetcher=fetcher,
    )

    monkeypatch.setattr(
        optimize,
        "fetch_universe",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network fetcher called")),
    )

    def fake_eval(
        data_dfs,
        start,
        end,
        weights,
        momentum_definition="90d",
        evaluation_start=None,
        evaluation_end=None,
        reversal_filter_params=None,
        engine="backtrader",
        book_values=None,
    ):
        del start, end, weights, evaluation_start, evaluation_end, engine, book_values
        assert set(data_dfs) == set(symbols)
        assert momentum_definition == "90d"
        return {"return_pct": 0.0, "sharpe": 0.0, "drawdown": 0.0, "symbol_returns": []}

    monkeypatch.setattr(optimize, "evaluate_weight_tuple", fake_eval)

    result = optimize.run_walk_forward_optimization(
        data_dfs=None,
        start="2024-01-01",
        end="2024-05-31",
        train_months=2,
        validation_months=1,
        step_months=1,
        artifact_dir=None,
        universe_name="local_test",
        universe_symbols=symbols,
        # local_store_root omitted intentionally.
    )

    assert int(result["summary"]["window_count"]) >= 1


def test_local_walk_forward_loads_include_enough_warmup_for_short_validation_windows(
    monkeypatch,
    tmp_path: Path,
):
    symbols = ["AAA.T"]
    frames = {symbol: _make_local_frame("2023-07-03", 280) for symbol in symbols}

    def fetcher(symbol: str, start: str, end: str) -> pd.DataFrame:
        del start, end
        return frames[symbol].copy()

    local_store.sync_universe_history(
        symbols,
        "2023-07-03",
        "2024-05-31",
        root=tmp_path,
        fetcher=fetcher,
    )

    seen_eval_windows: list[tuple[str, str]] = []

    def fake_eval(
        data_dfs,
        start,
        end,
        weights,
        momentum_definition="90d",
        evaluation_start=None,
        evaluation_end=None,
        reversal_filter_params=None,
        engine="backtrader",
        book_values=None,
    ):
        del data_dfs, end, weights, momentum_definition, evaluation_end, engine, book_values
        if evaluation_start is not None:
            seen_eval_windows.append((start, evaluation_start))
        return {"return_pct": 0.0, "sharpe": 0.0, "drawdown": 0.0, "symbol_returns": []}

    monkeypatch.setattr(optimize, "evaluate_weight_tuple", fake_eval)

    optimize.run_walk_forward_optimization(
        data_dfs=None,
        start="2024-01-01",
        end="2024-05-31",
        train_months=2,
        validation_months=1,
        step_months=1,
        artifact_dir=None,
        universe_name="local_test",
        universe_symbols=symbols,
        local_store_root=tmp_path,
    )

    assert any(
        pd.Timestamp(slice_start) < pd.Timestamp(eval_start)
        for slice_start, eval_start in seen_eval_windows
    )


def test_local_optimize_insufficient_warmup_raises_sync_required(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)

    symbols = ["AAA.T"]
    frames = {symbol: _make_local_frame("2024-02-15", 80) for symbol in symbols}

    def fetcher(symbol: str, start: str, end: str) -> pd.DataFrame:
        del start, end
        return frames[symbol].copy()

    local_store.sync_universe_history(
        symbols,
        "2024-02-15",
        "2024-05-31",
        fetcher=fetcher,
    )

    with pytest.raises(local_store.LocalDataSyncRequiredError) as excinfo:
        optimize.run_walk_forward_optimization(
            data_dfs=None,
            start="2024-03-01",
            end="2024-04-30",
            train_months=1,
            validation_months=1,
            step_months=1,
            artifact_dir=None,
            universe_name="local_test",
            universe_symbols=symbols,
            local_warmup_bars=50,
        )

    message = str(excinfo.value).lower()
    assert "warmup" in message
    assert "pre-start" in message or "before" in message
    assert "sync" in message


def test_local_optimize_requests_12_1_specific_warmup(monkeypatch, tmp_path: Path):
    requested_warmups: list[int] = []

    def fake_load_local_universe(
        symbols,
        start_date,
        end_date,
        warmup=0,
        strict_warmup=False,
        allowed_validation_statuses=("ok",),
        root=None,
    ):
        del start_date, end_date, strict_warmup, allowed_validation_statuses, root
        requested_warmups.append(int(warmup))
        frame = pd.DataFrame(
            {"Date": pd.date_range("2020-01-01", periods=400, freq="B"), "Close": range(400)},
        )
        return {symbol: frame.copy() for symbol in symbols}

    def fake_eval(
        data_dfs,
        start,
        end,
        weights,
        momentum_definition="90d",
        evaluation_start=None,
        evaluation_end=None,
        reversal_filter_params=None,
        engine="backtrader",
        book_values=None,
    ):
        del data_dfs, start, end, weights, evaluation_start, evaluation_end, engine, book_values
        assert momentum_definition == "12_1"
        return {"return_pct": 0.0, "sharpe": 0.0, "drawdown": 0.0, "symbol_returns": []}

    monkeypatch.setattr(local_store, "load_local_universe", fake_load_local_universe)
    monkeypatch.setattr(optimize, "evaluate_weight_tuple", fake_eval)

    optimize.run_walk_forward_optimization(
        data_dfs=None,
        start="2024-01-01",
        end="2024-05-31",
        train_months=2,
        validation_months=1,
        step_months=1,
        artifact_dir=None,
        universe_name="local_test",
        universe_symbols=["AAA.T"],
        local_store_root=tmp_path,
        momentum_definition="12_1",
    )

    assert requested_warmups
    assert min(requested_warmups) >= 273


def test_missing_local_validated_coverage_raises_clear_sync_required_error(
    tmp_path: Path,
):
    symbols = ["AAA.T"]
    frames = {symbol: _make_local_frame("2024-01-01", 20) for symbol in symbols}

    def fetcher(symbol: str, start: str, end: str) -> pd.DataFrame:
        del start, end
        return frames[symbol].copy()

    local_store.sync_universe_history(
        symbols,
        "2024-01-01",
        "2024-01-31",
        root=tmp_path,
        fetcher=fetcher,
    )

    with pytest.raises(local_store.LocalDataSyncRequiredError) as excinfo:
        optimize.run_walk_forward_optimization(
            data_dfs=None,
            start="2024-01-01",
            end="2024-05-31",
            train_months=2,
            validation_months=1,
            step_months=1,
            artifact_dir=None,
            universe_name="local_test",
            universe_symbols=symbols,
            local_store_root=tmp_path,
        )

    assert "sync" in str(excinfo.value).lower()


def test_run_walk_forward_optimization_defaults_to_90d_momentum(monkeypatch):
    captured = {}

    def fake_run_walk_forward_experiment(**kwargs):
        captured["kwargs"] = kwargs
        return {
            "weights": pd.DataFrame(),
            "summary": {
                "window_count": 0,
                "baseline_return_pct": 0.0,
                "walk_forward_return_pct": 0.0,
            },
            "metadata": {},
        }

    monkeypatch.setattr(optimize, "run_walk_forward_experiment", fake_run_walk_forward_experiment)

    optimize.run_walk_forward_optimization(
        data_dfs={},
        start="2021-01-01",
        end="2021-12-31",
        artifact_dir=None,
    )

    assert captured["kwargs"]["momentum_definition"] == "90d"


def test_run_walk_forward_optimization_accepts_12_1_momentum_override(monkeypatch):
    captured = {}

    def fake_evaluate_weight_tuple(
        data_dfs,
        start,
        end,
        weights,
        momentum_definition="90d",
        evaluation_start=None,
        evaluation_end=None,
        reversal_filter_params=None,
        engine="backtrader",
    ):
        del data_dfs, start, end, weights, evaluation_start, evaluation_end, engine
        return {
            "return_pct": 1.0,
            "sharpe": 0.1,
            "scores": pd.DataFrame(
                [
                    {
                        "symbol": "AAA.T",
                        "mom_raw": 12.0 if momentum_definition == "12_1" else 9.0,
                    }
                ]
            ),
        }

    def fake_run_walk_forward_experiment(**kwargs):
        captured["kwargs"] = kwargs
        captured["validation_metrics"] = kwargs["evaluate_validation_window"](
            {
                "validation_start": "2021-07-01",
                "validation_end": "2021-12-31",
            },
            (1.0, 0.0, 0.0, 0.0),
        )
        return {
            "weights": pd.DataFrame(),
            "summary": {
                "window_count": 1,
                "baseline_return_pct": 0.0,
                "walk_forward_return_pct": 1.0,
            },
            "metadata": {},
        }

    monkeypatch.setattr(optimize, "evaluate_weight_tuple", fake_evaluate_weight_tuple)
    monkeypatch.setattr(optimize, "run_walk_forward_experiment", fake_run_walk_forward_experiment)

    optimize.run_walk_forward_optimization(
        data_dfs={"AAA.T": pd.DataFrame({"Close": [100.0, 101.0]})},
        start="2021-01-01",
        end="2021-12-31",
        artifact_dir=None,
        momentum_definition="12_1",
    )

    assert captured["kwargs"]["momentum_definition"] == "12_1"
    assert captured["validation_metrics"]["scores"]["mom_raw"].tolist() == [12.0]


def test_run_walk_forward_optimization_rejects_unknown_momentum_definition():
    with pytest.raises(ValueError, match="Unsupported momentum_definition"):
        optimize.run_walk_forward_optimization(
            data_dfs={},
            start="2021-01-01",
            end="2021-12-31",
            artifact_dir=None,
            momentum_definition="bad_value",
        )


def test_run_walk_forward_optimization_persists_momentum_definition_metadata(monkeypatch, tmp_path):
    def fake_run_walk_forward_experiment(**kwargs):
        return {
            "weights": pd.DataFrame(),
            "summary": {
                "window_count": 0,
                "baseline_return_pct": 0.0,
                "walk_forward_return_pct": 0.0,
            },
            "metadata": {
                "momentum_definition": kwargs["momentum_definition"],
            },
        }

    monkeypatch.setattr(optimize, "run_walk_forward_experiment", fake_run_walk_forward_experiment)

    result = optimize.run_walk_forward_optimization(
        data_dfs={},
        start="2021-01-01",
        end="2021-12-31",
        artifact_dir=tmp_path,
        momentum_definition="12_1",
    )

    assert result["metadata"]["momentum_definition"] == "12_1"
    metadata = json.loads(result["artifacts"]["metadata"].read_text(encoding="utf-8"))
    assert metadata["momentum_definition"] == "12_1"
