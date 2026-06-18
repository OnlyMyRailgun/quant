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


def test_resolve_multi_factor_weights_preserves_optional_value_quality_weights(tmp_path: Path):
    write_approved_params(
        tmp_path,
        {"mom": 0.5, "vol": 1.0, "rev": 0.5, "val": 0.25, "qual": 0.75},
    )

    weights = resolve_multi_factor_weights(
        artifact_dir=tmp_path,
        weight_mom=None,
        weight_vol=None,
        weight_rev=None,
    )

    assert weights == {
        "weight_mom": 0.5,
        "weight_vol": 1.0,
        "weight_rev": 0.5,
        "weight_val": 0.25,
        "weight_qual": 0.75,
    }


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

    screen_calls = []

    def fake_screen_universe(candidate_symbols, data_dfs, start, end, screen_as_of, screening_rules=None):
        screen_calls.append(
            {
                "candidate_symbols": list(candidate_symbols),
                "data_symbols": sorted(data_dfs),
                "start": start,
                "end": end,
                "screen_as_of": screen_as_of,
            }
        )
        return {
            "eligible_symbols": list(candidate_symbols),
            "rejected_symbols": [],
            "by_symbol": {
                symbol: {
                    "symbol": symbol,
                    "eligible": True,
                    "reasons": [],
                    "metrics": {},
                }
                for symbol in candidate_symbols
            },
            "summary": {
                "requested_symbol_count": len(candidate_symbols),
                "eligible_symbol_count": len(candidate_symbols),
                "screened_out_symbol_count": 0,
            },
        }

    monkeypatch.setattr(main, "screen_universe", fake_screen_universe)

    screening_artifacts = []

    def fake_write_screening_run(*args, **kwargs):
        screening_artifacts.append({"args": args, "kwargs": kwargs})
        return {"run_dir": tmp_path / "screening", "metadata": tmp_path / "screening" / "metadata.json", "decisions": tmp_path / "screening" / "decisions.csv", "summary": tmp_path / "screening" / "summary.json"}

    monkeypatch.setattr(main, "write_screening_run", fake_write_screening_run)

    captured = {}

    def fake_run_backtest(
        data_dfs,
        strategy_class,
        initial_cash=1_000_000.0,
        engine="backtrader",
        momentum_definition="90d",
        reversal_filter_params=None,
        start=None,
        end=None,
        strategy_kwargs=None,
    ):
        captured["data_symbols"] = sorted(data_dfs)
        captured["strategy_class"] = strategy_class.__name__
        captured["initial_cash"] = initial_cash
        captured["engine"] = engine
        captured["momentum_definition"] = momentum_definition
        captured["reversal_filter_params"] = reversal_filter_params
        captured["start"] = start
        captured["end"] = end
        captured["strategy_kwargs"] = strategy_kwargs
        return {
            "metrics": {
                "final_value": 1_010_000.0,
                "sharpe": 0.8,
                "max_drawdown": 2.5,
                "rebalance_count": 3,
                "position_change_count": 5,
                "turnover_ratio": 0.6,
            },
            "cerebro": object(),
        }

    monkeypatch.setattr(
        main,
        "run_with_logging",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("run_with_logging should not be called for default simple engine")
        ),
    )
    monkeypatch.setattr(main, "run_backtest", fake_run_backtest, raising=False)
    monkeypatch.setattr(sys, "argv", ["main.py", "--strategy", "multi", "--universe", "--no-plot"])

    exit_code = main.main()

    output = capsys.readouterr().out
    assert exit_code is None
    assert "Fetching data for 2 symbols from 2023-01-01 to 2024-01-01" in output
    assert captured["data_symbols"] == ["AAA.T", "BBB.T"]
    assert captured["strategy_class"] == "UniversalMultiFactor"
    assert captured["initial_cash"] == 1_000_000.0
    assert captured["engine"] == "simple"
    assert captured["momentum_definition"] == "90d"
    assert captured["reversal_filter_params"] is None
    assert captured["start"] == "2023-01-01"
    assert captured["end"] == "2024-01-01"
    assert captured["strategy_kwargs"] == {
        "weight_mom": 0.25,
        "weight_vol": 0.75,
        "weight_rev": 0.5,
        "artifact_dir": tmp_path,
        "artifact_run_name": "backtest_rebalance",
        "universe_name": "topix_top_10",
    }
    assert fetch_calls == [
        {
            "symbols": ["AAA.T", "BBB.T"],
            "start": "2023-01-01",
            "end": "2024-01-01",
        }
    ]
    assert screen_calls == [
        {
            "candidate_symbols": ["AAA.T", "BBB.T"],
            "data_symbols": ["AAA.T", "BBB.T"],
            "start": "2023-01-01",
            "end": "2024-01-01",
            "screen_as_of": "2024-01-01",
        }
    ]
    assert len(screening_artifacts) == 1


