from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from src.research.reversal_filter import (
    ReversalFilterParams,
    apply_reversal_filter,
)


def make_df(closes):
    """Build a DataFrame with Close column and DatetimeIndex from 2024-01-01."""
    dates = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"Close": closes}, index=dates)


# ---------------------------------------------------------------------------
# Test 1: params defaults
# ---------------------------------------------------------------------------

def test_reversal_filter_params_defaults():
    params = ReversalFilterParams()
    assert params.lookback_days == 20
    assert params.threshold == 0.10


def test_reversal_filter_params_custom():
    params = ReversalFilterParams(lookback_days=10, threshold=0.05)
    assert params.lookback_days == 10
    assert params.threshold == 0.05


def test_reversal_filter_params_is_frozen():
    params = ReversalFilterParams()
    with pytest.raises(Exception):
        params.lookback_days = 30  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test 2: flags sharp drop
# ---------------------------------------------------------------------------

def test_flags_sharp_drop():
    """Stock drops 35% → flagged. top_n=1 with sufficient non-top-n alternatives.
    Fallback not triggered because retained >= top_n."""
    bad_closes = [90] * 80 + [100] + [100 - i * 2 for i in range(1, 20)]
    good_closes = [90] * 80 + [105] * 20
    data = {
        "BAD.T": make_df(bad_closes),
        "GOOD.T": make_df(good_closes),
    }

    scored = pd.DataFrame({
        "symbol": ["BAD.T", "GOOD.T"],
        "price": [float(bad_closes[-1]), float(good_closes[-1])],
        "total_score": [2.0, 1.0],
        "rank": [1, 2],
        "is_top_n": [True, False],  # top_n=1
    })

    result = apply_reversal_filter(scored, data)

    assert "BAD.T" in result["flagged_symbols"]
    assert "GOOD.T" in result["retained_symbols"]
    assert result["by_symbol"]["BAD.T"]["flagged"] is True
    assert result["by_symbol"]["BAD.T"]["drawdown"] < -0.30


# ---------------------------------------------------------------------------
# Test 3: passes moderate drop
# ---------------------------------------------------------------------------

def test_passes_moderate_drop():
    """Stock drops from 100 to 93 over last 20 days → -7% drawdown → passes."""
    closes = [90] * 80 + [100, 99, 98, 97, 96, 95, 94, 93, 93, 93,
                           93, 93, 93, 93, 93, 93, 93, 93, 93, 93]
    data = {"STOCK.T": make_df(closes)}

    scored = pd.DataFrame({
        "symbol": ["STOCK.T"],
        "price": [float(closes[-1])],
        "total_score": [1.0],
        "rank": [1],
        "is_top_n": [True],
    })

    result = apply_reversal_filter(scored, data)

    assert result["retained_symbols"] == ["STOCK.T"]
    assert result["flagged_symbols"] == []
    assert result["by_symbol"]["STOCK.T"]["flagged"] is False


# ---------------------------------------------------------------------------
# Test 4: passes at high
# ---------------------------------------------------------------------------

def test_passes_at_high():
    """Stock price equals recent 20-day high → drawdown=0 → passes."""
    closes = [90] * 80 + [100] * 20
    data = {"STOCK.T": make_df(closes)}

    scored = pd.DataFrame({
        "symbol": ["STOCK.T"],
        "price": [100.0],
        "total_score": [1.0],
        "rank": [1],
        "is_top_n": [True],
    })

    result = apply_reversal_filter(scored, data)

    assert result["retained_symbols"] == ["STOCK.T"]
    assert result["by_symbol"]["STOCK.T"]["drawdown"] == 0.0


# ---------------------------------------------------------------------------
# Test 5: passes at new high
# ---------------------------------------------------------------------------

def test_passes_at_new_high():
    """Stock at all-time high → drawdown > 0 → passes."""
    closes = list(range(80, 100)) + list(range(100, 120))
    data = {"STOCK.T": make_df(closes)}

    scored = pd.DataFrame({
        "symbol": ["STOCK.T"],
        "price": [float(closes[-1])],
        "total_score": [1.0],
        "rank": [1],
        "is_top_n": [True],
    })

    result = apply_reversal_filter(scored, data)

    assert result["retained_symbols"] == ["STOCK.T"]
    assert result["by_symbol"]["STOCK.T"]["flagged"] is False


