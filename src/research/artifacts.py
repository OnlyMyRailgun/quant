from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.research.registry import append_run_record, create_run_id


DEFAULT_ARTIFACT_DIR = Path(".research_artifacts")
DEFAULT_REGISTRY_FILE = DEFAULT_ARTIFACT_DIR / "registry.jsonl"
DEFAULT_NEAR_MISS_COUNT = 3


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_walk_forward_metadata(
    metadata: dict,
    universe_name: str | None = None,
    universe_symbols: list[str] | None = None,
) -> dict:
    payload = dict(metadata)
    if universe_name is not None:
        payload["universe_name"] = universe_name
    if universe_symbols is not None:
        payload["universe_symbols"] = list(universe_symbols)
    return payload


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


def build_screening_metadata(
    start,
    end,
    screen_as_of,
    universe_name: str,
    screening_rules: dict,
) -> dict:
    return {
        "start": start,
        "end": end,
        "screen_as_of": screen_as_of,
        "universe_name": universe_name,
        "screening_rules": dict(screening_rules),
    }


def build_scoring_summary(
    scores: pd.DataFrame,
    top_n: int,
    near_miss_count: int = DEFAULT_NEAR_MISS_COUNT,
    extra_summary: dict | None = None,
) -> dict:
    winners = scores.head(top_n)["symbol"].tolist()
    near_misses = scores.iloc[top_n : top_n + near_miss_count]["symbol"].tolist()

    summary = {
        "top_n": top_n,
        "winner_count": len(winners),
        "winners": winners,
        "near_miss_count": len(near_misses),
        "near_misses": near_misses,
    }
    if extra_summary:
        summary.update(extra_summary)
    return summary


def write_scoring_run(
    base_dir: Path,
    run_name: str,
    metadata: dict,
    scores: pd.DataFrame,
    summary: dict,
    run_id: str | None = None,
    timestamp: str | None = None,
    created_at: str | None = None,
) -> dict[str, Path]:
    run_id = run_id or create_run_id(run_name)
    timestamp = timestamp or _timestamp()
    created_at = created_at or _timestamp()
    run_dir = base_dir / run_name / f"{timestamp}-{run_id.split('-', 1)[-1]}"
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
        "created_at": created_at,
    }
    append_run_record(base_dir / "registry.jsonl", registry_entry)

    return {
        "run_dir": run_dir,
        "metadata": metadata_path,
        "scores": scores_path,
        "summary": summary_path,
    }


def write_walk_forward_run(
    base_dir: Path,
    metadata: dict,
    weights: pd.DataFrame,
    summary: dict,
) -> dict[str, Path]:
    run_name = "walk_forward"
    run_id = create_run_id(run_name)
    run_dir = base_dir / run_name / f"{_timestamp()}-{run_id.split('-', 1)[-1]}"
    run_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = run_dir / "metadata.json"
    weights_path = run_dir / "weights.csv"
    summary_path = run_dir / "summary.json"

    metadata_payload = {"run_id": run_id, "run_name": run_name, **metadata}
    metadata_path.write_text(json.dumps(metadata_payload, indent=2, sort_keys=True), encoding="utf-8")
    weights.to_csv(weights_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    registry_entry = {
        "run_id": run_id,
        "run_name": run_name,
        "run_dir": str(run_dir),
        "metadata": str(metadata_path),
        "weights": str(weights_path),
        "summary": str(summary_path),
        "created_at": _timestamp(),
    }
    append_run_record(base_dir / "registry.jsonl", registry_entry)

    return {
        "run_dir": run_dir,
        "metadata": metadata_path,
        "weights": weights_path,
        "summary": summary_path,
    }


def write_screening_run(
    base_dir: Path,
    run_name: str,
    metadata: dict,
    decisions: pd.DataFrame,
    summary: dict,
    run_id: str | None = None,
    timestamp: str | None = None,
    created_at: str | None = None,
) -> dict[str, Path]:
    run_id = run_id or create_run_id(run_name)
    timestamp = timestamp or _timestamp()
    created_at = created_at or _timestamp()
    run_dir = base_dir / run_name / f"{timestamp}-{run_id.split('-', 1)[-1]}"
    run_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = run_dir / "metadata.json"
    decisions_path = run_dir / "decisions.csv"
    summary_path = run_dir / "summary.json"

    metadata_payload = {"run_id": run_id, "run_name": run_name, **metadata}
    metadata_path.write_text(json.dumps(metadata_payload, indent=2, sort_keys=True), encoding="utf-8")
    decisions.to_csv(decisions_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    registry_entry = {
        "run_id": run_id,
        "run_name": run_name,
        "run_dir": str(run_dir),
        "metadata": str(metadata_path),
        "decisions": str(decisions_path),
        "summary": str(summary_path),
        "created_at": created_at,
    }
    append_run_record(base_dir / "registry.jsonl", registry_entry)

    return {
        "run_dir": run_dir,
        "metadata": metadata_path,
        "decisions": decisions_path,
        "summary": summary_path,
    }