def test_main_simple_engine_uses_engine_dispatch_instead_of_logging(monkeypatch, tmp_path: Path):
    write_approved_params(tmp_path, {"mom": 0.25, "vol": 0.75, "rev": 0.5})
    monkeypatch.setattr(main, "DEFAULT_ARTIFACT_DIR", tmp_path)
    monkeypatch.setattr(
        main,
        "fetch_universe",
        lambda symbols, start, end: {
            symbol: pd.DataFrame({"Close": [100.0, 101.0, 102.0]})
            for symbol in symbols
        },
    )
    monkeypatch.setattr(
        main,
        "run_with_logging",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("run_with_logging should not be called for --engine simple")
        ),
    )

    captured = {}

    def fake_run_backtest(
        data_dfs,
        strategy_class,
        initial_cash=1_000_000.0,
        engine="backtrader",
        momentum_definition="90d",
        reversal_filter_params=None,
        start=None,
        end=None,
        strategy_kwargs=None,
    ):
        captured["data_symbols"] = sorted(data_dfs)
        captured["strategy_class"] = strategy_class.__name__
        captured["initial_cash"] = initial_cash
        captured["engine"] = engine
        captured["momentum_definition"] = momentum_definition
        captured["reversal_filter_params"] = reversal_filter_params
        captured["start"] = start
        captured["end"] = end
        captured["strategy_kwargs"] = strategy_kwargs
        return {
            "metrics": {
                "final_value": 1_010_000.0,
                "sharpe": 0.8,
                "max_drawdown": 2.5,
                "rebalance_count": 0,
                "position_change_count": 0,
                "turnover_ratio": 0.0,
            },
            "cerebro": object(),
        }

    monkeypatch.setattr(main, "run_backtest", fake_run_backtest, raising=False)
    monkeypatch.setattr(sys, "argv", ["main.py", "--strategy", "multi", "--engine", "simple", "--no-plot"])

    exit_code = main.main()

    assert exit_code is None
    assert captured == {
        "data_symbols": ["6758.T", "7203.T", "8306.T"],
        "strategy_class": "UniversalMultiFactor",
        "initial_cash": 1_000_000.0,
        "engine": "simple",
        "momentum_definition": "90d",
        "reversal_filter_params": None,
        "start": "2023-01-01",
        "end": "2024-01-01",
        "strategy_kwargs": {
            "weight_mom": 0.25,
            "weight_vol": 0.75,
            "weight_rev": 0.5,
            "artifact_dir": tmp_path,
            "artifact_run_name": "backtest_rebalance",
        },
    }