# ---------------------------------------------------------------------------
# Test 6: flags missing symbol
# ---------------------------------------------------------------------------

def test_flags_missing_symbol():
    """Symbol in scored_df but not in data_dfs → flagged (fail-safe)."""
    data = {}  # empty

    scored = pd.DataFrame({
        "symbol": ["MISSING.T"],
        "price": [100.0],
        "total_score": [1.0],
        "rank": [1],
        "is_top_n": [True],
    })

    result = apply_reversal_filter(scored, data)

    assert result["flagged_symbols"] == ["MISSING.T"]
    assert result["retained_symbols"] == []


# ---------------------------------------------------------------------------
# Test 7: flags insufficient data
# ---------------------------------------------------------------------------

def test_flags_insufficient_data():
    """Symbol has fewer data rows than lookback_days → flagged."""
    closes = [100] * 10  # only 10 rows, lookback=20
    data = {"STOCK.T": make_df(closes)}

    scored = pd.DataFrame({
        "symbol": ["STOCK.T"],
        "price": [100.0],
        "total_score": [1.0],
        "rank": [1],
        "is_top_n": [True],
    })

    result = apply_reversal_filter(scored, data)

    assert result["flagged_symbols"] == ["STOCK.T"]


# ---------------------------------------------------------------------------
# Test 8: empty input
# ---------------------------------------------------------------------------

def test_empty_input():
    """Empty scored_df → empty output with correct structure."""
    scored = pd.DataFrame({
        "symbol": pd.Series(dtype="str"),
        "total_score": pd.Series(dtype="float64"),
        "rank": pd.Series(dtype="int64"),
        "is_top_n": pd.Series(dtype="bool"),
    })

    result = apply_reversal_filter(scored, {})

    assert result["filtered_scores"].empty
    assert result["retained_symbols"] == []
    assert result["flagged_symbols"] == []
    assert result["summary"]["scored_symbol_count"] == 0
    assert result["summary"]["retention_ratio"] == 0.0


# ---------------------------------------------------------------------------
# Test 9: all flagged
# ---------------------------------------------------------------------------

def test_all_flagged():
    """When all scored symbols are flagged with deep drawdowns.
    Fallback ensures we still get top_n stocks back."""
    closes_bad1 = [90] * 80 + [100] + [100 - i * 3 for i in range(1, 20)]
    closes_bad2 = [90] * 80 + [100] + [100 - i * 3 for i in range(1, 20)]
    data = {
        "BAD1.T": make_df(closes_bad1),
        "BAD2.T": make_df(closes_bad2),
    }

    scored = pd.DataFrame({
        "symbol": ["BAD1.T", "BAD2.T"],
        "price": [float(closes_bad1[-1]), float(closes_bad2[-1])],
        "total_score": [2.0, 1.0],
        "rank": [1, 2],
        "is_top_n": [True, True],
    })

    result = apply_reversal_filter(scored, data)

    # Fallback fills to top_n with least-negative stocks
    assert len(result["retained_symbols"]) == 2
    assert result["flagged_symbols"] == []
    assert result["summary"]["retention_ratio"] == 1.0


# ---------------------------------------------------------------------------
# Test 10: none flagged
# ---------------------------------------------------------------------------

def test_none_flagged():
    """All stocks at highs → none flagged, output matches input structure."""
    closes = [90] * 80 + [105] * 20
    data = {
        "A.T": make_df(closes),
        "B.T": make_df(closes),
    }

    scored = pd.DataFrame({
        "symbol": ["A.T", "B.T"],
        "price": [105.0, 105.0],
        "total_score": [2.0, 1.0],
        "rank": [1, 2],
        "is_top_n": [True, False],
    })

    result = apply_reversal_filter(scored, data)

    assert len(result["retained_symbols"]) == 2
    assert result["flagged_symbols"] == []
    assert result["summary"]["retention_ratio"] == 1.0


# ---------------------------------------------------------------------------
# Test 11: preserves columns
# ---------------------------------------------------------------------------

