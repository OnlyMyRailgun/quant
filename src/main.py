import argparse
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
import sys
from typing import TextIO
import backtrader as bt
import pandas as pd
from src.data.bulk_loader import fetch_universe
from src.data import local_store
from src.data.universe import (
    format_unknown_universe_message,
    get_topix_top_10,
    get_universe,
)
from src.research.artifacts import (
    DEFAULT_ARTIFACT_DIR,
    build_screening_metadata,
    write_screening_run,
)
from src.strategies.sma_crossover import SmaCross
from src.strategies.momentum_factor import CrossSectionalMomentum
from src.strategies.multi_factor import UniversalMultiFactor
from src.engine.commission import JapanStockCommission
from src.engine.runner import run_backtest
from src.research.approved_params import resolve_approved_weight_values
from src.research.screening import ScreeningRules, screen_universe


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


def _filter_strategy_kwargs(strategy_class, kwargs: dict) -> dict:
    param_names = _strategy_param_names(strategy_class)
    if not param_names:
        return {}
    return {
        key: value
        for key, value in kwargs.items()
        if key in param_names
    }


def run_with_logging(data_dfs, strategy_class, kwargs_dict=None, initial_cash=1_000_000.0):
    """Run a backtest with per-trade console logging for multiple datasets."""
    cerebro = bt.Cerebro()
    if kwargs_dict is None:
        kwargs_dict = {}
        
    cerebro.addstrategy(strategy_class, **_filter_strategy_kwargs(strategy_class, kwargs_dict))
    
    for symbol, df in data_dfs.items():
        cerebro.adddata(bt.feeds.PandasData(dataname=df), name=symbol)
        
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.addcommissioninfo(JapanStockCommission())
    cerebro.broker.set_slippage_perc(0.0005)
    
    # Critical: Allow simultaneous execution of sell limits and buy limits for rebalancing
    cerebro.broker.set_coc(True) # Cheat-on-close so targets evaluate realistically
    
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')

    # Monkey-patch notify_order/trade onto the strategy class for this run
    original_notify_order = getattr(strategy_class, 'notify_order', None)
    original_notify_trade = getattr(strategy_class, 'notify_trade', None)
    
    orders_log = []
    trades_log = []
    trade_count = [0]

    def notify_order(self, order):
        if order.status == order.Completed:
            action = 'BUY ' if order.isbuy() else 'SELL'
            symbol = order.data._name if hasattr(order.data, '_name') else 'UNKNOWN'
            msg = (
                f"  [{self.data.datetime.date(0)}] {action} {symbol}"
                f"  price=¥{order.executed.price:,.2f}"
                f"  size={int(abs(order.executed.size))}"
                f"  value=¥{order.executed.value:,.2f}"
                f"  commission=¥{order.executed.comm:,.2f}"
            )
            orders_log.append(msg)
            print(msg)

    def notify_trade(self, trade):
        if trade.isclosed:
            trade_count[0] += 1
            result = "✅" if trade.pnlcomm >= 0 else "❌"
            symbol = trade.data._name if hasattr(trade.data, '_name') else 'UNKNOWN'
            msg = (
                f"  {result} TRADE #{trade_count[0]} CLOSED {symbol}"
                f"  gross=¥{trade.pnl:,.2f}"
                f"  net (after fees)=¥{trade.pnlcomm:,.2f}"
            )
            trades_log.append(msg)
            print(msg)

    strategy_class.notify_order = notify_order
    strategy_class.notify_trade = notify_trade

    strats = cerebro.run()
    strat = strats[0]

    # Restore original class (clean up monkey-patch)
    if original_notify_order:
        strategy_class.notify_order = original_notify_order
    else:
        del strategy_class.notify_order
        
    if original_notify_trade:
        strategy_class.notify_trade = original_notify_trade
    else:
        del strategy_class.notify_trade

    metrics = {
        "final_value": cerebro.broker.getvalue(),
        "sharpe": strat.analyzers.sharpe.get_analysis().get('sharperatio'),
        "max_drawdown": strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0.0),
    }
    return metrics, cerebro


def resolve_multi_factor_weights(
    artifact_dir,
    weight_mom,
    weight_vol,
    weight_rev,
):
    resolved = resolve_approved_weight_values(
        artifact_dir=artifact_dir,
        weight_mom=weight_mom,
        weight_vol=weight_vol,
        weight_rev=weight_rev,
        fallback=(1.0, 1.0, 1.0),
    )
    weights = {
        "weight_mom": resolved["mom"],
        "weight_vol": resolved["vol"],
        "weight_rev": resolved["rev"],
    }
    if "val" in resolved:
        weights["weight_val"] = resolved["val"]
    if "qual" in resolved:
        weights["weight_qual"] = resolved["qual"]
    return weights


