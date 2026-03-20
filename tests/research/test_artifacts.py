import json
import re
from pathlib import Path

import pandas as pd

from src.paper.bot import calculate_current_signals
from src.research.artifacts import (
    build_scoring_metadata,
    build_screening_metadata,
    build_walk_forward_metadata,
    write_scoring_run,
    write_screening_run,
    write_walk_forward_run,
)
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


def test_build_walk_forward_metadata_includes_universe_fields_when_provided():
    metadata = build_walk_forward_metadata(
        {"start": "2021-01-01", "end": "2021-12-31"},
        universe_name="topix_top_10",
        universe_symbols=["AAA.T", "BBB.T"],
    )

    assert metadata == {
        "start": "2021-01-01",
        "end": "2021-12-31",
        "universe_name": "topix_top_10",
        "universe_symbols": ["AAA.T", "BBB.T"],
    }


def test_write_screening_run_persists_decisions_and_summary(tmp_path: Path):
    decisions = pd.DataFrame(
        [
            {
                "symbol": "AAA.T",
                "eligible": True,
                "reasons": [],
                "history_days": 252,
                "missing_ratio": 0.01,
                "latest_close": 100.0,
                "recent_trading_day_ratio": 1.0,
                "recent_inactive_day_ratio": 0.0,
            },
            {
                "symbol": "BBB.T",
                "eligible": False,
                "reasons": ["low_latest_close", "high_missing_ratio"],
                "history_days": 20,
                "missing_ratio": 0.4,
                "latest_close": 4.5,
                "recent_trading_day_ratio": 0.5,
                "recent_inactive_day_ratio": 0.5,
            },
        ]
    )

    metadata = build_screening_metadata(
        start="2024-01-01",
        end="2024-03-31",
        screen_as_of="2024-03-31",
        universe_name="topix_top_30",
        screening_rules={
            "min_history_days": 252,
            "max_missing_ratio": 0.1,
            "min_latest_close": 5.0,
            "recent_window_days": 20,
            "min_recent_trading_day_ratio": 0.8,
            "max_recent_inactive_day_ratio": 0.2,
        },
    )

    paths = write_screening_run(
        base_dir=tmp_path,
        run_name="universe_screening",
        metadata=metadata,
        decisions=decisions,
        summary={
            "requested_symbol_count": 2,
            "eligible_symbol_count": 1,
            "screened_out_symbol_count": 1,
            "eligibility_ratio": 0.5,
            "screened_out_low_latest_close_count": 1,
            "screened_out_high_missing_ratio_count": 1,
        },
        run_id="universe_screening-20260320T010203Z-deadbeef",
        timestamp="20260320T010203Z",
        created_at="20260320T010203Z",
    )

    assert paths["run_dir"] == tmp_path / "universe_screening" / "20260320T010203Z-20260320T010203Z-deadbeef"
    assert paths["metadata"].exists()
    assert paths["decisions"].exists()
    assert paths["summary"].exists()

    saved_metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    assert saved_metadata["run_name"] == "universe_screening"
    assert saved_metadata["universe_name"] == "topix_top_30"
    assert saved_metadata["screen_as_of"] == "2024-03-31"
    assert saved_metadata["screening_rules"] == {
        "min_history_days": 252,
        "max_missing_ratio": 0.1,
        "min_latest_close": 5.0,
        "recent_window_days": 20,
        "min_recent_trading_day_ratio": 0.8,
        "max_recent_inactive_day_ratio": 0.2,
    }

    saved_decisions = pd.read_csv(paths["decisions"])
    assert saved_decisions["symbol"].tolist() == ["AAA.T", "BBB.T"]
    assert saved_decisions["eligible"].tolist() == [True, False]
    assert saved_decisions.loc[1, "reasons"] == "['low_latest_close', 'high_missing_ratio']"

    saved_summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert saved_summary["requested_symbol_count"] == 2
    assert saved_summary["eligible_symbol_count"] == 1
    assert saved_summary["screened_out_symbol_count"] == 1
    assert saved_summary["eligibility_ratio"] == 0.5

    registry_lines = (tmp_path / "registry.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(registry_lines) == 1
    registry_entry = json.loads(registry_lines[0])
    assert registry_entry["run_id"] == "universe_screening-20260320T010203Z-deadbeef"
    assert registry_entry["run_name"] == "universe_screening"
    assert registry_entry["metadata"] == str(paths["metadata"])
    assert registry_entry["decisions"] == str(paths["decisions"])
    assert registry_entry["summary"] == str(paths["summary"])


def test_write_walk_forward_run_persists_diagnostics_in_summary(tmp_path: Path):
    weights = pd.DataFrame(
        [
            {
                "rebalance_date": "2021-07-01",
                "weight_mom": 1.0,
                "weight_vol": 0.0,
                "weight_rev": 0.0,
                "hit_rate": 0.5,
                "top_contributors": [{"symbol": "AAA.T", "return_pct": 2.0}],
                "bottom_contributors": [{"symbol": "BBB.T", "return_pct": -0.5}],
            }
        ]
    )

    paths = write_walk_forward_run(
        base_dir=tmp_path,
        metadata={"start": "2021-01-01", "end": "2021-12-31"},
        weights=weights,
        summary={
            "window_count": 1,
            "baseline_return_pct": 1.0,
            "walk_forward_return_pct": 1.8,
            "avg_hit_rate": 0.5,
            "avg_loaded_symbol_count": 8.0,
            "avg_skipped_symbol_count": 2.0,
            "avg_coverage_ratio": 0.8,
            "min_loaded_symbol_count": 8,
            "min_coverage_ratio": 0.8,
            "top_contributors": [{"symbol": "AAA.T", "return_pct": 2.0}],
            "bottom_contributors": [{"symbol": "BBB.T", "return_pct": -0.5}],
        },
    )

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    saved_weights = pd.read_csv(paths["weights"])

    assert summary["avg_hit_rate"] == 0.5
    assert summary["avg_loaded_symbol_count"] == 8.0
    assert summary["avg_skipped_symbol_count"] == 2.0
    assert summary["avg_coverage_ratio"] == 0.8
    assert summary["min_loaded_symbol_count"] == 8
    assert summary["min_coverage_ratio"] == 0.8
    assert summary["top_contributors"] == [{"symbol": "AAA.T", "return_pct": 2.0}]
    assert summary["bottom_contributors"] == [{"symbol": "BBB.T", "return_pct": -0.5}]
    assert "hit_rate" in saved_weights.columns


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