def test_preserves_columns():
    """Filtered scores retains key input columns + adds reversal columns."""
    closes = [90] * 80 + [105] * 20
    data = {"A.T": make_df(closes)}

    required_columns = {"symbol", "total_score", "rank", "is_top_n"}
    scored = pd.DataFrame({
        "symbol": ["A.T"],
        "price": [105.0],
        "total_score": [1.0],
        "rank": [1],
        "is_top_n": [True],
        "mom_z": [0.5],
        "vol_z": [-0.3],
        "rev_z": [0.2],
    })

    result = apply_reversal_filter(scored, data)

    filtered = result["filtered_scores"]
    assert required_columns.issubset(set(filtered.columns))
    assert "reversal_drawdown" in filtered.columns
    assert "reversal_flagged" in filtered.columns


# ---------------------------------------------------------------------------
# Test 12: reassigns ranks
# ---------------------------------------------------------------------------

def test_reassigns_ranks():
    """After filtering, retained symbols get contiguous ranks."""
    bad_closes = [90] * 80 + [100] + [100 - i * 2 for i in range(1, 20)]
    good_closes = [90] * 80 + [105] * 20
    data = {
        "BAD.T": make_df(bad_closes),
        "GOOD1.T": make_df(good_closes),
        "GOOD2.T": make_df(good_closes),
        "GOOD3.T": make_df(good_closes),
    }

    scored = pd.DataFrame({
        "symbol": ["GOOD1.T", "BAD.T", "GOOD2.T", "GOOD3.T"],
        "price": [105.0, float(bad_closes[-1]), 105.0, 105.0],
        "total_score": [4.0, 3.0, 2.0, 1.0],
        "rank": [1, 2, 3, 4],
        "is_top_n": [True, True, False, False],  # top_n=2, 4 scored
    })

    result = apply_reversal_filter(scored, data)

    filtered = result["filtered_scores"]
    # 4 scored, BAD flagged, 3 retained, top_n=2
    assert list(filtered["rank"]) == [1, 2, 3]
    assert list(filtered["symbol"]) == ["GOOD1.T", "GOOD2.T", "GOOD3.T"]
    assert list(filtered["is_top_n"]) == [True, True, False]


# ---------------------------------------------------------------------------
# Test 13: summary counts
# ---------------------------------------------------------------------------

def test_summary_counts():
    """Summary statistics reflect filtering outcome correctly."""
    bad_closes = [90] * 80 + [100] + [100 - i * 2 for i in range(1, 20)]
    good_closes = [90] * 80 + [105] * 20
    data = {
        "BAD.T": make_df(bad_closes),
        "GOOD1.T": make_df(good_closes),
        "GOOD2.T": make_df(good_closes),
    }

    scored = pd.DataFrame({
        "symbol": ["GOOD1.T", "BAD.T", "GOOD2.T"],
        "price": [105.0, float(bad_closes[-1]), 105.0],
        "total_score": [3.0, 2.0, 1.0],
        "rank": [1, 2, 3],
        "is_top_n": [True, False, False],
    })

    result = apply_reversal_filter(scored, data)

    assert result["summary"]["scored_symbol_count"] == 3
    assert result["summary"]["retained_symbol_count"] == 2
    assert result["summary"]["flagged_symbol_count"] == 1
    assert result["summary"]["retention_ratio"] == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# Test 14: custom params
# ---------------------------------------------------------------------------

def test_custom_params():
    """Custom lookback and threshold change filtering behavior."""
    # Short, shallow drop: 5% in 5 days
    drops = [90] * 40 + [100, 99, 98, 97, 96, 95]
    flat = [90] * 40 + [100] * 6
    data = {
        "DROP.T": make_df(drops),
        "GOOD.T": make_df(flat),
    }

    scored = pd.DataFrame({
        "symbol": ["DROP.T", "GOOD.T"],
        "price": [95.0, 100.0],
        "total_score": [2.0, 1.0],
        "rank": [1, 2],
        "is_top_n": [True, False],  # top_n=1
    })

    # Default: lookback=20, threshold=10% → 5% drop is over full 20d → passes
    result_default = apply_reversal_filter(scored, data)
    assert "DROP.T" in result_default["retained_symbols"]

    # Custom: lookback=5, threshold=3% → 5% in 5 days → flagged
    custom = ReversalFilterParams(lookback_days=5, threshold=0.03)
    result_custom = apply_reversal_filter(scored, data, custom)
    assert "DROP.T" in result_custom["flagged_symbols"]


