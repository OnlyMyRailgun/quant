from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.research.artifacts import build_scoring_summary


def _rounded(value: float) -> float:
    return round(float(value), 10)


def build_selection_report(
    scores: pd.DataFrame,
    top_n: int,
    near_miss_count: int = 3,
) -> dict:
    return build_scoring_summary(
        scores=scores,
        top_n=top_n,
        near_miss_count=near_miss_count,
    )


def compare_ranked_symbols(
    scores: pd.DataFrame,
    higher_symbol: str,
    lower_symbol: str,
) -> dict:
    indexed = scores.set_index("symbol", drop=False)
    higher = indexed.loc[higher_symbol]
    lower = indexed.loc[lower_symbol]

    contribution_columns = [
        "mom_contribution",
        "vol_contribution",
        "rev_contribution",
    ]
    contribution_deltas = {
        column: _rounded(higher[column] - lower[column])
        for column in contribution_columns
    }

    return {
        "higher_symbol": higher_symbol,
        "lower_symbol": lower_symbol,
        "higher_rank": int(higher["rank"]),
        "lower_rank": int(lower["rank"]),
        "higher_total_score": _rounded(higher["total_score"]),
        "lower_total_score": _rounded(lower["total_score"]),
        "total_score_delta": _rounded(higher["total_score"] - lower["total_score"]),
        "contribution_deltas": contribution_deltas,
    }


def load_scoring_run_scores(run_dir: Path) -> pd.DataFrame:
    return pd.read_csv(Path(run_dir) / "scores.csv")