def resolve_multi_factor_strategy_kwargs(
    artifact_dir,
    weight_mom,
    weight_vol,
    weight_rev,
    buy_rank_threshold=None,
    sell_rank_threshold=None,
    artifact_run_name=None,
    universe_name=None,
    reversal_filter_params=None,
):
    kwargs = resolve_multi_factor_weights(
        artifact_dir=artifact_dir,
        weight_mom=weight_mom,
        weight_vol=weight_vol,
        weight_rev=weight_rev,
    )
    if buy_rank_threshold is not None:
        kwargs["buy_rank_threshold"] = buy_rank_threshold
    if sell_rank_threshold is not None:
        kwargs["sell_rank_threshold"] = sell_rank_threshold
    if artifact_dir is not None:
        kwargs["artifact_dir"] = artifact_dir
    if artifact_run_name is not None:
        kwargs["artifact_run_name"] = artifact_run_name
    if universe_name is not None:
        kwargs["universe_name"] = universe_name
    if reversal_filter_params is not None:
        kwargs["reversal_filter_params"] = reversal_filter_params
    return kwargs


def render_backtest_results(
    metrics,
    initial_cash: float,
    strategy_name: str,
    output: TextIO = sys.stdout,
):
    print("\nBACKTEST RESULTS", file=output)
    print("=" * 40, file=output)
    print(f"Strategy        : {strategy_name}", file=output)
    print(f"Initial Capital : ¥{initial_cash:,.2f}", file=output)
    print(f"Final Capital   : ¥{metrics['final_value']:,.2f}", file=output)
    simple_return = (metrics["final_value"] - initial_cash) / initial_cash * 100
    print(f"Total Return    : {simple_return:.2f}%", file=output)
    print(f"Max Drawdown    : {metrics['max_drawdown']:.2f}%", file=output)
    sharpe_val = metrics["sharpe"] if metrics["sharpe"] is not None else 0.0
    print(f"Sharpe Ratio    : {sharpe_val:.4f}", file=output)
    if strategy_name == "UniversalMultiFactor":
        print(f"Rebalance Count : {metrics.get('rebalance_count', 0)}", file=output)
        print(f"Position Changes: {metrics.get('position_change_count', 0)}", file=output)
        print(f"Turnover Ratio  : {metrics.get('turnover_ratio', 0.0):.4f}", file=output)
    print("=" * 40 + "\n", file=output)


def sync_named_universe(
    universe_name: str,
    start_date: str,
    end_date: str,
    root: Path | str | None = None,
    fetcher: local_store.Fetcher | None = None,
) -> dict[str, local_store.ManifestRecord]:
    """Minimal entry point for syncing a named universe into the local research store."""
    symbols = get_universe(universe_name)
    return local_store.sync_universe_history(
        symbols,
        start_date,
        end_date,
        root=root,
        fetcher=fetcher,
    )