# ---------------------------------------------------------------------------
# Test 15: threshold boundary
# ---------------------------------------------------------------------------

def test_threshold_boundary():
    """Exactly at threshold boundary → passes (strict less-than)."""
    # Drawdown = exactly -10%
    closes = [90] * 80 + [100] + [90] * 19  # last 20: 100, 90x19 → high=100, latest=90, dd=-10%
    data = {"A.T": make_df(closes), "B.T": make_df(closes)}

    scored = pd.DataFrame({
        "symbol": ["A.T", "B.T"],
        "price": [90.0, 90.0],
        "total_score": [2.0, 1.0],
        "rank": [1, 2],
        "is_top_n": [True, False],
    })

    result = apply_reversal_filter(scored, data)

    # dd = -0.10, condition is dd < -threshold = -0.10
    # -0.10 < -0.10 is False → passes (not flagged)
    assert "A.T" in result["retained_symbols"]
    assert result["by_symbol"]["A.T"]["flagged"] is False


# ---------------------------------------------------------------------------
# Test 16: fallback relaxes threshold
# ---------------------------------------------------------------------------

def test_fallback_relaxes_threshold():
    """When many stocks are flagged, threshold relaxes to meet top_n."""
    symbols = [f"S{i:02d}.T" for i in range(8)]
    data = {}
    for i, sym in enumerate(symbols):
        if i < 2:
            # 2 stocks at highs → pass
            data[sym] = make_df([90] * 80 + [105] * 20)
        else:
            # 6 stocks with various drawdowns: -12%, -14%, ..., -24%
            drawdown_pct = 0.12 + (i - 2) * 0.02
            peak = 100
            trough = int(peak * (1 - drawdown_pct))
            data[sym] = make_df([90] * 80 + [peak] + [peak - j for j in range(1, 20)])

    scored = pd.DataFrame({
        "symbol": symbols,
        "price": [105.0] * 2 + [80.0] * 6,
        "total_score": list(range(8, 0, -1)),
        "rank": list(range(1, 9)),
        "is_top_n": [True] * 5 + [False] * 3,  # top_n=5
    })

    result = apply_reversal_filter(scored, data)

    # Default threshold=10%: all 6 bad stocks flagged at first
    # Fallback relaxes: 15%→20%→25%→30%, stopping when retained >= 5
    # At relaxed=15%: -12% > -15% → 1 un-flagged → retained=3
    # At relaxed=20%: -12%, -14%, -16%, -18% > -20% → 4 more → retained=7, stop
    assert len(result["retained_symbols"]) >= 5
    assert result["summary"]["retained_symbol_count"] >= 5
    # At least some stocks that would be flagged at 10% are now retained
    assert result["summary"]["flagged_symbol_count"] < 6


# ---------------------------------------------------------------------------
# Test 17: integration with scoring
# ---------------------------------------------------------------------------

def test_integration_with_scoring():
    """Full pipeline: score_universe → apply_reversal_filter."""
    from src.scoring.multi_factor import score_universe

    # Create data suitable for scoring (need enough history for lookbacks)
    # 120+ days to satisfy 90-day momentum lookback
    good_closes = [100 + i * 0.5 for i in range(120)]  # steady uptrend
    bad_closes = [100 + i * 0.5 for i in range(100)] + list(range(150, 70, -4))

    data = {
        "GOOD.T": pd.DataFrame({"Close": good_closes},
                                index=pd.date_range("2023-01-01", periods=120, freq="D")),
        "BAD.T": pd.DataFrame({"Close": bad_closes},
                               index=pd.date_range("2023-01-01", periods=120, freq="D")),
    }

    scored = score_universe(data, top_n=2, weight_mom=1.0, weight_vol=0.0, weight_rev=0.0)

    result = apply_reversal_filter(scored, data)

    assert "filtered_scores" in result
    assert "summary" in result
    assert "retained_symbols" in result
    # The pipeline runs without error
    assert len(result["filtered_scores"]) <= len(scored)
