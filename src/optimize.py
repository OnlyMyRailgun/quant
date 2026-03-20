from __future__ import annotations

import argparse
import sys
from itertools import product
from pathlib import Path

import backtrader as bt
import pandas as pd

from src.data.bulk_loader import fetch_universe
from src.data.universe import get_topix_top_10
from src.engine.commission import JapanStockCommission
from src.research.artifacts import DEFAULT_ARTIFACT_DIR
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

    strategy = cerebro.run()[0]
    returns = strategy.analyzers.returns.get_analysis()
    sharpe = strategy.analyzers.sharpe.get_analysis().get("sharperatio")
    drawdown = strategy.analyzers.drawdown.get_analysis().get("max", {}).get("drawdown", 0.0)

    return {
        "return_pct": round(returns.get("rtot", 0.0) * 100, 4),
        "sharpe": round(sharpe if sharpe is not None else 0.0, 4),
        "drawdown": round(drawdown, 4),
    }


def run_walk_forward_optimization(
    data_dfs: dict[str, pd.DataFrame],
    start: str,
    end: str,
    train_months: int = 12,
    validation_months: int = 3,
    step_months: int = 3,
    artifact_dir: Path | None = DEFAULT_ARTIFACT_DIR,
) -> dict[str, object]:
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
        artifact_dir=Path(artifact_dir) if artifact_dir is not None else None,
    )

    weights = result["weights"]
    summary = result["summary"]

    print("=" * 60)
    print("WALK-FORWARD OPTIMIZATION SUMMARY")
    print("=" * 60)
    print(weights.to_string(index=False))
    print()
    print(f"Windows evaluated               : {summary['window_count']}")
    print(f"Static baseline return total % : {summary['baseline_return_pct']:.4f}")
    if "one_shot_return_pct" in summary:
        print(f"One-shot optimized return total % : {summary['one_shot_return_pct']:.4f}")
    print(f"Walk-forward return total %    : {summary['walk_forward_return_pct']:.4f}")
    if "artifacts" in result:
        print(f"Artifacts written to           : {result['artifacts']['run_dir']}")

    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run walk-forward optimization research")
    parser.add_argument("--start", default=DEFAULT_OPTIMIZE_START, help="Research start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=DEFAULT_OPTIMIZE_END, help="Research end date (YYYY-MM-DD)")
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
    symbols = get_topix_top_10()
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
        run_walk_forward_optimization(
            data_dfs=data_dfs,
            start=args.start,
            end=args.end,
            train_months=args.train_months,
            validation_months=args.validation_months,
            step_months=args.step_months,
            artifact_dir=args.artifact_dir,
        )
    except Exception as exc:
        print(f"Walk-forward optimization failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
