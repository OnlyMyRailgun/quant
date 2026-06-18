from __future__ import annotations

import argparse
import inspect
import sys
from collections.abc import Callable, Mapping
from itertools import product
from pathlib import Path

import backtrader as bt
import pandas as pd

from src.data.bulk_loader import fetch_universe
from src.data import local_store
from src.data.universe import (
    format_unknown_universe_message,
    get_topix_top_10,
    get_universe,
)
from src.engine.commission import JapanStockCommission
from src.research.artifacts import DEFAULT_ARTIFACT_DIR, build_walk_forward_metadata, write_walk_forward_run
from src.research.research_scoring import score_research_universe
from src.research.walk_forward import run_walk_forward_experiment
from src.scoring.multi_factor import (
    DEFAULT_LOOKBACK_MOM,
    DEFAULT_LOOKBACK_REV,
    DEFAULT_LOOKBACK_VOL,
    score_universe,
)
from src.strategies.multi_factor import UniversalMultiFactor


STARTING_CASH = 1_000_000.0
DEFAULT_BASELINE_WEIGHTS = (1.0, 1.0, 1.0, 0.0)
DEFAULT_WEIGHT_GRID = [
    weights
    for weights in product((0.0, 0.5, 1.0), repeat=4)
    if any(w != 0.0 for w in weights)
]
DEFAULT_OPTIMIZE_START = "2021-01-01"
DEFAULT_OPTIMIZE_END = "2024-01-01"
DEFAULT_TRAIN_MONTHS = 12
DEFAULT_VALIDATION_MONTHS = 6
DEFAULT_STEP_MONTHS = 6
DEFAULT_BENCHMARK_SYMBOLS = {
    "topx": "1306.T",
    "n225": "1321.T",
}
SUPPORTED_MOMENTUM_DEFINITIONS = {"90d", "12_1"}
BookValuesInput = (
    Mapping[str, float | None]
    | Callable[[pd.Timestamp], Mapping[str, float | None] | None]
    | None
)


def _resolve_book_values(
    book_values: BookValuesInput,
    as_of_date: str | pd.Timestamp,
) -> Mapping[str, float | None] | None:
    if callable(book_values):
        return book_values(pd.Timestamp(as_of_date))
    return book_values


def _call_evaluate_weight_tuple(
    data_dfs: dict[str, pd.DataFrame],
    start: str,
    end: str,
    weights: tuple[float, ...],
    **kwargs,
) -> dict[str, object]:
    evaluator = evaluate_weight_tuple
    try:
        signature = inspect.signature(evaluator)
    except (TypeError, ValueError):
        return evaluator(data_dfs, start, end, weights, **kwargs)

    accepts_var_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    if not accepts_var_kwargs:
        kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in signature.parameters
        }

    return evaluator(data_dfs, start, end, weights, **kwargs)


def _strategy_param_names(strategy_class) -> set[str]:
    params = getattr(strategy_class, "params", None)
    if params is None:
        return set()
    if isinstance(params, Mapping):
        return set(params)
    if hasattr(params, "_getkeys"):
        return set(params._getkeys())
    return {
        name
        for name in dir(params)
        if not name.startswith("_")
    }


def _filter_strategy_kwargs(strategy_class, kwargs: dict[str, object]) -> dict[str, object]:
    param_names = _strategy_param_names(strategy_class)
    if not param_names:
        return {}
    return {
        key: value
        for key, value in kwargs.items()
        if key in param_names
    }


class SymbolReturnAnalyzer(bt.Analyzer):
    def start(self):
        self._starting_value = float(self.strategy.broker.getvalue())
        self._realized_pnl_by_symbol: dict[str, float] = {}

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        symbol = trade.data._name if hasattr(trade.data, "_name") else "UNKNOWN"
        self._realized_pnl_by_symbol[symbol] = (
            self._realized_pnl_by_symbol.get(symbol, 0.0) + float(trade.pnlcomm)
        )

    def get_analysis(self):
        rows: list[dict[str, float | str]] = []
        seen_symbols = set(self._realized_pnl_by_symbol)

        for data in self.strategy.datas:
            symbol = data._name if hasattr(data, "_name") else "UNKNOWN"
            position = self.strategy.getposition(data)
            pnl = float(self._realized_pnl_by_symbol.get(symbol, 0.0))
            if position.size:
                seen_symbols.add(symbol)
                pnl += float((data.close[0] - position.price) * position.size)

            if symbol not in seen_symbols:
                continue

            return_pct = 0.0
            if self._starting_value > 0.0:
                return_pct = round((pnl / self._starting_value) * 100.0, 4)
            rows.append({"symbol": symbol, "return_pct": return_pct})

        rows.sort(key=lambda row: str(row["symbol"]))
        return {"symbol_returns": rows}


