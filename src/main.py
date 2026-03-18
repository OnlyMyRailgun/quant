import argparse
import sys
import backtrader as bt
from src.data.bulk_loader import fetch_universe
from src.data.universe import get_topix_top_10
from src.strategies.sma_crossover import SmaCross
from src.engine.commission import JapanStockCommission


def run_with_logging(data_dfs, initial_cash=1_000_000.0):
    """Run a SmaCross backtest with per-trade console logging for multiple datasets."""
    cerebro = bt.Cerebro()
    cerebro.addstrategy(SmaCross)
    
    for symbol, df in data_dfs.items():
        cerebro.adddata(bt.feeds.PandasData(dataname=df), name=symbol)
        
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.addcommissioninfo(JapanStockCommission())
    cerebro.broker.set_slippage_perc(0.0005)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')

    # Monkey-patch notify_order/trade onto the strategy class for this run
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

    SmaCross.notify_order = notify_order
    SmaCross.notify_trade = notify_trade

    strats = cerebro.run()
    strat = strats[0]

    # Restore original class (clean up monkey-patch)
    if hasattr(SmaCross, 'notify_order'):
        del SmaCross.notify_order
    if hasattr(SmaCross, 'notify_trade'):
        del SmaCross.notify_trade

    metrics = {
        "final_value": cerebro.broker.getvalue(),
        "sharpe": strat.analyzers.sharpe.get_analysis().get('sharperatio'),
        "max_drawdown": strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0.0),
    }
    return metrics, cerebro


def main():
    parser = argparse.ArgumentParser(description="Run Quant Backtest and Plot Results")
    parser.add_argument("--ticker", type=str, default=None, help="Specific ticker symbol (e.g. 7203.T)")
    parser.add_argument("--universe", action="store_true", help="Run on the full Top 10 TOPIX Universe")
    parser.add_argument("--start", type=str, default="2023-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2024-01-01", help="End date (YYYY-MM-DD)")
    parser.add_argument("--no-plot", action="store_true", help="Disable plotting (useful for CI)")

    args = parser.parse_args()

    symbols = []
    if args.universe:
        symbols = get_topix_top_10()
    elif args.ticker:
        symbols = [args.ticker]
    else:
        # Default behavior
        symbols = ["7203.T"]

    print(f"Fetching data for {len(symbols)} symbols from {args.start} to {args.end}...")
    try:
        data_dfs = fetch_universe(symbols, args.start, args.end)
        if not data_dfs:
            print("Error: No data fetched for any symbol.")
            sys.exit(1)
    except Exception as e:
        print(f"Failed to fetch data: {e}")
        sys.exit(1)

    print("Running backtest using SmaCross strategy with friction modeling...\n")
    print("=" * 50)
    print("ORDER & TRADE LOG")
    print("=" * 50)

    metrics, cerebro = run_with_logging(data_dfs, initial_cash=1_000_000.0)

    print("=" * 50)
    print("\nBACKTEST RESULTS")
    print("=" * 40)
    print(f"Initial Capital : ¥1,000,000.00")
    print(f"Final Capital   : ¥{metrics['final_value']:,.2f}")
    simple_return = (metrics['final_value'] - 1_000_000.0) / 1_000_000.0 * 100
    print(f"Total Return    : {simple_return:.2f}%")
    print(f"Max Drawdown    : {metrics['max_drawdown']:.2f}%")
    sharpe_val = metrics['sharpe'] if metrics['sharpe'] is not None else 0.0
    print(f"Sharpe Ratio    : {sharpe_val:.4f}")
    print("=" * 40 + "\n")

    if not args.no_plot:
        print("Rendering chart... (Close the chart window to exit the program)")
        cerebro.plot(style='bar')


if __name__ == "__main__":
    main()
