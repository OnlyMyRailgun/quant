import json
from pathlib import Path

import pandas as pd

from src.research.approved_params import (
    approve_walk_forward_params,
    approve_best_walk_forward_run,
    load_walk_forward_run_candidates,
    load_approved_paper_trading_params,
    resolve_approved_weight_values,
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


def test_load_walk_forward_run_candidates_returns_summary_latest_rebalance_date_and_weights_path(tmp_path: Path):
    run_dir = tmp_path / "walk_forward" / "run-a"
    run_dir.mkdir(parents=True)
    weights_path = run_dir / "weights.csv"
    summary_path = run_dir / "summary.json"

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
    (tmp_path / "registry.jsonl").write_text(
        json.dumps(
            {
                "run_id": "wf-a",
                "run_name": "walk_forward",
                "run_dir": str(run_dir),
                "weights": str(weights_path),
                "summary": str(summary_path),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    candidates = load_walk_forward_run_candidates(tmp_path)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["run_id"] == "wf-a"
    assert candidate["summary"]["active_return_pct"] == 3.5
    assert candidate["latest_rebalance_date"] == "2022-07-01"
    assert candidate["weights_path"] == str(weights_path)


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


def test_approve_walk_forward_params_preserves_optional_value_and_quality_weights(tmp_path: Path):
    run_dir = tmp_path / "walk_forward" / "20260320T010101Z-wf"
    run_dir.mkdir(parents=True)
    weights_path = run_dir / "weights.csv"

    pd.DataFrame(
        [
            {
                "rebalance_date": "2022-07-01",
                "weight_mom": 0.5,
                "weight_vol": 1.0,
                "weight_rev": 0.0,
                "weight_val": 0.5,
                "weight_qual": 1.0,
            },
        ]
    ).to_csv(weights_path, index=False)

    approved = approve_walk_forward_params(
        artifact_dir=tmp_path,
        run_record={
            "run_id": "wf-optional",
            "weights": str(weights_path),
        },
        rebalance_date="2022-07-01",
    )

    assert approved["weights"] == {
        "mom": 0.5,
        "vol": 1.0,
        "rev": 0.0,
        "val": 0.5,
        "qual": 1.0,
    }
    assert load_approved_paper_trading_params(tmp_path)["weights"] == approved["weights"]


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


def test_resolve_approved_weight_values_merges_explicit_overrides_with_approved_values(tmp_path: Path):
    approved_path = tmp_path / "paper_trade_params.json"
    approved_path.write_text(
        json.dumps(
            {
                "source_run_id": "wf-b",
                "rebalance_date": "2022-07-01",
                "weights": {"mom": 0.0, "vol": 1.0, "rev": 0.5},
            }
        ),
        encoding="utf-8",
    )

    resolved = resolve_approved_weight_values(
        artifact_dir=tmp_path,
        weight_mom=1.0,
        weight_vol=None,
        weight_rev=None,
        fallback=(1.0, 1.0, 1.0),
    )

    assert resolved == {"mom": 1.0, "vol": 1.0, "rev": 0.5}


def test_resolve_approved_weight_values_preserves_optional_value_and_quality(tmp_path: Path):
    approved_path = tmp_path / "paper_trade_params.json"
    approved_path.write_text(
        json.dumps(
            {
                "source_run_id": "wf-optional",
                "rebalance_date": "2022-07-01",
                "weights": {
                    "mom": 0.25,
                    "vol": 0.5,
                    "rev": 0.75,
                    "val": 1.0,
                    "qual": 1.25,
                },
            }
        ),
        encoding="utf-8",
    )

    resolved = resolve_approved_weight_values(
        artifact_dir=tmp_path,
        weight_mom=None,
        weight_vol=None,
        weight_rev=None,
        weight_val=None,
        weight_qual=None,
        fallback=(1.0, 1.0, 1.0, 0.0, 0.0),
    )

    assert resolved == {
        "mom": 0.25,
        "vol": 0.5,
        "rev": 0.75,
        "val": 1.0,
        "qual": 1.25,
    }


def test_offline_walk_forward_approval_workflow_round_trips_artifacts(tmp_path: Path):
    run_dir_a = tmp_path / "walk_forward" / "run-a"
    run_dir_b = tmp_path / "walk_forward" / "run-b"
    run_dir_a.mkdir(parents=True)
    run_dir_b.mkdir(parents=True)

    weights_a = run_dir_a / "weights.csv"
    weights_b = run_dir_b / "weights.csv"
    summary_a = run_dir_a / "summary.json"
    summary_b = run_dir_b / "summary.json"
    metadata_a = run_dir_a / "metadata.json"
    metadata_b = run_dir_b / "metadata.json"

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
                "weight_mom": 0.0,
                "weight_vol": 1.0,
                "weight_rev": 0.5,
            },
        ]
    ).to_csv(weights_a, index=False)
    pd.DataFrame(
        [
            {
                "rebalance_date": "2022-01-01",
                "weight_mom": 0.5,
                "weight_vol": 1.0,
                "weight_rev": 0.5,
            },
            {
                "rebalance_date": "2022-07-01",
                "weight_mom": 0.0,
                "weight_vol": 1.0,
                "weight_rev": 0.5,
            },
        ]
    ).to_csv(weights_b, index=False)

    summary_a.write_text(
        json.dumps(
            {
                "window_count": 4,
                "baseline_return_pct": 1.0,
                "walk_forward_return_pct": 2.0,
                "active_return_pct": 1.0,
            }
        ),
        encoding="utf-8",
    )
    summary_b.write_text(
        json.dumps(
            {
                "window_count": 4,
                "baseline_return_pct": 1.5,
                "walk_forward_return_pct": 4.0,
                "active_return_pct": 2.5,
            }
        ),
        encoding="utf-8",
    )
    metadata_a.write_text(json.dumps({"run_id": "wf-a"}), encoding="utf-8")
    metadata_b.write_text(json.dumps({"run_id": "wf-b"}), encoding="utf-8")

    (tmp_path / "registry.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "run_id": "wf-a",
                        "run_name": "walk_forward",
                        "run_dir": str(run_dir_a),
                        "metadata": str(metadata_a),
                        "weights": str(weights_a),
                        "summary": str(summary_a),
                    }
                ),
                json.dumps(
                    {
                        "run_id": "wf-b",
                        "run_name": "walk_forward",
                        "run_dir": str(run_dir_b),
                        "metadata": str(metadata_b),
                        "weights": str(weights_b),
                        "summary": str(summary_b),
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    candidates = load_walk_forward_run_candidates(tmp_path)
    assert [candidate["run_id"] for candidate in candidates] == ["wf-a", "wf-b"]
    assert [candidate["latest_rebalance_date"] for candidate in candidates] == ["2022-07-01", "2022-07-01"]

    approved = approve_best_walk_forward_run(tmp_path, min_window_count=3)
    assert approved["source_run_id"] == "wf-b"
    assert approved["rebalance_date"] == "2022-07-01"
    assert (tmp_path / "paper_trade_params.json").exists()

    loaded = load_approved_paper_trading_params(tmp_path)
    assert loaded["source_run_id"] == "wf-b"
    assert loaded["rebalance_date"] == "2022-07-01"

    resolved = resolve_approved_weight_values(
        artifact_dir=tmp_path,
        weight_mom=None,
        weight_vol=None,
        weight_rev=None,
        fallback=(1.0, 1.0, 1.0),
    )
    assert resolved == {"mom": 0.0, "vol": 1.0, "rev": 0.5}


def test_load_approved_paper_trading_params_raises_clear_error_for_invalid_json(tmp_path: Path):
    approved_path = tmp_path / "paper_trade_params.json"
    approved_path.write_text("{bad json", encoding="utf-8")

    try:
        load_approved_paper_trading_params(tmp_path)
    except ValueError as exc:
        assert "paper_trade_params.json" in str(exc)
        assert "valid JSON" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid approved params JSON")


def test_load_approved_paper_trading_params_raises_clear_error_when_weights_are_missing(tmp_path: Path):
    approved_path = tmp_path / "paper_trade_params.json"
    approved_path.write_text(json.dumps({"source_run_id": "wf-b"}), encoding="utf-8")

    try:
        load_approved_paper_trading_params(tmp_path)
    except ValueError as exc:
        assert "weights" in str(exc)
        assert "paper_trade_params.json" in str(exc)
    else:
        raise AssertionError("Expected ValueError when approved params weights are missing")


def test_approve_walk_forward_params_raises_clear_error_when_weights_file_is_empty(tmp_path: Path):
    run_dir = tmp_path / "walk_forward" / "run-a"
    run_dir.mkdir(parents=True)
    weights_path = run_dir / "weights.csv"
    weights_path.write_text("rebalance_date,weight_mom,weight_vol,weight_rev\n", encoding="utf-8")

    try:
        approve_walk_forward_params(
            artifact_dir=tmp_path,
            run_record={
                "run_id": "wf-a",
                "weights": str(weights_path),
            },
            rebalance_date="2022-07-01",
        )
    except ValueError as exc:
        assert "weights.csv" in str(exc)
        assert "empty" in str(exc)
    else:
        raise AssertionError("Expected ValueError for empty weights.csv")


def test_approve_walk_forward_params_raises_clear_error_when_required_columns_are_missing(tmp_path: Path):
    run_dir = tmp_path / "walk_forward" / "run-a"
    run_dir.mkdir(parents=True)
    weights_path = run_dir / "weights.csv"
    pd.DataFrame(
        [
            {
                "rebalance_date": "2022-07-01",
                "weight_mom": 0.5,
                "weight_vol": 1.0,
            }
        ]
    ).to_csv(weights_path, index=False)

    try:
        approve_walk_forward_params(
            artifact_dir=tmp_path,
            run_record={
                "run_id": "wf-a",
                "weights": str(weights_path),
            },
            rebalance_date="2022-07-01",
        )
    except ValueError as exc:
        assert "weight_rev" in str(exc)
        assert "weights.csv" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing weight columns")
