from io import StringIO
import json
from pathlib import Path

from src.main import resolve_multi_factor_strategy_kwargs, resolve_multi_factor_weights, render_backtest_results
from src.paper.bot import _resolve_signal_weights


def write_approved_params(tmp_path: Path, weights: dict[str, float]) -> None:
    (tmp_path / "paper_trade_params.json").write_text(
        json.dumps(
            {
                "source_run_id": "wf-2",
                "rebalance_date": "2022-07-01",
                "weights": weights,
            }
        ),
        encoding="utf-8",
    )


def test_resolve_multi_factor_weights_uses_approved_params_when_cli_uses_defaults(tmp_path: Path):
    write_approved_params(tmp_path, {"mom": 0.5, "vol": 1.0, "rev": 0.5})

    weights = resolve_multi_factor_weights(
        artifact_dir=tmp_path,
        weight_mom=None,
        weight_vol=None,
        weight_rev=None,
    )

    assert weights == {"weight_mom": 0.5, "weight_vol": 1.0, "weight_rev": 0.5}


def test_resolve_multi_factor_weights_respects_explicit_cli_overrides(tmp_path: Path):
    write_approved_params(tmp_path, {"mom": 0.5, "vol": 1.0, "rev": 0.5})

    weights = resolve_multi_factor_weights(
        artifact_dir=tmp_path,
        weight_mom=1.0,
        weight_vol=None,
        weight_rev=0.0,
    )

    assert weights == {"weight_mom": 1.0, "weight_vol": 1.0, "weight_rev": 0.0}


def test_backtest_and_paper_resolve_same_approved_weights(tmp_path: Path):
    write_approved_params(tmp_path, {"mom": 0.0, "vol": 1.0, "rev": 0.5})

    backtest_weights = resolve_multi_factor_weights(
        artifact_dir=tmp_path,
        weight_mom=None,
        weight_vol=None,
        weight_rev=None,
    )
    paper_weights = _resolve_signal_weights(
        artifact_dir=tmp_path,
        weight_mom=None,
        weight_vol=None,
        weight_rev=None,
    )

    assert backtest_weights == {"weight_mom": 0.0, "weight_vol": 1.0, "weight_rev": 0.5}
    assert paper_weights == (0.0, 1.0, 0.5)


def test_resolve_multi_factor_strategy_kwargs_preserves_weight_defaults_and_thresholds(tmp_path: Path):
    write_approved_params(tmp_path, {"mom": 0.5, "vol": 1.0, "rev": 0.5})

    kwargs = resolve_multi_factor_strategy_kwargs(
        artifact_dir=tmp_path,
        weight_mom=None,
        weight_vol=None,
        weight_rev=None,
        buy_rank_threshold=2,
        sell_rank_threshold=4,
    )

    assert kwargs == {
        "weight_mom": 0.5,
        "weight_vol": 1.0,
        "weight_rev": 0.5,
        "buy_rank_threshold": 2,
        "sell_rank_threshold": 4,
    }


def test_render_backtest_results_includes_turnover_metrics(capsys):
    output = StringIO()
    render_backtest_results(
        metrics={
            "final_value": 1_050_000.0,
            "max_drawdown": 5.25,
            "sharpe": 1.2,
            "rebalance_count": 4,
            "position_change_count": 6,
            "turnover_ratio": 1.5,
        },
        initial_cash=1_000_000.0,
        strategy_name="UniversalMultiFactor",
        output=output,
    )

    rendered = output.getvalue()
    assert "Rebalance Count : 4" in rendered
    assert "Position Changes: 6" in rendered
    assert "Turnover Ratio  : 1.5000" in rendered
