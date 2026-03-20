import json
from pathlib import Path

import backtrader as bt
import pandas as pd

import src.optimize as optimize
from src.research.walk_forward import (
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


def test_select_best_weights_picks_highest_scoring_weight_tuple():
    leaderboard = select_best_weights(
        weight_grid=[(0.0, 0.0, 1.0), (1.0, 0.5, 0.0), (1.0, 1.0, 1.0)],
        evaluate=lambda weights: {
            (0.0, 0.0, 1.0): {"return_pct": 1.0, "sharpe": 0.1},
            (1.0, 0.5, 0.0): {"return_pct": 4.0, "sharpe": 0.2},
            (1.0, 1.0, 1.0): {"return_pct": 3.0, "sharpe": 0.5},
        }[weights],
    )

    assert leaderboard["best"]["weights"] == {"mom": 1.0, "vol": 0.5, "rev": 0.0}
    assert leaderboard["rows"][0]["return_pct"] == 4.0


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


def test_run_walk_forward_experiment_returns_rebalance_weights_and_summary():
    weight_grid = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    one_shot_weights = (0.0, 1.0, 0.0)
    training_scores = {
        ("2021-01-01", "2021-06-30", (1.0, 0.0, 0.0)): {"return_pct": 5.0, "sharpe": 0.5},
        ("2021-01-01", "2021-06-30", (0.0, 1.0, 0.0)): {"return_pct": 3.0, "sharpe": 0.2},
        ("2021-04-01", "2021-09-30", (1.0, 0.0, 0.0)): {"return_pct": 2.0, "sharpe": 0.1},
        ("2021-04-01", "2021-09-30", (0.0, 1.0, 0.0)): {"return_pct": 4.0, "sharpe": 0.3},
    }
    validation_scores = {
        ("2021-07-01", "2021-09-30", (1.0, 0.0, 0.0)): {
            "return_pct": 1.5,
            "sharpe": 0.15,
            "symbol_returns": [
                {"symbol": "AAA.T", "return_pct": 2.0},
                {"symbol": "BBB.T", "return_pct": -0.5},
            ],
        },
        ("2021-10-01", "2021-12-31", (0.0, 1.0, 0.0)): {
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
        ("2021-01-01", "2021-06-30", (1.0, 0.0, 0.0)): {"return_pct": 2.0, "sharpe": 0.2},
        ("2021-01-01", "2021-06-30", (0.0, 1.0, 0.0)): {"return_pct": 3.5, "sharpe": 0.35},
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
        "baseline_return_pct": 2.2,
        "one_shot_return_pct": 3.2,
        "walk_forward_return_pct": 4.0,
        "one_shot_active_return_pct": 1.0,
        "active_return_pct": 1.8,
        "topx_return_pct": 1.9,
        "n225_return_pct": 2.1,
        "walk_forward_excess_vs_topx_pct": 2.1,
        "walk_forward_excess_vs_n225_pct": 1.9,
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


def test_run_walk_forward_experiment_aggregates_summary_contributors_from_full_symbol_returns():
    weight_grid = [(1.0, 0.0, 0.0)]
    validation_scores = {
        ("2021-07-01", "2021-09-30", (1.0, 0.0, 0.0)): {
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
        ("2021-10-01", "2021-12-31", (1.0, 0.0, 0.0)): {
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


def test_run_walk_forward_optimization_smoke_test_with_offline_stubbed_evaluator(
    monkeypatch,
    tmp_path: Path,
):
    def fake_evaluate_weight_tuple(data_dfs, start, end, weights):
        del data_dfs
        if (start, end) == ("2021-01-01", "2021-12-31"):
            if weights == (1.0, 0.0, 0.0):
                return {"return_pct": 2.0, "sharpe": 0.2, "drawdown": 1.0}
            return {"return_pct": 3.0, "sharpe": 0.3, "drawdown": 1.0}
        if (start, end) == ("2021-01-01", "2021-06-30"):
            if weights == (1.0, 0.0, 0.0):
                return {"return_pct": 5.0, "sharpe": 0.5, "drawdown": 1.0}
            return {"return_pct": 3.0, "sharpe": 0.3, "drawdown": 1.0}
        if (start, end) == ("2021-07-01", "2021-12-31"):
            if weights == (1.0, 0.0, 0.0):
                return {"return_pct": 1.8, "sharpe": 0.18, "drawdown": 1.0}
            if weights == (1.0, 1.0, 1.0):
                return {"return_pct": 1.0, "sharpe": 0.1, "drawdown": 1.0}
            return {"return_pct": 1.4, "sharpe": 0.14, "drawdown": 1.0}
        raise AssertionError(f"Unexpected window: {(start, end, weights)}")

    monkeypatch.setattr(optimize, "DEFAULT_WEIGHT_GRID", [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)])
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
