from __future__ import annotations

import argparse
import sys
from itertools import product
from pathlib import Path

import backtrader as bt
import pandas as pd

from src.data.bulk_loader import fetch_universe
from src.data.universe import (
    format_unknown_universe_message,
    get_topix_top_10,
    get_universe,
)
from src.engine.commission import JapanStockCommission
from src.research.artifacts import DEFAULT_ARTIFACT_DIR, build_walk_forward_metadata, write_walk_forward_run
from src.research.walk_forward import run_walk_forward_experiment
from src.strategies.multi_factor import UniversalMultiFactor


STARTING_CASH = 1_000_000.0
DEFAULT_BASELINE_WEIGHTS = (1.0, 1.0, 1.0)
DEFAULT_WEIGHT_GRID = list(product((0.0, 0.5, 1.0), repeat=3))
DEFAULT_OPTIMIZE_START = "2021-01-01"
DEFAULT_OPTIMIZE_END = "2024-01-01"
DEFAULT_TRAIN_MONTHS = 12
DEFAULT_VALIDATION_MONTHS = 6
DEFAULT_STEP_MONTHS = 6
DEFAULT_BENCHMARK_SYMBOLS = {
    "topx": "1306.T",
    "n225": "1321.T",
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


def suppress_output(strategy_class):
    """Temporarily suppress noisy strategy callbacks during optimization."""
    strategy_class.notify_order = lambda self, order: None
    strategy_class.notify_trade = lambda self, trade: None


def _slice_window_data(
    data_dfs: dict[str, pd.DataFrame],
    start: str,
    end: str,
) -> dict[str, pd.DataFrame]:
    window_dfs: dict[str, pd.DataFrame] = {}
    for symbol, df in data_dfs.items():
        try:
            window_df = df.loc[start:end]
        except KeyError:
            continue

        if not window_df.empty:
            window_dfs[symbol] = window_df
    return window_dfs


def evaluate_weight_tuple(
    data_dfs: dict[str, pd.DataFrame],
    start: str,
    end: str,
    weights: tuple[float, float, float],
) -> dict[str, float]:
    window_dfs = _slice_window_data(data_dfs, start, end)
    if not window_dfs:
        return {"return_pct": 0.0, "sharpe": 0.0, "drawdown": 0.0}

    suppress_output(UniversalMultiFactor)

    cerebro = bt.Cerebro()
    cerebro.addstrategy(
        UniversalMultiFactor,
        weight_mom=weights[0],
        weight_vol=weights[1],
        weight_rev=weights[2],
    )

    for symbol, df in window_dfs.items():
        cerebro.adddata(bt.feeds.PandasData(dataname=df), name=symbol)

    cerebro.broker.setcash(STARTING_CASH)
    cerebro.broker.addcommissioninfo(JapanStockCommission())
    cerebro.broker.set_coc(True)
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(SymbolReturnAnalyzer, _name="symbol_returns")

    strategy = cerebro.run()[0]
    returns = strategy.analyzers.returns.get_analysis()
    sharpe = strategy.analyzers.sharpe.get_analysis().get("sharperatio")
    drawdown = strategy.analyzers.drawdown.get_analysis().get("max", {}).get("drawdown", 0.0)
    symbol_returns = strategy.analyzers.symbol_returns.get_analysis().get("symbol_returns", [])

    return {
        "return_pct": round(returns.get("rtot", 0.0) * 100, 4),
        "sharpe": round(sharpe if sharpe is not None else 0.0, 4),
        "drawdown": round(drawdown, 4),
        "symbol_returns": symbol_returns,
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
    data_dfs: dict[str, pd.DataFrame],
    start: str,
    end: str,
    train_months: int = 12,
    validation_months: int = 3,
    step_months: int = 3,
    artifact_dir: Path | None = DEFAULT_ARTIFACT_DIR,
    benchmark_data_dfs: dict[str, pd.DataFrame] | None = None,
    universe_name: str | None = None,
    universe_symbols: list[str] | None = None,
) -> dict[str, object]:
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

    result = run_walk_forward_experiment(
        start=start,
        end=end,
        train_months=train_months,
        validation_months=validation_months,
        step_months=step_months,
        weight_grid=DEFAULT_WEIGHT_GRID,
        evaluate_training_window=lambda window, weights: evaluate_weight_tuple(
            data_dfs,
            window["train_start"],
            window["train_end"],
            weights,
        ),
        evaluate_validation_window=lambda window, weights: evaluate_weight_tuple(
            data_dfs,
            window["validation_start"],
            window["validation_end"],
            weights,
        ),
        evaluate_baseline_window=lambda window: evaluate_weight_tuple(
            data_dfs,
            window["validation_start"],
            window["validation_end"],
            DEFAULT_BASELINE_WEIGHTS,
        ),
        evaluate_one_shot_training_window=lambda weights: evaluate_weight_tuple(
            data_dfs,
            start,
            end,
            weights,
        ),
        evaluate_one_shot_validation_window=lambda window, weights: evaluate_weight_tuple(
            data_dfs,
            window["validation_start"],
            window["validation_end"],
            weights,
        ),
        evaluate_benchmark_windows=benchmark_evaluators,
        artifact_dir=None,
    )

    weights = result["weights"]
    summary = result["summary"]
    metadata = build_walk_forward_metadata(
        result.get("metadata", {}),
        universe_name=universe_name,
        universe_symbols=universe_symbols if universe_symbols is not None else list(data_dfs.keys()),
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
    parser.add_argument("--train-months", type=int, default=DEFAULT_TRAIN_MONTHS, help="Training window length in months")
    parser.add_argument(
        "--validation-months",
        type=int,
        default=DEFAULT_VALIDATION_MONTHS,
        help="Validation window length in months",
    )
    parser.add_argument("--step-months", type=int, default=DEFAULT_STEP_MONTHS, help="Walk-forward step size in months")
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR, help="Artifact output directory")
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
    print(
        "Fetching historical data for walk-forward optimization "
        f"({args.start} -> {args.end})..."
    )

    try:
        data_dfs = fetch_universe(symbols, args.start, args.end)
    except Exception as exc:
        print(f"Data fetch failed: {exc}")
        return 1

    benchmark_data_dfs = {}
    try:
        benchmark_data_dfs = fetch_universe(list(DEFAULT_BENCHMARK_SYMBOLS.values()), args.start, args.end)
    except Exception as exc:
        print(f"Benchmark data fetch skipped: {exc}")

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
        )
    except Exception as exc:
        print(f"Walk-forward optimization failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
