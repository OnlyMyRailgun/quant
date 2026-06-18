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


def test_score_universe_defaults_use_broader_portfolio_and_disable_reversion():
    data = {
        f"{idx:03d}.T": make_df([100 + idx] * 100)
        for idx in range(12)
    }

    result = score_universe(data)

    assert int(result["is_top_n"].sum()) == 10
    assert result["rev_contribution"].tolist() == [0.0] * len(result)


def test_score_universe_exposes_weighted_factor_contributions():
    data = {
        "AAA.T": make_df([100] * 70 + list(range(100, 110)) + list(range(150, 130, -1))),
        "BBB.T": make_df([120] * 70 + list(range(120, 110, -1)) + [80] * 20),
        "CCC.T": make_df([100] * 100),
    }

    result = score_universe(data, top_n=2, weight_mom=1.5, weight_vol=0.5, weight_rev=2.0)

    for contribution, weight, zscore in (
        ("mom_contribution", 1.5, "mom_z"),
        ("vol_contribution", 0.5, "vol_z"),
        ("rev_contribution", 2.0, "rev_z"),
    ):
        assert contribution in result.columns
        expected = result[zscore] * weight
        assert result[contribution].round(10).tolist() == expected.round(10).tolist()

    expected_total = (
        result["mom_contribution"] + result["vol_contribution"] + result["rev_contribution"]
    )
    assert result["total_score"].round(10).tolist() == expected_total.round(10).tolist()
    assert result["symbol"].tolist() == ["AAA.T", "CCC.T", "BBB.T"]


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
    expected = score_universe(data, top_n=2, weight_mom=1.0, weight_vol=1.0, weight_rev=0.0).head(2)

    assert winners["symbol"].tolist() == expected["symbol"].tolist()
    assert winners["total_score"].tolist() == expected["total_score"].tolist()


def test_calculate_current_signals_applies_quality_factor_with_12_1_momentum():
    dates = pd.date_range("2021-01-01", periods=300, freq="D")
    flat = pd.DataFrame({"Close": [100.0] * len(dates)}, index=dates)
    data = {
        "LOW_ROE.T": flat.copy(),
        "HIGH_ROE.T": flat.copy(),
    }

    winners = calculate_current_signals(
        data,
        top_n=1,
        weight_mom=0.0,
        weight_vol=0.0,
        weight_rev=0.0,
        weight_qual=1.0,
        momentum_definition="12_1",
        roe_values={"LOW_ROE.T": 0.02, "HIGH_ROE.T": 0.20},
    )

    assert winners["symbol"].tolist() == ["HIGH_ROE.T"]
    assert "qual_contribution" in winners.columns
