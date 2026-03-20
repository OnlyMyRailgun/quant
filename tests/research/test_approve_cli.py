import json
from pathlib import Path

import pandas as pd

from src.research import approve


def _write_walk_forward_run(
    tmp_path: Path,
    run_name: str,
    run_id: str,
    rebalance_date: str,
    summary: dict,
) -> None:
    run_dir = tmp_path / "walk_forward" / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    weights_path = run_dir / "weights.csv"
    summary_path = run_dir / "summary.json"

    pd.DataFrame(
        [
            {
                "rebalance_date": rebalance_date,
                "weight_mom": 0.5,
                "weight_vol": 1.0,
                "weight_rev": 0.5,
            }
        ]
    ).to_csv(weights_path, index=False)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    registry_path = tmp_path / "registry.jsonl"
    existing = registry_path.read_text(encoding="utf-8") if registry_path.exists() else ""
    registry_path.write_text(
        existing
        + json.dumps(
            {
                "run_id": run_id,
                "run_name": "walk_forward",
                "run_dir": str(run_dir),
                "weights": str(weights_path),
                "summary": str(summary_path),
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_approve_cli_list_shows_candidate_runs(tmp_path: Path, capsys):
    _write_walk_forward_run(
        tmp_path,
        run_name="run-a",
        run_id="wf-a",
        rebalance_date="2022-01-01",
        summary={
            "window_count": 4,
            "baseline_return_pct": 1.0,
            "walk_forward_return_pct": 2.0,
            "active_return_pct": 1.0,
        },
    )
    _write_walk_forward_run(
        tmp_path,
        run_name="run-b",
        run_id="wf-b",
        rebalance_date="2022-07-01",
        summary={
            "window_count": 5,
            "baseline_return_pct": 1.5,
            "walk_forward_return_pct": 4.0,
            "active_return_pct": 2.5,
        },
    )

    exit_code = approve.main(["list", "--artifact-dir", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "wf-a" in output
    assert "wf-b" in output
    assert "active_return_pct" in output
    assert "walk_forward_return_pct" in output
    assert "latest_rebalance_date" in output
    assert "weights_path" in output
    assert "2022-01-01" in output
    assert "2022-07-01" in output
    assert str(tmp_path / "walk_forward" / "run-b" / "weights.csv") in output


def test_approve_cli_approve_writes_selected_run_and_reports_path(tmp_path: Path, capsys):
    _write_walk_forward_run(
        tmp_path,
        run_name="run-b",
        run_id="wf-b",
        rebalance_date="2022-07-01",
        summary={
            "window_count": 5,
            "baseline_return_pct": 1.5,
            "walk_forward_return_pct": 4.0,
            "active_return_pct": 2.5,
        },
    )

    exit_code = approve.main(
        [
            "approve",
            "--artifact-dir",
            str(tmp_path),
            "--run-id",
            "wf-b",
            "--rebalance-date",
            "2022-07-01",
        ]
    )

    output = capsys.readouterr().out
    approved_path = tmp_path / "paper_trade_params.json"

    assert exit_code == 0
    assert "Approved run wf-b" in output
    assert str(approved_path) in output

    approved_payload = json.loads(approved_path.read_text(encoding="utf-8"))
    assert approved_payload["source_run_id"] == "wf-b"
    assert approved_payload["rebalance_date"] == "2022-07-01"
    assert approved_payload["weights"] == {"mom": 0.5, "vol": 1.0, "rev": 0.5}


def test_approve_cli_approve_defaults_to_latest_rebalance_date(tmp_path: Path, capsys):
    run_dir = tmp_path / "walk_forward" / "run-b"
    run_dir.mkdir(parents=True, exist_ok=True)
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
                "window_count": 5,
                "baseline_return_pct": 1.5,
                "walk_forward_return_pct": 4.0,
                "active_return_pct": 2.5,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "registry.jsonl").write_text(
        json.dumps(
            {
                "run_id": "wf-b",
                "run_name": "walk_forward",
                "run_dir": str(run_dir),
                "weights": str(weights_path),
                "summary": str(summary_path),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = approve.main(
        [
            "approve",
            "--artifact-dir",
            str(tmp_path),
            "--run-id",
            "wf-b",
        ]
    )

    output = capsys.readouterr().out
    approved_payload = json.loads((tmp_path / "paper_trade_params.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "2022-07-01" in output
    assert approved_payload["rebalance_date"] == "2022-07-01"


def test_approve_cli_approve_missing_run_id_reports_readable_error(tmp_path: Path, capsys):
    exit_code = approve.main(
        [
            "approve",
            "--artifact-dir",
            str(tmp_path),
            "--run-id",
            "wf-missing",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Approval workflow failed:" in output
    assert "wf-missing" in output