def _build_screening_decisions_frame(candidate_symbols, by_symbol):
    rows = []
    for symbol in candidate_symbols:
        record = by_symbol[symbol]
        rows.append(
            {
                "symbol": symbol,
                "eligible": record.get("eligible", False),
                "reasons": record.get("reasons", []),
                "metrics": record.get("metrics", {}),
            }
        )
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Run Quant Backtest and Plot Results")
    parser.add_argument(
        "--sync-local",
        action="store_true",
        help="Sync selected ticker/universe into the local research store and exit",
    )
    parser.add_argument(
        "--local-store-root",
        type=str,
        default=None,
        help="Root directory for the local research store (defaults to current directory)",
    )
    parser.add_argument("--ticker", type=str, default=None, help="Specific ticker symbol (e.g. 7203.T)")
    parser.add_argument("--universe", action="store_true", help="Run on the full Top 10 TOPIX Universe")
    parser.add_argument(
        "--universe-name",
        type=str,
        default=None,
        help="Run on a named universe from src.data.universe",
    )
    parser.add_argument("--strategy", type=str, choices=["sma", "momentum", "multi"], default="multi", help="Strategy to run")
    parser.add_argument("--weight-mom", type=float, default=None, help="Weight for Momentum Factor")
    parser.add_argument("--weight-vol", type=float, default=None, help="Weight for Low Volatility Factor")
    parser.add_argument("--weight-rev", type=float, default=None, help="Weight for Mean Reversion Factor")
    parser.add_argument("--buy-rank-threshold", type=int, default=None, help="Buy only when rank is at or above this threshold")
    parser.add_argument("--sell-rank-threshold", type=int, default=None, help="Keep holdings until rank falls below this threshold")
    parser.add_argument("--start", type=str, default="2023-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2024-01-01", help="End date (YYYY-MM-DD)")
    parser.add_argument("--no-plot", action="store_true", help="Disable plotting (useful for CI)")
    parser.add_argument("--engine", choices=["simple", "backtrader", "vectorbt"], default="simple")
    parser.add_argument("--fast", action="store_true", help="Alias for --engine vectorbt")
    parser.add_argument("--momentum-definition", choices=["90d", "12_1"], default="90d",
                        help="Momentum definition for backtest (default: 90d)")
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

    args = parser.parse_args()

    symbols = []
    selected_universe_name = None
    if args.ticker:
        symbols = [args.ticker]
    elif args.universe_name:
        try:
            symbols = get_universe(args.universe_name)
        except KeyError:
            print(format_unknown_universe_message(args.universe_name))
            sys.exit(1)
        selected_universe_name = args.universe_name
    elif args.universe:
        symbols = get_topix_top_10()
        selected_universe_name = "topix_top_10"
    else:
        # Default behavior limits output for testing
        symbols = ["7203.T", "6758.T", "8306.T"]

    if args.sync_local:
        local_store.sync_universe_history(
            symbols,
            args.start,
            args.end,
            root=args.local_store_root,
        )
        print(f"Synced {len(symbols)} symbols into local store at {args.local_store_root or '.'}.")
        return

    print(f"Fetching data for {len(symbols)} symbols from {args.start} to {args.end}...")
    try:
        data_dfs = fetch_universe(symbols, args.start, args.end)
        if not data_dfs:
            print("Error: No data fetched for any symbol.")
            sys.exit(1)
    except Exception as e:
        print(f"Failed to fetch data: {e}")
        sys.exit(1)

    strategy_map = {
        "sma": SmaCross,
        "momentum": CrossSectionalMomentum,
        "multi": UniversalMultiFactor
    }
    selected_strategy = strategy_map[args.strategy]
    
    reversal_filter_params = None
    if args.reversal_filter:
        from src.research.reversal_filter import ReversalFilterParams
        reversal_filter_params = ReversalFilterParams(
            lookback_days=args.reversal_lookback,
            threshold=args.reversal_threshold,
        )

    kwargs = {}
    if args.strategy == "multi":
        kwargs = resolve_multi_factor_strategy_kwargs(
            artifact_dir=DEFAULT_ARTIFACT_DIR,
            weight_mom=args.weight_mom,
            weight_vol=args.weight_vol,
            weight_rev=args.weight_rev,
            buy_rank_threshold=args.buy_rank_threshold,
            sell_rank_threshold=args.sell_rank_threshold,
            artifact_run_name="backtest_rebalance",
            universe_name=selected_universe_name,
            reversal_filter_params=reversal_filter_params,
        )

    if selected_universe_name is not None:
        screening_rules = ScreeningRules()
        screening_result = screen_universe(
            candidate_symbols=symbols,
            data_dfs=data_dfs,
            start=args.start,
            end=args.end,
            screen_as_of=args.end,
            screening_rules=screening_rules,
        )
        screening_summary = screening_result["summary"]
        print(
            "Screening summary: "
            f"requested={screening_summary['requested_symbol_count']} "
            f"eligible={screening_summary['eligible_symbol_count']} "
            f"screened_out={screening_summary['screened_out_symbol_count']}"
        )

        screening_metadata = build_screening_metadata(
            start=args.start,
            end=args.end,
            screen_as_of=args.end,
            universe_name=selected_universe_name,
            screening_rules=asdict(screening_rules),
        )
        write_screening_run(
            base_dir=DEFAULT_ARTIFACT_DIR,
            run_name="universe_screening",
            metadata=screening_metadata,
            decisions=_build_screening_decisions_frame(symbols, screening_result["by_symbol"]),
            summary=screening_summary,
        )

        eligible_symbols = screening_result["eligible_symbols"]
        if not eligible_symbols:
            print("No symbols remained after screening. Please choose a larger universe or relax the screening rules.")
            sys.exit(1)
        data_dfs = {symbol: data_dfs[symbol] for symbol in eligible_symbols if symbol in data_dfs}

    engine = "vectorbt" if args.fast else args.engine
    print(f"Running backtest using {selected_strategy.__name__} strategy with friction modeling...\n")

    if engine == "backtrader":
        print("=" * 50)
        print("ORDER & TRADE LOG")
        print("=" * 50)
        metrics, cerebro = run_with_logging(data_dfs, selected_strategy, kwargs_dict=kwargs, initial_cash=1_000_000.0)
    else:
        result = run_backtest(
            data_dfs,
            selected_strategy,
            initial_cash=1_000_000.0,
            engine=engine,
            momentum_definition=args.momentum_definition,
            reversal_filter_params=reversal_filter_params,
            start=args.start,
            end=args.end,
            strategy_kwargs=kwargs,
        )
        metrics = result["metrics"]
        cerebro = result["cerebro"]

    print("=" * 50)
    render_backtest_results(
        metrics=metrics,
        initial_cash=1_000_000.0,
        strategy_name=selected_strategy.__name__,
    )

    if not args.no_plot:
        print("Rendering chart... (Close the chart window to exit the program)")
        cerebro.plot(style='bar')


if __name__ == "__main__":
    main()
