import json
from pathlib import Path

import pandas as pd

from src.research.approved_params import (
    approve_walk_forward_params,
    approve_best_walk_forward_run,
    load_approved_paper_trading_params,
    select_best_walk_forward_run,
)


def test_select_best_walk_forward_run_chooses_highest_qualified_summary():
    runs = [
        {
            "run_id": "wf-1",
            "summary": {
                "window_count": 4,
                "baseline_return_pct": 2.0,
                "walk_forward_return_pct": 3.0,
                "active_return_pct": 1.0,
            },
        },
        {
            "run_id": "wf-2",
            "summary": {
                "window_count": 4,
                "baseline_return_pct": 1.5,
                "walk_forward_return_pct": 5.0,
                "active_return_pct": 3.5,
            },
        },
        {
            "run_id": "wf-3",
            "summary": {
                "window_count": 2,
                "baseline_return_pct": 0.5,
                "walk_forward_return_pct": 8.0,
                "active_return_pct": 7.5,
            },
        },
    ]

    best = select_best_walk_forward_run(runs, min_window_count=3)

    assert best["run_id"] == "wf-2"


def test_approve_walk_forward_params_writes_stable_paper_trading_file(tmp_path: Path):
    run_dir = tmp_path / "walk_forward" / "20260320T010101Z-wf"
    run_dir.mkdir(parents=True)
    weights_path = run_dir / "weights.csv"
    summary_path = run_dir / "summary.json"
    metadata_path = run_dir / "metadata.json"

    pd.DataFrame(
        [
            {
                "rebalance_date": "2022-01-01",
                "weight_mom": 1.0,
                "weight_vol": 0.0,
                "weight_rev": 0.0,
            },
            {
                "rebalance_date": "2022-07-01",
                "weight_mom": 0.5,
                "weight_vol": 1.0,
                "weight_rev": 0.5,
            },
        ]
    ).to_csv(weights_path, index=False)
    summary_path.write_text(
        json.dumps(
            {
                "window_count": 4,
                "baseline_return_pct": 1.5,
                "walk_forward_return_pct": 5.0,
                "active_return_pct": 3.5,
            }
        ),
        encoding="utf-8",
    )
    metadata_path.write_text(json.dumps({"run_id": "wf-2"}), encoding="utf-8")

    approved = approve_walk_forward_params(
        artifact_dir=tmp_path,
        run_record={
            "run_id": "wf-2",
            "run_dir": str(run_dir),
            "metadata": str(metadata_path),
            "weights": str(weights_path),
            "summary": str(summary_path),
        },
        rebalance_date="2022-07-01",
    )

    approved_path = tmp_path / "paper_trade_params.json"
    assert approved_path.exists()
    assert approved["weights"] == {"mom": 0.5, "vol": 1.0, "rev": 0.5}

    loaded = load_approved_paper_trading_params(tmp_path)
    assert loaded["source_run_id"] == "wf-2"
    assert loaded["rebalance_date"] == "2022-07-01"
    assert loaded["weights"] == {"mom": 0.5, "vol": 1.0, "rev": 0.5}


def test_approve_best_walk_forward_run_selects_from_registry_and_writes_file(tmp_path: Path):
    run_dir_a = tmp_path / "walk_forward" / "run-a"
    run_dir_b = tmp_path / "walk_forward" / "run-b"
    run_dir_a.mkdir(parents=True)
    run_dir_b.mkdir(parents=True)

    weights_a = run_dir_a / "weights.csv"
    weights_b = run_dir_b / "weights.csv"
    pd.DataFrame(
        [{"rebalance_date": "2022-01-01", "weight_mom": 1.0, "weight_vol": 0.0, "weight_rev": 0.0}]
    ).to_csv(weights_a, index=False)
    pd.DataFrame(
        [{"rebalance_date": "2022-07-01", "weight_mom": 0.0, "weight_vol": 1.0, "weight_rev": 0.5}]
    ).to_csv(weights_b, index=False)

    summary_a = run_dir_a / "summary.json"
    summary_b = run_dir_b / "summary.json"
    summary_a.write_text(
        json.dumps({"window_count": 4, "baseline_return_pct": 1.0, "walk_forward_return_pct": 2.0, "active_return_pct": 1.0}),
        encoding="utf-8",
    )
    summary_b.write_text(
        json.dumps({"window_count": 4, "baseline_return_pct": 1.0, "walk_forward_return_pct": 4.0, "active_return_pct": 3.0}),
        encoding="utf-8",
    )

    registry_path = tmp_path / "registry.jsonl"
    registry_path.write_text(
        "\n".join(
            [
                json.dumps({"run_id": "wf-a", "run_name": "walk_forward", "run_dir": str(run_dir_a), "weights": str(weights_a), "summary": str(summary_a)}),
                json.dumps({"run_id": "wf-b", "run_name": "walk_forward", "run_dir": str(run_dir_b), "weights": str(weights_b), "summary": str(summary_b)}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    approved = approve_best_walk_forward_run(tmp_path, min_window_count=3)

    assert approved["source_run_id"] == "wf-b"
    assert approved["weights"] == {"mom": 0.0, "vol": 1.0, "rev": 0.5}
