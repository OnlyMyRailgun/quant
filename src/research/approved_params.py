from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.research.artifacts import DEFAULT_REGISTRY_FILE


DEFAULT_APPROVED_PARAMS_FILE = "paper_trade_params.json"


def _validate_weights_table(weights: pd.DataFrame, weights_path: Path) -> None:
    if weights.empty:
        raise ValueError(f"{weights_path.name} is empty")

    required_columns = {"rebalance_date", "weight_mom", "weight_vol", "weight_rev"}
    missing_columns = sorted(required_columns - set(weights.columns))
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"{weights_path.name} is missing required columns: {missing}")


def _load_walk_forward_weights(weights_path: Path) -> pd.DataFrame:
    weights = pd.read_csv(weights_path)
    _validate_weights_table(weights, weights_path)
    return weights


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
    weights_path = Path(run_record["weights"])
    weights = _load_walk_forward_weights(weights_path)
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


def load_walk_forward_run_candidates(artifact_dir: Path) -> list[dict]:
    artifact_dir = Path(artifact_dir)
    registry_records = _load_registry_records(artifact_dir / DEFAULT_REGISTRY_FILE.name)

    candidates = []
    for record in registry_records:
        if record.get("run_name") != "walk_forward":
            continue

        summary_path = Path(record["summary"])
        if not summary_path.exists():
            continue

        weights_path = Path(record["weights"])
        weights = _load_walk_forward_weights(weights_path)

        run = dict(record)
        run["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
        run["latest_rebalance_date"] = str(weights.iloc[-1]["rebalance_date"])
        run["weights_path"] = str(weights_path)
        candidates.append(run)

    candidates.sort(key=lambda run: str(run.get("run_id", "")))
    return candidates


def approve_best_walk_forward_run(
    artifact_dir: Path,
    min_window_count: int = 1,
) -> dict:
    artifact_dir = Path(artifact_dir)
    walk_forward_runs = load_walk_forward_run_candidates(artifact_dir)

    best_run = select_best_walk_forward_run(walk_forward_runs, min_window_count=min_window_count)
    return approve_walk_forward_params(
        artifact_dir=artifact_dir,
        run_record=best_run,
        rebalance_date=best_run["latest_rebalance_date"],
    )


def load_approved_paper_trading_params(artifact_dir: Path) -> dict | None:
    approved_path = Path(artifact_dir) / DEFAULT_APPROVED_PARAMS_FILE
    if not approved_path.exists():
        return None
    try:
        approved = json.loads(approved_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{approved_path.name} must contain valid JSON") from exc

    if not isinstance(approved, dict):
        raise ValueError(f"{approved_path.name} must contain a JSON object")

    weights = approved.get("weights")
    if not isinstance(weights, dict):
        raise ValueError(f"{approved_path.name} must contain a 'weights' object")

    missing_keys = [key for key in ("mom", "vol", "rev") if key not in weights]
    if missing_keys:
        missing = ", ".join(missing_keys)
        raise ValueError(f"{approved_path.name} weights are missing required keys: {missing}")

    return approved


def resolve_approved_weight_values(
    artifact_dir: Path | None,
    weight_mom: float | None,
    weight_vol: float | None,
    weight_rev: float | None,
    fallback: tuple[float, float, float],
) -> dict[str, float]:
    approved = None
    if artifact_dir is not None:
        approved = load_approved_paper_trading_params(Path(artifact_dir))

    approved_weights = approved["weights"] if approved is not None else {}
    return {
        "mom": float(approved_weights.get("mom", fallback[0])) if weight_mom is None else weight_mom,
        "vol": float(approved_weights.get("vol", fallback[1])) if weight_vol is None else weight_vol,
        "rev": float(approved_weights.get("rev", fallback[2])) if weight_rev is None else weight_rev,
    }