class WindowReturnAnalyzer(bt.Analyzer):
    """Computes a simple return over an evaluation sub-window.

    This is used to support warmup bars (history before the evaluation start) without
    requiring the strategy to manage an explicit warmup/trading toggle.
    """

    params = dict(evaluation_start=None, evaluation_end=None)

    def start(self):
        evaluation_start = self.p.evaluation_start
        evaluation_end = self.p.evaluation_end
        if evaluation_start is None or evaluation_end is None:
            raise ValueError("evaluation_start and evaluation_end are required")

        self._evaluation_start = pd.Timestamp(evaluation_start).date()
        self._evaluation_end = pd.Timestamp(evaluation_end).date()
        if self._evaluation_end < self._evaluation_start:
            raise ValueError("evaluation_end must be on or after evaluation_start")

        self._start_value: float | None = None
        self._end_value: float | None = None

    def next(self):
        current = self.strategy.datetime.date(0)
        if self._start_value is None and current >= self._evaluation_start:
            self._start_value = float(self.strategy.broker.getvalue())

        if current <= self._evaluation_end:
            self._end_value = float(self.strategy.broker.getvalue())

    def get_analysis(self):
        if self._start_value is None or self._end_value is None:
            return {"return_pct": 0.0}
        if self._start_value <= 0.0:
            return {"return_pct": 0.0}
        return {"return_pct": round(((self._end_value / self._start_value) - 1.0) * 100.0, 4)}


