from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.research.artifacts import DEFAULT_REGISTRY_FILE


DEFAULT_APPROVED_PARAMS_FILE = "paper_trade_params.json"


def select_best_walk_forward_run(
    runs: list[dict],
    min_window_count: int = 1,
) -> dict:
    qualified = [
        run
        for run in runs
        if int(run.get("summary", {}).get("window_count", 0)) >= min_window_count
    ]
    if not qualified:
        raise ValueError("No qualified walk-forward runs found")

    qualified.sort(
        key=lambda run: (
            float(run["summary"].get("active_return_pct", float("-inf"))),
            float(run["summary"].get("walk_forward_return_pct", float("-inf"))),
            float(run["summary"].get("baseline_return_pct", float("-inf"))),
        ),
        reverse=True,
    )
    return qualified[0]


def approve_walk_forward_params(
    artifact_dir: Path,
    run_record: dict,
    rebalance_date: str,
) -> dict:
    weights = pd.read_csv(run_record["weights"])
    selected = weights.loc[weights["rebalance_date"] == rebalance_date]
    if selected.empty:
        raise ValueError(f"No walk-forward weights found for rebalance_date={rebalance_date}")

    row = selected.iloc[-1]
    approved = {
        "source_run_id": run_record["run_id"],
        "rebalance_date": rebalance_date,
        "weights": {
            "mom": float(row["weight_mom"]),
            "vol": float(row["weight_vol"]),
            "rev": float(row["weight_rev"]),
        },
    }

    approved_path = Path(artifact_dir) / DEFAULT_APPROVED_PARAMS_FILE
    approved_path.parent.mkdir(parents=True, exist_ok=True)
    approved_path.write_text(json.dumps(approved, indent=2, sort_keys=True), encoding="utf-8")
    return approved


def _load_registry_records(registry_path: Path) -> list[dict]:
    if not registry_path.exists():
        return []

    return [
        json.loads(line)
        for line in registry_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def approve_best_walk_forward_run(
    artifact_dir: Path,
    min_window_count: int = 1,
) -> dict:
    artifact_dir = Path(artifact_dir)
    registry_records = _load_registry_records(artifact_dir / DEFAULT_REGISTRY_FILE.name)

    walk_forward_runs = []
    for record in registry_records:
        if record.get("run_name") != "walk_forward":
            continue
        summary_path = Path(record["summary"])
        if not summary_path.exists():
            continue
        run = dict(record)
        run["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
        walk_forward_runs.append(run)

    best_run = select_best_walk_forward_run(walk_forward_runs, min_window_count=min_window_count)
    weights = pd.read_csv(best_run["weights"])
    latest_rebalance_date = str(weights.iloc[-1]["rebalance_date"])
    return approve_walk_forward_params(
        artifact_dir=artifact_dir,
        run_record=best_run,
        rebalance_date=latest_rebalance_date,
    )


def load_approved_paper_trading_params(artifact_dir: Path) -> dict | None:
    approved_path = Path(artifact_dir) / DEFAULT_APPROVED_PARAMS_FILE
    if not approved_path.exists():
        return None
    return json.loads(approved_path.read_text(encoding="utf-8"))
