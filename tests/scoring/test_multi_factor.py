import json
from pathlib import Path

import pandas as pd

from src.paper.bot import calculate_current_signals
from src.scoring.multi_factor import score_universe


def make_df(closes):
    dates = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"Close": closes}, index=dates)


def test_score_universe_ranks_symbols_by_total_score():
    data = {
        "AAA.T": make_df([100] * 70 + list(range(100, 110)) + list(range(150, 130, -1))),
        "BBB.T": make_df([120] * 70 + list(range(120, 110, -1)) + [80] * 20),
        "CCC.T": make_df([100] * 100),
    }

    result = score_universe(data, top_n=2, weight_mom=1.0, weight_vol=1.0, weight_rev=1.0)

    assert list(result["symbol"]) == ["AAA.T", "CCC.T", "BBB.T"]
    assert list(result["rank"]) == [1, 2, 3]
    assert list(result["is_top_n"]) == [True, True, False]


def test_score_universe_skips_symbols_with_insufficient_history():
    data = {
        "AAA.T": make_df([100] * 100),
        "BBB.T": make_df([100] * 10),
    }

    result = score_universe(data)

    assert list(result["symbol"]) == ["AAA.T"]
    assert result["rank"].tolist() == [1]


def test_score_universe_handles_constant_cross_section_without_nan_scores():
    base = make_df([100] * 100)
    data = {"AAA.T": base.copy(), "BBB.T": base.copy()}

    result = score_universe(data)

    assert result["total_score"].tolist() == [0.0, 0.0]
    assert result[["mom_z", "vol_z", "rev_z"]].isna().sum().sum() == 0


def test_score_universe_skips_symbols_with_zero_or_negative_prices():
    data = {
        "AAA.T": make_df([100] * 100),
        "ZERO.T": make_df([100] * 99 + [0]),
        "NEG.T": make_df([100] * 99 + [-1]),
    }

    result = score_universe(data)

    assert result["symbol"].tolist() == ["AAA.T"]
    assert result["rank"].tolist() == [1]


def test_score_universe_skips_symbols_with_non_finite_factor_outputs():
    explosive = [100] * 79 + [0] + [100] * 20
    data = {
        "AAA.T": make_df([100] * 100),
        "INF.T": make_df(explosive),
    }

    result = score_universe(data)

    assert result["symbol"].tolist() == ["AAA.T"]
    assert result["total_score"].tolist() == [0.0]


def test_score_universe_returns_empty_when_all_symbols_are_invalid():
    data = {
        "ZERO.T": make_df([100] * 99 + [0]),
        "NEG.T": make_df([100] * 99 + [-1]),
    }

    result = score_universe(data)

    assert result.empty


# Task 3 paper-trading integration coverage lives here so the pure scorer
# expectations above stay focused on the shared scoring module itself.
def test_paper_signal_generation_matches_shared_scoring():
    data = {
        "AAA.T": make_df([100] * 70 + list(range(100, 110)) + list(range(150, 130, -1))),
        "BBB.T": make_df([120] * 70 + list(range(120, 110, -1)) + [80] * 20),
        "CCC.T": make_df([100] * 100),
    }

    shared = score_universe(data, top_n=2)
    winners = calculate_current_signals(data, top_n=2)

    assert winners["symbol"].tolist() == shared.head(2)["symbol"].tolist()
    assert winners["total_score"].tolist() == shared.head(2)["total_score"].tolist()


def test_calculate_current_signals_preserves_legacy_factor_aliases():
    data = {
        "AAA.T": make_df([100] * 70 + list(range(100, 110)) + list(range(150, 130, -1))),
        "BBB.T": make_df([120] * 70 + list(range(120, 110, -1)) + [80] * 20),
        "CCC.T": make_df([100] * 100),
    }

    winners = calculate_current_signals(data, top_n=2)

    assert winners["is_top_n"].tolist() == [True, True]
    for legacy, raw in (("mom", "mom_raw"), ("vol", "vol_raw"), ("rev", "rev_raw")):
        assert legacy in winners.columns
        assert raw in winners.columns
        assert winners[legacy].tolist() == winners[raw].tolist()


def test_calculate_current_signals_uses_approved_params_when_available(tmp_path: Path):
    data = {
        "AAA.T": make_df([100] * 70 + list(range(100, 110)) + list(range(150, 130, -1))),
        "BBB.T": make_df([120] * 70 + list(range(120, 110, -1)) + [80] * 20),
        "CCC.T": make_df([100] * 100),
    }

    (tmp_path / "paper_trade_params.json").write_text(
        json.dumps(
            {
                "source_run_id": "wf-2",
                "rebalance_date": "2022-07-01",
                "weights": {"mom": 0.0, "vol": 1.0, "rev": 0.0},
            }
        ),
        encoding="utf-8",
    )

    winners = calculate_current_signals(data, top_n=2, artifact_dir=tmp_path)
    expected = score_universe(data, top_n=2, weight_mom=0.0, weight_vol=1.0, weight_rev=0.0).head(2)

    assert winners["symbol"].tolist() == expected["symbol"].tolist()
    assert winners["total_score"].tolist() == expected["total_score"].tolist()


def test_calculate_current_signals_falls_back_when_no_approved_params_exist(tmp_path: Path):
    data = {
        "AAA.T": make_df([100] * 70 + list(range(100, 110)) + list(range(150, 130, -1))),
        "BBB.T": make_df([120] * 70 + list(range(120, 110, -1)) + [80] * 20),
        "CCC.T": make_df([100] * 100),
    }

    winners = calculate_current_signals(data, top_n=2, artifact_dir=tmp_path)
    expected = score_universe(data, top_n=2, weight_mom=1.0, weight_vol=1.0, weight_rev=1.0).head(2)

    assert winners["symbol"].tolist() == expected["symbol"].tolist()
    assert winners["total_score"].tolist() == expected["total_score"].tolist()
