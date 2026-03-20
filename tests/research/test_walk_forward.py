import json
from pathlib import Path

import pandas as pd

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


def test_run_walk_forward_experiment_returns_rebalance_weights_and_summary():
    weight_grid = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    training_scores = {
        ("2021-01-01", "2021-06-30", (1.0, 0.0, 0.0)): {"return_pct": 5.0, "sharpe": 0.5},
        ("2021-01-01", "2021-06-30", (0.0, 1.0, 0.0)): {"return_pct": 3.0, "sharpe": 0.2},
        ("2021-04-01", "2021-09-30", (1.0, 0.0, 0.0)): {"return_pct": 2.0, "sharpe": 0.1},
        ("2021-04-01", "2021-09-30", (0.0, 1.0, 0.0)): {"return_pct": 4.0, "sharpe": 0.3},
    }
    validation_scores = {
        ("2021-07-01", "2021-09-30", (1.0, 0.0, 0.0)): {"return_pct": 1.5, "sharpe": 0.15},
        ("2021-10-01", "2021-12-31", (0.0, 1.0, 0.0)): {"return_pct": 2.5, "sharpe": 0.25},
    }
    baseline_scores = {
        ("2021-07-01", "2021-09-30"): {"return_pct": 1.0, "sharpe": 0.1},
        ("2021-10-01", "2021-12-31"): {"return_pct": 1.2, "sharpe": 0.12},
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
    )

    assert result["weights"]["rebalance_date"].tolist() == ["2021-07-01", "2021-10-01"]
    assert result["weights"]["weight_mom"].tolist() == [1.0, 0.0]
    assert result["weights"]["weight_vol"].tolist() == [0.0, 1.0]
    assert result["summary"] == {
        "window_count": 2,
        "baseline_return_pct": 2.2,
        "walk_forward_return_pct": 4.0,
    }
