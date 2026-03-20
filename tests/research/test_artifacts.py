import json
import re
from pathlib import Path

import pandas as pd

from src.paper.bot import calculate_current_signals
from src.research.artifacts import build_scoring_metadata, write_scoring_run
from src.research.registry import append_run_record, create_run_id
from src.scoring.multi_factor import score_universe


def make_df(closes):
    dates = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"Close": closes}, index=dates)


def test_write_scoring_run_creates_metadata_scores_and_summary(tmp_path: Path):
    scores = pd.DataFrame(
        [
            {"symbol": "AAA.T", "total_score": 1.23, "rank": 1},
        ]
    )

    paths = write_scoring_run(
        base_dir=tmp_path,
        run_name="paper_signal",
        metadata={"weight_mom": 1.0},
        scores=scores,
        summary={"winner_count": 1},
    )

    assert paths["run_dir"].exists()
    assert paths["metadata"].exists()
    assert paths["scores"].exists()
    assert paths["summary"].exists()

    metadata = json.loads(paths["metadata"].read_text())
    assert metadata["run_name"] == "paper_signal"
    assert metadata["weight_mom"] == 1.0

    saved_scores = pd.read_csv(paths["scores"])
    assert saved_scores["symbol"].tolist() == ["AAA.T"]

    summary = json.loads(paths["summary"].read_text())
    assert summary == {"winner_count": 1}


def test_write_scoring_run_supports_deterministic_run_paths_for_regression_tests(tmp_path: Path):
    scores = pd.DataFrame(
        [
            {"symbol": "AAA.T", "total_score": 1.23, "rank": 1},
        ]
    )

    paths = write_scoring_run(
        base_dir=tmp_path,
        run_name="paper_signal",
        metadata={"weight_mom": 1.0},
        scores=scores,
        summary={"winner_count": 1},
        run_id="paper_signal-20260320T010203Z-deadbeef",
        timestamp="20260320T010203Z",
        created_at="20260320T010203Z",
    )

    assert paths["run_dir"] == tmp_path / "paper_signal" / "20260320T010203Z-20260320T010203Z-deadbeef"

    registry_lines = (tmp_path / "registry.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(registry_lines) == 1
    registry_entry = json.loads(registry_lines[0])
    assert registry_entry["run_id"] == "paper_signal-20260320T010203Z-deadbeef"
    assert registry_entry["created_at"] == "20260320T010203Z"
    assert registry_entry["run_dir"] == str(paths["run_dir"])


def test_build_scoring_metadata_derives_standard_payload_from_scores():
    scores = pd.DataFrame(
        [
            {"symbol": "AAA.T", "total_score": 1.23, "rank": 1},
            {"symbol": "BBB.T", "total_score": 0.45, "rank": 2},
        ]
    )

    metadata = build_scoring_metadata(
        scores=scores,
        top_n=2,
        weights={"mom": 1.5, "vol": 0.5, "rev": 2.0},
        lookbacks={"mom": 90, "vol": 20, "rev": 20},
    )

    assert metadata == {
        "top_n": 2,
        "weights": {"mom": 1.5, "vol": 0.5, "rev": 2.0},
        "lookbacks": {"mom": 90, "vol": 20, "rev": 20},
        "universe": ["AAA.T", "BBB.T"],
    }


def test_append_run_record_is_append_only_jsonl(tmp_path: Path):
    registry_path = tmp_path / "registry.jsonl"

    append_run_record(
        registry_path,
        {"run_id": "run-123", "kind": "paper_signal"},
    )
    first_snapshot = registry_path.read_text(encoding="utf-8")

    lines = registry_path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["run_id"] == "run-123"

    append_run_record(
        registry_path,
        {"run_id": "run-456", "kind": "paper_signal"},
    )

    assert registry_path.read_text(encoding="utf-8").startswith(first_snapshot)

    lines = registry_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["run_id"] == "run-123"
    assert json.loads(lines[1])["run_id"] == "run-456"


def test_create_run_id_is_unique_and_timestamped():
    run_id_1 = create_run_id("paper_signal")
    run_id_2 = create_run_id("paper_signal")

    pattern = re.compile(r"^paper_signal-\d{8}T\d{6}Z-[0-9a-f]{8}$")

    assert run_id_1 != run_id_2
    assert pattern.match(run_id_1)
    assert pattern.match(run_id_2)


def test_paper_signal_run_can_write_artifacts(tmp_path: Path):
    data = {
        "AAA.T": make_df([100] * 70 + list(range(100, 110)) + list(range(150, 130, -1))),
        "BBB.T": make_df([120] * 70 + list(range(120, 110, -1)) + [80] * 20),
        "CCC.T": make_df([100] * 100),
        "DDD.T": make_df([90] * 70 + list(range(90, 96)) + [95] * 24),
        "EEE.T": make_df([130] * 70 + list(range(130, 125, -1)) + [124] * 25),
    }
    expected_ranked = score_universe(
        data,
        top_n=2,
        weight_mom=1.5,
        weight_vol=0.5,
        weight_rev=2.0,
    )

    winners = calculate_current_signals(
        data,
        top_n=2,
        weight_mom=1.5,
        weight_vol=0.5,
        weight_rev=2.0,
        artifact_dir=tmp_path,
    )

    assert winners["symbol"].tolist() == ["AAA.T", "DDD.T"]

    run_root = tmp_path / "paper_signal"
    run_dirs = [path for path in run_root.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1

    run_dir = run_dirs[0]
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    scores = pd.read_csv(run_dir / "scores.csv")
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    assert metadata["top_n"] == 2
    assert metadata["weights"] == {"mom": 1.5, "vol": 0.5, "rev": 2.0}
    assert metadata["lookbacks"] == {"mom": 90, "vol": 20, "rev": 20}
    assert metadata["universe"] == scores["symbol"].tolist()
    assert scores["symbol"].tolist() == expected_ranked["symbol"].tolist()
    for column in ("mom_contribution", "vol_contribution", "rev_contribution"):
        assert column in scores.columns
    assert summary == {
        "near_miss_count": 3,
        "near_misses": expected_ranked.iloc[2:5]["symbol"].tolist(),
        "top_n": 2,
        "winner_count": 2,
        "winners": expected_ranked.head(2)["symbol"].tolist(),
    }

    registry_lines = (tmp_path / "registry.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(registry_lines) == 1
    registry_entry = json.loads(registry_lines[0])
    assert registry_entry["run_name"] == "paper_signal"
    assert Path(registry_entry["run_dir"]) == run_dir
