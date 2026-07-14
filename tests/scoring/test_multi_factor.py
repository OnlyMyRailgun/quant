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


def test_missing_optional_value_factor_is_neutral_not_nan_poisoning():
    """A stock missing its P/B input must be scored neutrally (val_z=0) on that
    factor, not dropped from top_n via a NaN total_score."""
    strong_mom = make_df([100] * 70 + list(range(100, 130)))
    mid_mom = make_df([110] * 70 + list(range(110, 125)) + list(range(125, 110, -1)))
    weak_mom = make_df([130] * 70 + list(range(130, 100, -1)))
    # STRONG has the best momentum but a missing book value. MID/WEAK have valid
    # book values, so the val z-score population has std > 0 (not the zero-std
    # fallback), meaning STRONG's own val_z is a genuine NaN unless we neutralize.
    data = {"STRONG.T": strong_mom, "MID.T": mid_mom, "WEAK.T": weak_mom}

    result = score_universe(
        data,
        top_n=1,
        weight_mom=1.0,
        weight_vol=0.0,
        weight_rev=0.0,
        weight_val=0.5,
        book_values={"STRONG.T": None, "MID.T": 2.0, "WEAK.T": 5.0},
    )

    by_symbol = result.set_index("symbol")
    # STRONG.T is missing book value; it must not be NaN-poisoned out of top_n.
    assert by_symbol.loc["STRONG.T", "total_score"] == by_symbol.loc["STRONG.T", "total_score"]  # not NaN
    assert by_symbol.loc["STRONG.T", "val_z"] == 0.0
    assert by_symbol.loc["STRONG.T", "is_top_n"]


def test_industry_neutral_single_stock_industry_uses_cross_sectional_zscore():
    """Single-stock industries must fall back to the cross-sectional z-score
    (as the docstring promises), not be zeroed out."""
    strong_mom = make_df([100] * 70 + list(range(100, 130)))
    weak_mom = make_df([130] * 70 + list(range(130, 100, -1)))
    data = {"STRONG.T": strong_mom, "WEAK.T": weak_mom}

    result = score_universe(
        data,
        top_n=1,
        weight_mom=1.0,
        weight_vol=0.0,
        weight_rev=0.0,
        industry_map={"STRONG.T": "SectorA", "WEAK.T": "SectorB"},
    )

    by_symbol = result.set_index("symbol")
    # Each stock is alone in its industry; both would be zeroed by the bug,
    # collapsing the ranking. Correct behavior gives non-zero cross-sectional z.
    assert by_symbol.loc["STRONG.T", "mom_z"] != 0.0
    assert by_symbol.loc["STRONG.T", "mom_z"] > by_symbol.loc["WEAK.T", "mom_z"]
    assert by_symbol.loc["STRONG.T", "is_top_n"]


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


def test_new_value_factors_default_weight_zero_is_unchanged():
    data = {
        "AAA.T": make_df([100] * 70 + list(range(100, 110)) + list(range(150, 130, -1))),
        "BBB.T": make_df([120] * 70 + list(range(120, 110, -1)) + [80] * 20),
        "CCC.T": make_df([100] * 100),
    }
    baseline = score_universe(data, top_n=2, weight_mom=1.0, weight_vol=1.0, weight_rev=1.0)
    with_inputs = score_universe(
        data, top_n=2, weight_mom=1.0, weight_vol=1.0, weight_rev=1.0,
        market_caps={"AAA.T": 1e9, "BBB.T": 2e9, "CCC.T": 3e9},
        ev_ebit_values={"AAA.T": 5.0, "BBB.T": 10.0, "CCC.T": 15.0},
        dividend_yields={"AAA.T": 0.01, "BBB.T": 0.02, "CCC.T": 0.03},
    )
    assert with_inputs["total_score"].round(10).tolist() == baseline["total_score"].round(10).tolist()


def test_size_factor_prefers_small_cap():
    data = {"SMALL.T": make_df([100] * 100), "BIG.T": make_df([100] * 100)}
    result = score_universe(
        data, top_n=1, weight_mom=0.0, weight_vol=0.0, weight_rev=0.0,
        weight_size=1.0, market_caps={"SMALL.T": 1e8, "BIG.T": 9e9},
    )
    assert result.set_index("symbol").loc["SMALL.T", "size_z"] > 0
    assert result.iloc[0]["symbol"] == "SMALL.T"


def test_evebit_factor_prefers_cheap_and_divy_prefers_high():
    data = {"CHEAP.T": make_df([100] * 100), "RICH.T": make_df([100] * 100)}
    ev = score_universe(
        data, top_n=1, weight_mom=0.0, weight_vol=0.0, weight_rev=0.0,
        weight_evebit=1.0, ev_ebit_values={"CHEAP.T": 4.0, "RICH.T": 40.0},
    )
    assert ev.iloc[0]["symbol"] == "CHEAP.T"
    dv = score_universe(
        {"HIGH.T": make_df([100] * 100), "LOW.T": make_df([100] * 100)},
        top_n=1, weight_mom=0.0, weight_vol=0.0, weight_rev=0.0,
        weight_divy=1.0, dividend_yields={"HIGH.T": 0.05, "LOW.T": 0.0},
    )
    assert dv.iloc[0]["symbol"] == "HIGH.T"