def _prepare_price_frame_for_backtrader(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize local-store frames (Date column) into the indexed format expected elsewhere."""
    normalized = frame.copy()
    if "Date" in normalized.columns:
        dates = pd.to_datetime(normalized["Date"], errors="coerce", utc=True)
        dates = dates.dt.tz_convert(None)
        normalized["Date"] = dates
        normalized = normalized.dropna(subset=["Date"])
        normalized = normalized.sort_values("Date", kind="mergesort")
        normalized = normalized.drop_duplicates(subset=["Date"], keep="last")
        normalized = normalized.set_index("Date")
    else:
        index = pd.to_datetime(normalized.index, errors="coerce")
        if getattr(index, "tz", None) is not None:
            index = index.tz_convert(None)
        normalized.index = index
        normalized = normalized.loc[~normalized.index.isna()].sort_index(kind="mergesort")

    if getattr(normalized.index, "tz", None) is not None:
        normalized.index = normalized.index.tz_convert(None)
    return normalized


def suppress_output(strategy_class):
    """Temporarily suppress noisy strategy callbacks during optimization."""
    strategy_class.notify_order = lambda self, order: None
    strategy_class.notify_trade = lambda self, trade: None


def _slice_window_data(
    data_dfs: dict[str, pd.DataFrame],
    start: str,
    end: str,
    warmup_bars: int = 0,
) -> dict[str, pd.DataFrame]:
    window_dfs: dict[str, pd.DataFrame] = {}
    start_ts = pd.Timestamp(start)
    for symbol, df in data_dfs.items():
        try:
            up_to_end_df = df.loc[:end]
        except KeyError:
            continue

        if up_to_end_df.empty:
            continue

        if warmup_bars > 0:
            pre_window_df = up_to_end_df[up_to_end_df.index < start_ts].tail(warmup_bars)
            in_window_df = up_to_end_df[up_to_end_df.index >= start_ts]
            window_df = pd.concat([pre_window_df, in_window_df])
            window_df = window_df[~window_df.index.duplicated(keep="last")].sort_index()
        else:
            window_df = up_to_end_df.loc[start:end]

        if not window_df.empty:
            window_dfs[symbol] = window_df
    return window_dfs


def _build_validation_participation_metrics(
    data_dfs: dict[str, pd.DataFrame],
    universe_symbols: list[str] | None,
    validation_start: str,
    validation_end: str,
) -> dict[str, float | int]:
    if universe_symbols is None:
        return {}

    loaded_symbol_count = 0
    for symbol in universe_symbols:
        df = data_dfs.get(symbol)
        if df is None:
            continue
        try:
            window_df = df.loc[validation_start:validation_end]
        except KeyError:
            continue
        if not window_df.empty:
            loaded_symbol_count += 1

    requested_symbol_count = len(universe_symbols)
    skipped_symbol_count = requested_symbol_count - loaded_symbol_count
    coverage_ratio = 0.0
    if requested_symbol_count > 0:
        coverage_ratio = round(loaded_symbol_count / requested_symbol_count, 4)

    return {
        "requested_symbol_count": requested_symbol_count,
        "loaded_symbol_count": loaded_symbol_count,
        "skipped_symbol_count": skipped_symbol_count,
        "coverage_ratio": coverage_ratio,
    }


def _evaluate_weight_tuple_with_momentum(
    data_dfs: dict[str, pd.DataFrame],
    start: str,
    end: str,
    weights: tuple[float, float, float],
    momentum_definition: str,
    reversal_filter_params=None,
    engine="simple",
    book_values: BookValuesInput = None,
    top_n: int = 3,
) -> dict[str, object]:
    return _call_evaluate_weight_tuple(
        data_dfs,
        start,
        end,
        weights,
        momentum_definition=momentum_definition,
        reversal_filter_params=reversal_filter_params,
        engine=engine,
        book_values=book_values,
        top_n=top_n,
    )


def _build_execution_strategy_class(momentum_definition: str):
    if momentum_definition == "90d":
        return UniversalMultiFactor

    class ResearchExecutionStrategy(UniversalMultiFactor):
        def _score_visible_universe(self) -> pd.DataFrame:
            return score_research_universe(
                self._collect_visible_history(),
                top_n=self.p.top_n,
                weight_mom=self.p.weight_mom,
                weight_vol=self.p.weight_vol,
                weight_rev=self.p.weight_rev,
                momentum_definition=momentum_definition,
            )

    return ResearchExecutionStrategy


def evaluate_weight_tuple(
    data_dfs: dict[str, pd.DataFrame],
    start: str,
    end: str,
    weights: tuple[float, float, float],
    momentum_definition: str = "90d",
    evaluation_start: str | None = None,
    evaluation_end: str | None = None,
    reversal_filter_params=None,
    engine="backtrader",
    book_values: BookValuesInput = None,
    roe_values: dict[str, float | None] | None = None,
    top_n: int = 3,
) -> dict[str, float]:
    if momentum_definition not in SUPPORTED_MOMENTUM_DEFINITIONS:
        raise ValueError(f"Unsupported momentum_definition: {momentum_definition}")
    eval_start = evaluation_start or start
    eval_end = evaluation_end or end

    w_val = weights[3] if len(weights) > 3 else 0.0
    w_qual = weights[4] if len(weights) > 4 else 0.0
    score_book_values = _resolve_book_values(book_values, eval_end)

    warmup_bars = max(DEFAULT_LOOKBACK_MOM, DEFAULT_LOOKBACK_VOL, DEFAULT_LOOKBACK_REV)
    window_dfs = _slice_window_data(data_dfs, start, end, warmup_bars=warmup_bars)
    if not window_dfs:
        empty_scores = score_universe(
            {},
            weight_mom=weights[0],
            weight_vol=weights[1],
            weight_rev=weights[2],
            weight_val=w_val, weight_qual=w_qual, roe_values=roe_values,
            top_n=top_n,
        )
        return {
            "return_pct": 0.0,
            "sharpe": 0.0,
            "drawdown": 0.0,
            "scores": empty_scores,
        }

    if momentum_definition == "12_1":
        scores = score_research_universe(
            window_dfs,
            top_n=top_n,
            weight_mom=weights[0],
            weight_vol=weights[1],
            weight_rev=weights[2],
            weight_val=w_val, weight_qual=w_qual, roe_values=roe_values,
            momentum_definition=momentum_definition,
            book_values=score_book_values,
        )
    else:
        scores = score_universe(
            window_dfs,
            top_n=top_n,
            weight_mom=weights[0],
            weight_vol=weights[1],
            weight_rev=weights[2],
            weight_val=w_val, weight_qual=w_qual, roe_values=roe_values,
            book_values=score_book_values,
        )

    if reversal_filter_params is not None:
        from src.research.reversal_filter import apply_reversal_filter
        result = apply_reversal_filter(scores, window_dfs, reversal_filter_params)
        scores = result["filtered_scores"]

    if engine == "simple":
        from src.engine.simple_runner import run_backtest_simple
        return run_backtest_simple(
            data_dfs=data_dfs, start=start, end=end,
            weights=weights, top_n=top_n,
            momentum_definition=momentum_definition,
            reversal_filter_params=reversal_filter_params,
            evaluation_start=eval_start, evaluation_end=eval_end,
            book_values=book_values, roe_values=roe_values,
        )

    if engine == "vectorbt":
        from src.engine.vectorbt_runner import run_backtest_vectorbt
        return run_backtest_vectorbt(
            data_dfs=window_dfs,
            start=start,
            end=end,
            weights=weights,
            top_n=top_n,
            initial_cash=STARTING_CASH,
            commission_rate=0.001,
            slippage_pct=0.0,
            momentum_definition=momentum_definition,
            reversal_filter_params=reversal_filter_params,
            evaluation_start=eval_start,
            evaluation_end=eval_end,
        )

    strategy_class = _build_execution_strategy_class(momentum_definition)
    suppress_output(strategy_class)

    strategy_kwargs: dict = {
        "weight_mom": weights[0],
        "weight_vol": weights[1],
        "weight_rev": weights[2],
        "top_n": top_n,
    }
    if reversal_filter_params is not None:
        strategy_kwargs["reversal_filter_params"] = reversal_filter_params

    cerebro = bt.Cerebro()
    cerebro.addstrategy(
        strategy_class,
        **_filter_strategy_kwargs(strategy_class, strategy_kwargs),
    )

    for symbol, df in window_dfs.items():
        cerebro.adddata(bt.feeds.PandasData(dataname=df), name=symbol)

    cerebro.broker.setcash(STARTING_CASH)
    cerebro.broker.addcommissioninfo(JapanStockCommission())
    cerebro.broker.set_coc(True)
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(
        WindowReturnAnalyzer,
        _name="window_return",
        evaluation_start=eval_start,
        evaluation_end=eval_end,
    )
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Days,
                        riskfreerate=0.0,
                        annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(SymbolReturnAnalyzer, _name="symbol_returns")

    strategy = cerebro.run(runonce=False, preload=True)[0]
    window_return = strategy.analyzers.window_return.get_analysis()
    sharpe = strategy.analyzers.sharpe.get_analysis().get("sharperatio")
    drawdown = strategy.analyzers.drawdown.get_analysis().get("max", {}).get("drawdown", 0.0)
    symbol_returns = strategy.analyzers.symbol_returns.get_analysis().get("symbol_returns", [])

    # Use WindowReturnAnalyzer (simple return percentage) in all cases.
    # Do NOT use bt.analyzers.Returns which returns the natural log of the
    # return ratio (rtot = ln(V_end/V_start)), not the simple return.
    return_pct = float(window_return.get("return_pct", 0.0))

    return {
        "return_pct": return_pct,
        "sharpe": round(sharpe if sharpe is not None else 0.0, 4),
        "drawdown": round(drawdown, 4),
        "symbol_returns": symbol_returns,
        "scores": scores,
    }


def evaluate_benchmark_return(
    benchmark_df: pd.DataFrame,
    start: str,
    end: str,
) -> dict[str, float]:
    window_df = benchmark_df.loc[start:end]
    if window_df.empty or "Close" not in window_df.columns or len(window_df) < 2:
        return {"return_pct": 0.0}

    start_price = float(window_df["Close"].iloc[0])
    end_price = float(window_df["Close"].iloc[-1])
    if start_price <= 0.0:
        return {"return_pct": 0.0}

    return {"return_pct": round(((end_price / start_price) - 1.0) * 100, 4)}


def _format_contributor_summary(contributors: list[dict[str, object]]) -> str:
    if not contributors:
        return "n/a"
    return ", ".join(
        f"{item['symbol']} ({float(item['return_pct']):.4f}%)"
        for item in contributors
    )


def run_walk_forward_optimization(
    data_dfs: dict[str, pd.DataFrame] | None,
    start: str,
    end: str,
    train_months: int = 12,
    validation_months: int = 3,
    step_months: int = 3,
    artifact_dir: Path | None = DEFAULT_ARTIFACT_DIR,
    benchmark_data_dfs: dict[str, pd.DataFrame] | None = None,
    universe_name: str | None = None,
    universe_symbols: list[str] | None = None,
    momentum_definition: str = "90d",
    local_store_root: Path | str | None = None,
    local_warmup_bars: int | None = None,
    local_allowed_validation_statuses: tuple[str, ...] = ("ok",),
    reversal_filter_params=None,
    engine="simple",
    book_values: BookValuesInput = None,
    optimizer: str = "grid",
    n_factors: int = 4,
    top_n: int = 3,
) -> dict[str, object]:
    if momentum_definition not in SUPPORTED_MOMENTUM_DEFINITIONS:
        raise ValueError(f"Unsupported momentum_definition: {momentum_definition}")

    benchmark_evaluators = None
    if benchmark_data_dfs:
        benchmark_evaluators = {
            benchmark_name: (
                lambda window, benchmark_df=benchmark_df: evaluate_benchmark_return(
                    benchmark_df,
                    window["validation_start"],
                    window["validation_end"],
                )
        )
            for benchmark_name, benchmark_df in benchmark_data_dfs.items()
        }

    def _resolve_default_warmup_bars() -> int:
        if momentum_definition == "12_1":
            # 252 lookback + 21 skip, with a small buffer for indicator edges.
            return 252 + 21 + 5

        params = getattr(UniversalMultiFactor, "params", None)
        lookbacks = []
        for field in ("lookback_mom", "lookback_vol", "lookback_rev"):
            value = getattr(params, field, None)
            if value is None:
                continue
            try:
                lookbacks.append(int(value))
            except (TypeError, ValueError):
                continue
        warmup = max(lookbacks) if lookbacks else 0
        if warmup <= 0:
            warmup = 90
        # Small buffer to cover indicator edge cases.
        return warmup + 5

    def _load_local_window(
        symbols: list[str],
        window_start: str,
        window_end: str,
    ) -> tuple[dict[str, pd.DataFrame], str]:
        loaded = local_store.load_local_universe(
            symbols,
            window_start,
            window_end,
            warmup=local_warmup_bars if local_warmup_bars is not None else _resolve_default_warmup_bars(),
            strict_warmup=True,
            allowed_validation_statuses=local_allowed_validation_statuses,
            root=local_store_root,
        )
        prepared = {
            symbol: _prepare_price_frame_for_backtrader(df)
            for symbol, df in loaded.items()
        }
        if not prepared:
            raise ValueError("local universe load returned no frames")
        earliest = min(
            pd.Timestamp(df.index.min())
            for df in prepared.values()
            if not df.empty
        )
        slice_start = earliest.strftime("%Y-%m-%d")
        return prepared, slice_start

    if data_dfs is None:
        if universe_symbols is None:
            raise ValueError("universe_symbols is required when data_dfs is None")

        def evaluate_training_window(window, weights):
            window_dfs, slice_start = _load_local_window(
                universe_symbols,
                window["train_start"],
                window["train_end"],
            )
            return _call_evaluate_weight_tuple(
                window_dfs,
                slice_start,
                window["train_end"],
                weights,
                momentum_definition=momentum_definition,
                evaluation_start=window["train_start"],
                evaluation_end=window["train_end"],
                reversal_filter_params=reversal_filter_params,
                engine=engine,
                book_values=book_values,
                top_n=top_n,
            )

        def evaluate_validation_window(window, weights):
            window_dfs, slice_start = _load_local_window(
                universe_symbols,
                window["validation_start"],
                window["validation_end"],
            )
            metrics = _call_evaluate_weight_tuple(
                window_dfs,
                slice_start,
                window["validation_end"],
                weights,
                momentum_definition=momentum_definition,
                evaluation_start=window["validation_start"],
                evaluation_end=window["validation_end"],
                reversal_filter_params=reversal_filter_params,
                engine=engine,
                book_values=book_values,
                top_n=top_n,
            )
            metrics = metrics | _build_validation_participation_metrics(
                data_dfs=window_dfs,
                universe_symbols=universe_symbols,
                validation_start=window["validation_start"],
                validation_end=window["validation_end"],
            )
            return metrics

        def evaluate_baseline_window(window):
            window_dfs, slice_start = _load_local_window(
                universe_symbols,
                window["validation_start"],
                window["validation_end"],
            )
            return _call_evaluate_weight_tuple(
                window_dfs,
                slice_start,
                window["validation_end"],
                DEFAULT_BASELINE_WEIGHTS,
                momentum_definition=momentum_definition,
                evaluation_start=window["validation_start"],
                evaluation_end=window["validation_end"],
                reversal_filter_params=reversal_filter_params,
                engine=engine,
                book_values=book_values,
                top_n=top_n,
            )

        def evaluate_one_shot_training_window(weights):
            window_dfs, slice_start = _load_local_window(universe_symbols, start, end)
            return _call_evaluate_weight_tuple(
                window_dfs,
                slice_start,
                end,
                weights,
                momentum_definition=momentum_definition,
                evaluation_start=start,
                evaluation_end=end,
                reversal_filter_params=reversal_filter_params,
                engine=engine,
                book_values=book_values,
                top_n=top_n,
            )

        def evaluate_one_shot_validation_window(window, weights):
            window_dfs, slice_start = _load_local_window(
                universe_symbols,
                window["validation_start"],
                window["validation_end"],
            )
            return _call_evaluate_weight_tuple(
                window_dfs,
                slice_start,
                window["validation_end"],
                weights,
                momentum_definition=momentum_definition,
                evaluation_start=window["validation_start"],
                evaluation_end=window["validation_end"],
                reversal_filter_params=reversal_filter_params,
                engine=engine,
                book_values=book_values,
                top_n=top_n,
            )

    else:
        def evaluate_training_window(window, weights):
            return _evaluate_weight_tuple_with_momentum(
                data_dfs,
                window["train_start"],
                window["train_end"],
                weights,
                momentum_definition,
                reversal_filter_params=reversal_filter_params,
                book_values=book_values,
                engine=engine,
                top_n=top_n,
            )

        def evaluate_validation_window(window, weights):
            return _evaluate_weight_tuple_with_momentum(
                data_dfs,
                window["validation_start"],
                window["validation_end"],
                weights,
                momentum_definition,
                reversal_filter_params=reversal_filter_params,
                book_values=book_values,
                engine=engine,
                top_n=top_n,
            ) | _build_validation_participation_metrics(
                data_dfs=data_dfs,
                universe_symbols=universe_symbols,
                validation_start=window["validation_start"],
                validation_end=window["validation_end"],
            )

        def evaluate_baseline_window(window):
            return _evaluate_weight_tuple_with_momentum(
                data_dfs,
                window["validation_start"],
                window["validation_end"],
                DEFAULT_BASELINE_WEIGHTS,
                momentum_definition,
                reversal_filter_params=reversal_filter_params,
                book_values=book_values,
                engine=engine,
                top_n=top_n,
            )

        def evaluate_one_shot_training_window(weights):
            return _evaluate_weight_tuple_with_momentum(
                data_dfs,
                start,
                end,
                weights,
                momentum_definition,
                reversal_filter_params=reversal_filter_params,
                book_values=book_values,
                engine=engine,
                top_n=top_n,
            )

        def evaluate_one_shot_validation_window(window, weights):
            return _evaluate_weight_tuple_with_momentum(
                data_dfs,
                window["validation_start"],
                window["validation_end"],
                weights,
                momentum_definition,
                reversal_filter_params=reversal_filter_params,
                book_values=book_values,
                engine=engine,
                top_n=top_n,
            )

    result = run_walk_forward_experiment(
        start=start,
        end=end,
        train_months=train_months,
        validation_months=validation_months,
        step_months=step_months,
        weight_grid=DEFAULT_WEIGHT_GRID if optimizer == "grid" else None,
        evaluate_training_window=evaluate_training_window,
        evaluate_validation_window=evaluate_validation_window,
        evaluate_baseline_window=evaluate_baseline_window,
        evaluate_one_shot_training_window=evaluate_one_shot_training_window,
        evaluate_one_shot_validation_window=evaluate_one_shot_validation_window,
        evaluate_benchmark_windows=benchmark_evaluators,
        artifact_dir=None,
        momentum_definition=momentum_definition,
        optimizer=optimizer,
        n_factors=n_factors,
    )

    weights = result["weights"]
    summary = result["summary"]
    metadata = build_walk_forward_metadata(
        result.get("metadata", {}),
        universe_name=universe_name,
        universe_symbols=universe_symbols
        if universe_symbols is not None
        else list(data_dfs.keys()) if data_dfs is not None else [],
    )
    result["metadata"] = metadata

    if artifact_dir is not None:
        result["artifacts"] = write_walk_forward_run(
            base_dir=Path(artifact_dir),
            metadata=metadata,
            weights=weights,
            summary=summary,
        )

    print("=" * 60)
    print("WALK-FORWARD OPTIMIZATION SUMMARY")
    print("=" * 60)
    print(weights.to_string(index=False))
    print()
    print(f"Windows evaluated               : {summary['window_count']}")
    print(f"Static baseline return total % : {summary['baseline_return_pct']:.4f}")
    if "one_shot_return_pct" in summary:
        print(f"One-shot optimized return total % : {summary['one_shot_return_pct']:.4f}")
    if "topx_return_pct" in summary:
        print(f"TOPX benchmark return total % : {summary['topx_return_pct']:.4f}")
        print(f"Walk-forward excess vs TOPX % : {summary['walk_forward_excess_vs_topx_pct']:.4f}")
    if "n225_return_pct" in summary:
        print(f"N225 benchmark return total % : {summary['n225_return_pct']:.4f}")
        print(f"Walk-forward excess vs N225 % : {summary['walk_forward_excess_vs_n225_pct']:.4f}")
    print(f"Walk-forward return total %    : {summary['walk_forward_return_pct']:.4f}")
    if "avg_hit_rate" in summary and summary["avg_hit_rate"] is not None:
        print(f"Average window hit rate        : {summary['avg_hit_rate']:.4f}")
    if "avg_loaded_symbol_count" in summary:
        print(f"Average loaded symbols         : {summary['avg_loaded_symbol_count']:.4f}")
    if "avg_skipped_symbol_count" in summary:
        print(f"Average skipped symbols        : {summary['avg_skipped_symbol_count']:.4f}")
    if "avg_coverage_ratio" in summary:
        print(f"Average coverage ratio         : {summary['avg_coverage_ratio']:.4f}")
    if "min_coverage_ratio" in summary:
        print(f"Minimum coverage ratio         : {summary['min_coverage_ratio']:.4f}")
    if "top_contributors" in summary:
        print(f"Top contributors              : {_format_contributor_summary(summary['top_contributors'])}")
    if "bottom_contributors" in summary:
        print(f"Bottom contributors           : {_format_contributor_summary(summary['bottom_contributors'])}")
    if "artifacts" in result:
        print(f"Artifacts written to           : {result['artifacts']['run_dir']}")

    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run walk-forward optimization research")
    parser.add_argument("--start", default=DEFAULT_OPTIMIZE_START, help="Research start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=DEFAULT_OPTIMIZE_END, help="Research end date (YYYY-MM-DD)")
    parser.add_argument(
        "--universe-name",
        default=None,
        help="Named universe from src.data.universe to load (defaults to Topix-10)",
    )
    parser.add_argument(
        "--use-local-store",
        action="store_true",
        help="Load data from validated local research store instead of fetching from network/cache",
    )
    parser.add_argument(
        "--local-store-root",
        type=Path,
        default=None,
        help="Root directory for the local research store (defaults to current directory)",
    )
    parser.add_argument(
        "--local-warmup-bars",
        type=int,
        default=None,
        help="Warmup bar count to load before each window start when using --use-local-store",
    )
    parser.add_argument(
        "--momentum-definition",
        choices=sorted(SUPPORTED_MOMENTUM_DEFINITIONS),
        default="90d",
        help="Research-only momentum definition for walk-forward optimization",
    )
    parser.add_argument("--train-months", type=int, default=DEFAULT_TRAIN_MONTHS, help="Training window length in months")
    parser.add_argument(
        "--validation-months",
        type=int,
        default=DEFAULT_VALIDATION_MONTHS,
        help="Validation window length in months",
    )
    parser.add_argument("--step-months", type=int, default=DEFAULT_STEP_MONTHS, help="Walk-forward step size in months")
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR, help="Artifact output directory")
    parser.add_argument(
        "--reversal-filter",
        action="store_true",
        help="Enable reversal filter with default params (lookback=20, threshold=0.10)",
    )
    parser.add_argument(
        "--reversal-lookback",
        type=int,
        default=20,
        help="Reversal filter lookback days (default: 20)",
    )
    parser.add_argument(
        "--reversal-threshold",
        type=float,
        default=0.10,
        help="Reversal filter drawdown threshold (default: 0.10)",
    )
    parser.add_argument("--engine", choices=["simple", "backtrader", "vectorbt"], default="simple",
                        help="Backtesting engine")
    parser.add_argument("--fast", action="store_true",
                        help="Alias for --engine vectorbt")
    parser.add_argument("--optimizer", choices=["grid", "optuna"], default="grid",
                        help="Weight optimization method (default: grid)")
    parser.add_argument("--optuna-trials", type=int, default=50,
                        help="Number of Optuna trials per window (default: 50)")
    parser.add_argument("--top-n", type=int, default=3,
                        help="Number of stocks to hold in each rebalance (default: 3)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv if argv is not None else [])
    if args.universe_name:
        try:
            symbols = get_universe(args.universe_name)
        except KeyError:
            print(format_unknown_universe_message(args.universe_name))
            return 1
        universe_name = args.universe_name
    else:
        symbols = get_topix_top_10()
        universe_name = "topix_top_10"
    data_dfs = None
    benchmark_data_dfs: dict[str, pd.DataFrame] = {}

    if args.use_local_store:
        print(
            "Loading validated local data for walk-forward optimization "
            f"({args.start} -> {args.end})..."
        )
    else:
        print(
            "Fetching historical data for walk-forward optimization "
            f"({args.start} -> {args.end})..."
        )

        try:
            data_dfs = fetch_universe(symbols, args.start, args.end)
        except Exception as exc:
            print(f"Data fetch failed: {exc}")
            return 1

        try:
            benchmark_data_dfs = fetch_universe(list(DEFAULT_BENCHMARK_SYMBOLS.values()), args.start, args.end)
        except Exception as exc:
            print(f"Benchmark data fetch skipped: {exc}")

    reversal_filter_params = None
    if args.reversal_filter:
        from src.research.reversal_filter import ReversalFilterParams
        reversal_filter_params = ReversalFilterParams(
            lookback_days=args.reversal_lookback,
            threshold=args.reversal_threshold,
        )

    engine = "vectorbt" if args.fast else args.engine

    # Fetch book values for value factor (semi-static annual data)
    from src.data.fundamental_loader import get_book_values
    book_value_cache: dict[str, dict[str, float | None]] = {}

    def book_values(as_of_date: pd.Timestamp) -> dict[str, float | None]:
        key = pd.Timestamp(as_of_date).strftime("%Y-%m-%d")
        if key not in book_value_cache:
            book_value_cache[key] = get_book_values(symbols, as_of_date=pd.Timestamp(key))
        return book_value_cache[key]

    try:
        run_walk_forward_optimization(
            data_dfs=data_dfs,
            start=args.start,
            end=args.end,
            train_months=args.train_months,
            validation_months=args.validation_months,
            step_months=args.step_months,
            artifact_dir=args.artifact_dir,
            universe_name=universe_name,
            universe_symbols=symbols,
            benchmark_data_dfs={
                benchmark_name: benchmark_data_dfs[symbol]
                for benchmark_name, symbol in DEFAULT_BENCHMARK_SYMBOLS.items()
                if symbol in benchmark_data_dfs
            },
            momentum_definition=args.momentum_definition,
            local_store_root=args.local_store_root,
            local_warmup_bars=args.local_warmup_bars,
            reversal_filter_params=reversal_filter_params,
            engine=engine,
            book_values=book_values,
            optimizer=args.optimizer,
            n_factors=4,
            top_n=args.top_n,
        )
    except local_store.LocalDataSyncRequiredError as exc:
        print(f"Local data sync required: {exc}")
        print(
            "Sync local data via: "
            f"python -m src.main --sync-local --universe-name {universe_name} "
            f"--start {args.start} --end {args.end} "
            f"--local-store-root {args.local_store_root or '.'}"
        )
        return 1
    except Exception as exc:
        print(f"Walk-forward optimization failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