def test_main_multi_factor_filters_named_universe_with_screening(monkeypatch, tmp_path: Path, capsys):
    write_approved_params(tmp_path, {"mom": 0.25, "vol": 0.75, "rev": 0.5})
    monkeypatch.setattr(main, "DEFAULT_ARTIFACT_DIR", tmp_path)

    fetch_calls = []

    def fake_get_universe(name):
        assert name == "custom_universe"
        return ["AAA.T", "BBB.T", "CCC.T"]

    def fake_fetch_universe(symbols, start, end):
        fetch_calls.append({"symbols": symbols, "start": start, "end": end})
        return {symbol: pd.DataFrame({"Close": [100.0, 101.0]}) for symbol in symbols}

    monkeypatch.setattr(main, "get_universe", fake_get_universe)
    monkeypatch.setattr(main, "fetch_universe", fake_fetch_universe)

    screening_calls = []

    def fake_screen_universe(candidate_symbols, data_dfs, start, end, screen_as_of, screening_rules=None):
        screening_calls.append(
            {
                "candidate_symbols": list(candidate_symbols),
                "data_symbols": sorted(data_dfs),
                "start": start,
                "end": end,
                "screen_as_of": screen_as_of,
            }
        )
        return {
            "eligible_symbols": ["AAA.T", "CCC.T"],
            "rejected_symbols": ["BBB.T"],
            "by_symbol": {
                "AAA.T": {"symbol": "AAA.T", "eligible": True, "reasons": [], "metrics": {}},
                "BBB.T": {"symbol": "BBB.T", "eligible": False, "reasons": ["low_latest_close"], "metrics": {}},
                "CCC.T": {"symbol": "CCC.T", "eligible": True, "reasons": [], "metrics": {}},
            },
            "summary": {
                "requested_symbol_count": 3,
                "eligible_symbol_count": 2,
                "screened_out_symbol_count": 1,
            },
        }

    monkeypatch.setattr(main, "screen_universe", fake_screen_universe)

    screening_artifacts = []

    def fake_write_screening_run(base_dir, run_name, metadata, decisions, summary, run_id=None, timestamp=None, created_at=None):
        screening_artifacts.append(
            {
                "base_dir": base_dir,
                "run_name": run_name,
                "metadata": metadata,
                "summary": summary,
                "decisions_symbols": decisions["symbol"].tolist(),
            }
        )
        return {
            "run_dir": tmp_path / "screening" / "run",
            "metadata": tmp_path / "screening" / "metadata.json",
            "decisions": tmp_path / "screening" / "decisions.csv",
            "summary": tmp_path / "screening" / "summary.json",
        }

    monkeypatch.setattr(main, "write_screening_run", fake_write_screening_run)

    captured = {}

    def fake_run_backtest(
        data_dfs,
        strategy_class,
        initial_cash=1_000_000.0,
        engine="backtrader",
        momentum_definition="90d",
        reversal_filter_params=None,
        start=None,
        end=None,
        strategy_kwargs=None,
    ):
        captured["data_symbols"] = list(data_dfs)
        captured["strategy_class"] = strategy_class.__name__
        captured["initial_cash"] = initial_cash
        captured["engine"] = engine
        captured["momentum_definition"] = momentum_definition
        captured["reversal_filter_params"] = reversal_filter_params
        captured["start"] = start
        captured["end"] = end
        captured["strategy_kwargs"] = strategy_kwargs
        return {
            "metrics": {"final_value": 1_000_000.0, "sharpe": 0.0, "max_drawdown": 0.0},
            "cerebro": object(),
        }

    monkeypatch.setattr(
        main,
        "run_with_logging",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("run_with_logging should not be called for default simple engine")
        ),
    )
    monkeypatch.setattr(main, "run_backtest", fake_run_backtest, raising=False)
    monkeypatch.setattr(sys, "argv", ["main.py", "--strategy", "multi", "--universe-name", "custom_universe", "--no-plot"])

    exit_code = main.main()

    output = capsys.readouterr().out
    assert exit_code is None
    assert "Screening summary: requested=3 eligible=2 screened_out=1" in output
    assert captured["data_symbols"] == ["AAA.T", "CCC.T"]
    assert captured["strategy_class"] == "UniversalMultiFactor"
    assert captured["engine"] == "simple"
    assert captured["start"] == "2023-01-01"
    assert captured["end"] == "2024-01-01"
    assert captured["strategy_kwargs"] == {
        "weight_mom": 0.25,
        "weight_vol": 0.75,
        "weight_rev": 0.5,
        "artifact_dir": tmp_path,
        "artifact_run_name": "backtest_rebalance",
        "universe_name": "custom_universe",
    }
    assert screening_calls == [
        {
            "candidate_symbols": ["AAA.T", "BBB.T", "CCC.T"],
            "data_symbols": ["AAA.T", "BBB.T", "CCC.T"],
            "start": "2023-01-01",
            "end": "2024-01-01",
            "screen_as_of": "2024-01-01",
        }
    ]
    assert len(screening_artifacts) == 1
    assert screening_artifacts[0]["base_dir"] == tmp_path
    assert screening_artifacts[0]["run_name"] == "universe_screening"
    assert screening_artifacts[0]["summary"] == {
        "requested_symbol_count": 3,
        "eligible_symbol_count": 2,
        "screened_out_symbol_count": 1,
    }
    assert screening_artifacts[0]["decisions_symbols"] == ["AAA.T", "BBB.T", "CCC.T"]


