from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.research.registry import append_run_record, create_run_id


DEFAULT_ARTIFACT_DIR = Path(".research_artifacts")
DEFAULT_REGISTRY_FILE = DEFAULT_ARTIFACT_DIR / "registry.jsonl"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_scoring_metadata(
    scores: pd.DataFrame,
    top_n: int,
    weights: dict[str, float],
    lookbacks: dict[str, int],
) -> dict:
    return {
        "top_n": top_n,
        "weights": dict(weights),
        "lookbacks": dict(lookbacks),
        "universe": scores["symbol"].tolist(),
    }


def write_scoring_run(
    base_dir: Path,
    run_name: str,
    metadata: dict,
    scores: pd.DataFrame,
    summary: dict,
) -> dict[str, Path]:
    run_id = create_run_id(run_name)
    run_dir = base_dir / run_name / f"{_timestamp()}-{run_id.split('-', 1)[-1]}"
    run_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = run_dir / "metadata.json"
    scores_path = run_dir / "scores.csv"
    summary_path = run_dir / "summary.json"

    metadata_payload = {"run_id": run_id, "run_name": run_name, **metadata}
    metadata_path.write_text(json.dumps(metadata_payload, indent=2, sort_keys=True), encoding="utf-8")
    scores.to_csv(scores_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    registry_entry = {
        "run_id": run_id,
        "run_name": run_name,
        "run_dir": str(run_dir),
        "metadata": str(metadata_path),
        "scores": str(scores_path),
        "summary": str(summary_path),
        "created_at": _timestamp(),
    }
    append_run_record(base_dir / "registry.jsonl", registry_entry)

    return {
        "run_dir": run_dir,
        "metadata": metadata_path,
        "scores": scores_path,
        "summary": summary_path,
    }
