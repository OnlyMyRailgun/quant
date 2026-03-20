import pandas as pd

from src.research.artifacts import write_scoring_run
from src.research.explain import (
    build_selection_report,
    compare_ranked_symbols,
    load_scoring_run_scores,
)


def make_scores() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAA.T",
                "mom_contribution": 1.2,
                "vol_contribution": 0.2,
                "rev_contribution": 0.3,
                "total_score": 1.7,
                "rank": 1,
                "is_top_n": True,
            },
            {
                "symbol": "BBB.T",
                "mom_contribution": 0.8,
                "vol_contribution": 0.4,
                "rev_contribution": 0.1,
                "total_score": 1.3,
                "rank": 2,
                "is_top_n": True,
            },
            {
                "symbol": "CCC.T",
                "mom_contribution": 0.5,
                "vol_contribution": 0.2,
                "rev_contribution": 0.1,
                "total_score": 0.8,
                "rank": 3,
                "is_top_n": False,
            },
            {
                "symbol": "DDD.T",
                "mom_contribution": -0.1,
                "vol_contribution": 0.3,
                "rev_contribution": 0.2,
                "total_score": 0.4,
                "rank": 4,
                "is_top_n": False,
            },
        ]
    )


def test_build_selection_report_returns_winners_and_near_misses():
    report = build_selection_report(make_scores(), top_n=2, near_miss_count=2)

    assert report == {
        "top_n": 2,
        "winner_count": 2,
        "winners": ["AAA.T", "BBB.T"],
        "near_miss_count": 2,
        "near_misses": ["CCC.T", "DDD.T"],
    }


def test_compare_ranked_symbols_returns_factor_and_total_deltas():
    comparison = compare_ranked_symbols(make_scores(), higher_symbol="AAA.T", lower_symbol="CCC.T")

    assert comparison["higher_symbol"] == "AAA.T"
    assert comparison["lower_symbol"] == "CCC.T"
    assert comparison["total_score_delta"] == 0.9
    assert comparison["contribution_deltas"] == {
        "mom_contribution": 0.7,
        "vol_contribution": 0.0,
        "rev_contribution": 0.2,
    }


def test_load_scoring_run_scores_supports_saved_artifact_comparisons(tmp_path):
    scores = make_scores()
    paths = write_scoring_run(
        base_dir=tmp_path,
        run_name="paper_signal",
        metadata={"top_n": 2},
        scores=scores,
        summary={"top_n": 2, "winner_count": 2},
        run_id="paper_signal-20260320T010203Z-deadbeef",
        timestamp="20260320T010203Z",
        created_at="20260320T010203Z",
    )

    loaded_scores = load_scoring_run_scores(paths["run_dir"])
    report = build_selection_report(loaded_scores, top_n=2, near_miss_count=1)
    comparison = compare_ranked_symbols(loaded_scores, higher_symbol="BBB.T", lower_symbol="DDD.T")

    assert loaded_scores["symbol"].tolist() == scores["symbol"].tolist()
    assert report["winners"] == ["AAA.T", "BBB.T"]
    assert report["near_misses"] == ["CCC.T"]
    assert comparison["total_score_delta"] == 0.9