def test_main_exits_friendly_when_screening_removes_every_symbol(monkeypatch, tmp_path: Path, capsys):
    write_approved_params(tmp_path, {"mom": 0.25, "vol": 0.75, "rev": 0.5})
    monkeypatch.setattr(main, "DEFAULT_ARTIFACT_DIR", tmp_path)

    monkeypatch.setattr(main, "get_universe", lambda name: ["AAA.T", "BBB.T"])
    monkeypatch.setattr(
        main,
        "fetch_universe",
        lambda symbols, start, end: {symbol: pd.DataFrame({"Close": [100.0, 101.0]}) for symbol in symbols},
    )
    monkeypatch.setattr(
        main,
        "screen_universe",
        lambda *args, **kwargs: {
            "eligible_symbols": [],
            "rejected_symbols": ["AAA.T", "BBB.T"],
            "by_symbol": {
                "AAA.T": {"symbol": "AAA.T", "eligible": False, "reasons": ["low_latest_close"], "metrics": {}},
                "BBB.T": {"symbol": "BBB.T", "eligible": False, "reasons": ["low_latest_close"], "metrics": {}},
            },
            "summary": {
                "requested_symbol_count": 2,
                "eligible_symbol_count": 0,
                "screened_out_symbol_count": 2,
            },
        },
    )

    screening_artifacts = []

    def fake_write_screening_run(*args, **kwargs):
        screening_artifacts.append(kwargs)
        return {
            "run_dir": tmp_path / "screening" / "run",
            "metadata": tmp_path / "screening" / "metadata.json",
            "decisions": tmp_path / "screening" / "decisions.csv",
            "summary": tmp_path / "screening" / "summary.json",
        }

    monkeypatch.setattr(main, "write_screening_run", fake_write_screening_run)
    monkeypatch.setattr(
        main,
        "run_with_logging",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_with_logging should not be called when screening removes every symbol")),
    )
    monkeypatch.setattr(sys, "argv", ["main.py", "--strategy", "multi", "--universe-name", "custom_universe", "--no-plot"])

    with pytest.raises(SystemExit) as excinfo:
        main.main()

    output = capsys.readouterr().out
    assert excinfo.value.code == 1
    assert "No symbols remained after screening" in output
    assert len(screening_artifacts) == 1


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
    monkeypatch.setattr(
        main,
        "screen_universe",
        lambda *args, **kwargs: {
            "eligible_symbols": ["1111.T", "2222.T"],
            "rejected_symbols": [],
            "by_symbol": {
                "1111.T": {"symbol": "1111.T", "eligible": True, "reasons": [], "metrics": {}},
                "2222.T": {"symbol": "2222.T", "eligible": True, "reasons": [], "metrics": {}},
            },
            "summary": {
                "requested_symbol_count": 2,
                "eligible_symbol_count": 2,
                "screened_out_symbol_count": 0,
            },
        },
    )
    monkeypatch.setattr(
        main,
        "write_screening_run",
        lambda *args, **kwargs: {
            "run_dir": tmp_path / "screening" / "run",
            "metadata": tmp_path / "screening" / "metadata.json",
            "decisions": tmp_path / "screening" / "decisions.csv",
            "summary": tmp_path / "screening" / "summary.json",
        },
    )
    captured = {}

    def fake_run_backtest(
        data_dfs,
        strategy_class,
        initial_cash=1_000_000.0,
        engine="backtrader",
        momentum_definition="90d",
        reversal_filter_params=None,
        start=None,
        end=None,
        strategy_kwargs=None,
    ):
        del data_dfs, strategy_class, initial_cash, momentum_definition, reversal_filter_params
        captured["engine"] = engine
        captured["start"] = start
        captured["end"] = end
        captured["strategy_kwargs"] = strategy_kwargs
        return {
            "metrics": {"final_value": 1_000_000.0, "sharpe": 0.0, "max_drawdown": 0.0},
            "cerebro": object(),
        }

    monkeypatch.setattr(
        main,
        "run_with_logging",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("run_with_logging should not be called for default simple engine")
        ),
    )
    monkeypatch.setattr(main, "run_backtest", fake_run_backtest, raising=False)
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
    assert captured["engine"] == "simple"
    assert captured["start"] == "2023-01-01"
    assert captured["end"] == "2024-01-01"
    assert captured["strategy_kwargs"] == {
        "weight_mom": 0.25,
        "weight_vol": 0.75,
        "weight_rev": 0.5,
        "artifact_dir": tmp_path,
        "artifact_run_name": "backtest_rebalance",
        "universe_name": "custom_universe",
    }


def test_main_defaults_do_not_run_screening_without_universe_selection(
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
    monkeypatch.setattr(
        main,
        "screen_universe",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("screen_universe should not be called for default ticker fallback")),
    )
    monkeypatch.setattr(
        main,
        "write_screening_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("write_screening_run should not be called for default ticker fallback")),
    )
    monkeypatch.setattr(
        main,
        "run_with_logging",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("run_with_logging should not be called for default simple engine")
        ),
    )
    monkeypatch.setattr(
        main,
        "run_backtest",
        lambda *args, **kwargs: {
            "metrics": {"final_value": 1_000_000.0, "sharpe": 0.0, "max_drawdown": 0.0},
            "cerebro": object(),
        },
        raising=False,
    )
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
