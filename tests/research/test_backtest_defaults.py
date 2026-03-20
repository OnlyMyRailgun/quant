import json
from io import StringIO
from pathlib import Path
import sys

import pandas as pd
import pytest

import src.main as main
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
        artifact_run_name="backtest_rebalance",
        universe_name="topix_top_10",
    )

    assert kwargs == {
        "weight_mom": 0.5,
        "weight_vol": 1.0,
        "weight_rev": 0.5,
        "buy_rank_threshold": 2,
        "sell_rank_threshold": 4,
        "artifact_dir": tmp_path,
        "artifact_run_name": "backtest_rebalance",
        "universe_name": "topix_top_10",
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


def test_main_multi_factor_offline_smoke_uses_approved_params_and_skips_plot(monkeypatch, tmp_path: Path, capsys):
    write_approved_params(tmp_path, {"mom": 0.25, "vol": 0.75, "rev": 0.5})
    monkeypatch.setattr(main, "DEFAULT_ARTIFACT_DIR", tmp_path)
    monkeypatch.setattr(main, "get_topix_top_10", lambda: ["AAA.T", "BBB.T"])

    fetch_calls = []

    def fake_fetch_universe(symbols, start, end):
        fetch_calls.append({"symbols": symbols, "start": start, "end": end})
        return {symbol: pd.DataFrame({"Close": [100.0, 101.0, 102.0]}) for symbol in symbols}

    monkeypatch.setattr(main, "fetch_universe", fake_fetch_universe)

    captured = {}

    class FakeCerebro:
        def plot(self, *args, **kwargs):  # pragma: no cover - sanity guard
            raise AssertionError("plot should not be called when --no-plot is set")

    def fake_run_with_logging(data_dfs, strategy_class, kwargs_dict=None, initial_cash=1_000_000.0):
        captured["data_symbols"] = sorted(data_dfs)
        captured["strategy_class"] = strategy_class.__name__
        captured["kwargs_dict"] = kwargs_dict
        captured["initial_cash"] = initial_cash
        return (
            {
                "final_value": 1_010_000.0,
                "sharpe": 0.8,
                "max_drawdown": 2.5,
                "rebalance_count": 3,
                "position_change_count": 5,
                "turnover_ratio": 0.6,
            },
            FakeCerebro(),
        )

    monkeypatch.setattr(main, "run_with_logging", fake_run_with_logging)
    monkeypatch.setattr(sys, "argv", ["main.py", "--strategy", "multi", "--universe", "--no-plot"])

    exit_code = main.main()

    output = capsys.readouterr().out
    assert exit_code is None
    assert "Fetching data for 2 symbols from 2023-01-01 to 2024-01-01" in output
    assert captured["data_symbols"] == ["AAA.T", "BBB.T"]
    assert captured["strategy_class"] == "UniversalMultiFactor"
    assert captured["kwargs_dict"] == {
        "weight_mom": 0.25,
        "weight_vol": 0.75,
        "weight_rev": 0.5,
        "artifact_dir": tmp_path,
        "artifact_run_name": "backtest_rebalance",
        "universe_name": "topix_top_10",
    }
    assert captured["initial_cash"] == 1_000_000.0
    assert fetch_calls == [
        {
            "symbols": ["AAA.T", "BBB.T"],
            "start": "2023-01-01",
            "end": "2024-01-01",
        }
    ]


def test_main_multi_factor_can_select_named_universe_without_affecting_default_ticker_list(
    monkeypatch,
    tmp_path: Path,
    capsys,
):
    write_approved_params(tmp_path, {"mom": 0.25, "vol": 0.75, "rev": 0.5})
    monkeypatch.setattr(main, "DEFAULT_ARTIFACT_DIR", tmp_path)

    fetch_calls = []

    def fake_get_universe(name):
        assert name == "custom_universe"
        return ["1111.T", "2222.T"]

    def fake_get_topix_top_10():  # pragma: no cover - sanity guard
        raise AssertionError("get_topix_top_10 should not be used when --universe-name is set")

    def fake_fetch_universe(symbols, start, end):
        fetch_calls.append({"symbols": symbols, "start": start, "end": end})
        return {symbol: pd.DataFrame({"Close": [100.0, 101.0]}) for symbol in symbols}

    monkeypatch.setattr(main, "get_universe", fake_get_universe)
    monkeypatch.setattr(main, "get_topix_top_10", fake_get_topix_top_10)
    monkeypatch.setattr(main, "fetch_universe", fake_fetch_universe)
    captured = {}

    def fake_run_with_logging(data_dfs, strategy_class, kwargs_dict=None, initial_cash=1_000_000.0):
        captured["kwargs_dict"] = kwargs_dict
        return ({"final_value": 1_000_000.0, "sharpe": 0.0, "max_drawdown": 0.0}, object())

    monkeypatch.setattr(main, "run_with_logging", fake_run_with_logging)
    monkeypatch.setattr(sys, "argv", ["main.py", "--strategy", "multi", "--universe-name", "custom_universe", "--no-plot"])

    exit_code = main.main()

    output = capsys.readouterr().out
    assert exit_code is None
    assert "Fetching data for 2 symbols from 2023-01-01 to 2024-01-01" in output
    assert fetch_calls == [
        {
            "symbols": ["1111.T", "2222.T"],
            "start": "2023-01-01",
            "end": "2024-01-01",
        }
    ]
    assert captured["kwargs_dict"] == {
        "weight_mom": 0.25,
        "weight_vol": 0.75,
        "weight_rev": 0.5,
        "artifact_dir": tmp_path,
        "artifact_run_name": "backtest_rebalance",
        "universe_name": "custom_universe",
    }


def test_main_multi_factor_defaults_to_existing_small_ticker_list_when_no_universe_is_selected(
    monkeypatch,
    tmp_path: Path,
):
    write_approved_params(tmp_path, {"mom": 0.25, "vol": 0.75, "rev": 0.5})
    monkeypatch.setattr(main, "DEFAULT_ARTIFACT_DIR", tmp_path)

    fetch_calls = []

    def fake_get_universe(name):  # pragma: no cover - sanity guard
        raise AssertionError(f"get_universe should not be used for default ticker fallback: {name}")

    def fake_fetch_universe(symbols, start, end):
        fetch_calls.append({"symbols": symbols, "start": start, "end": end})
        return {symbol: pd.DataFrame({"Close": [100.0, 101.0]}) for symbol in symbols}

    monkeypatch.setattr(main, "get_universe", fake_get_universe)
    monkeypatch.setattr(main, "fetch_universe", fake_fetch_universe)
    monkeypatch.setattr(main, "run_with_logging", lambda *args, **kwargs: ({"final_value": 1_000_000.0, "sharpe": 0.0, "max_drawdown": 0.0}, object()))
    monkeypatch.setattr(sys, "argv", ["main.py", "--strategy", "multi", "--no-plot"])

    exit_code = main.main()

    assert exit_code is None
    assert fetch_calls == [
        {
            "symbols": ["7203.T", "6758.T", "8306.T"],
            "start": "2023-01-01",
            "end": "2024-01-01",
        }
    ]


def test_main_rejects_unknown_named_universe_with_friendly_error(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["main.py", "--strategy", "multi", "--universe-name", "unknown_universe", "--no-plot"],
    )

    with pytest.raises(SystemExit) as excinfo:
        main.main()

    output = capsys.readouterr().out
    assert excinfo.value.code == 1
    assert "Invalid universe name: unknown_universe" in output
    assert "Available universes: topix_top_10" in output
