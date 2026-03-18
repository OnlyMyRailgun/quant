import argparse
import sys
import backtrader as bt
from src.data.yfinance_loader import fetch_daily_data
from src.strategies.sma_crossover import SmaCross
from src.engine.commission import JapanStockCommission


class _LoggingWrapper(bt.Strategy):
    """Internal strategy wrapper that adds trade-by-trade logging to any strategy."""
    params = dict(
        base_strategy=None,
        pfast=10,
        pslow=30,
        stake=0.95,
    )

    def __init__(self):
        self._inner = SmaCross(pfast=self.p.pfast, pslow=self.p.pslow, stake=self.p.stake)
        self.trade_count = 0

    def notify_order(self, order):
        if order.status == order.Completed:
            action = 'BUY ' if order.isbuy() else 'SELL'
            print(
                f"  [{self.data.datetime.date(0)}] {action}"
                f"  price=¥{order.executed.price:,.2f}"
                f"  size={int(abs(order.executed.size))}"
                f"  value=¥{order.executed.value:,.2f}"
                f"  commission=¥{order.executed.comm:,.2f}"
            )

    def notify_trade(self, trade):
        if trade.isclosed:
            self.trade_count += 1
            result = "✅" if trade.pnlcomm >= 0 else "❌"
            print(
                f"  {result} TRADE #{self.trade_count} CLOSED"
                f"  gross=¥{trade.pnl:,.2f}"
                f"  net (after fees)=¥{trade.pnlcomm:,.2f}"
            )

    def next(self):
        pass  # Logic is in the inner SmaCross (shared indicators on same data)


def run_with_logging(data_df, initial_cash=1_000_000.0):
    """Run a SmaCross backtest with per-trade console logging."""
    cerebro = bt.Cerebro()
    cerebro.addstrategy(SmaCross)
    cerebro.adddata(bt.feeds.PandasData(dataname=data_df))
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.addcommissioninfo(JapanStockCommission())
    cerebro.broker.set_slippage_perc(0.0005)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')

    # Monkey-patch notify_order/trade onto the strategy class for this run
    original_next = SmaCross.next

    orders_log = []
    trades_log = []
    trade_count = [0]

    def notify_order(self, order):
        if order.status == order.Completed:
            action = 'BUY ' if order.isbuy() else 'SELL'
            msg = (
                f"  [{self.data.datetime.date(0)}] {action}"
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
            msg = (
                f"  {result} TRADE #{trade_count[0]} CLOSED"
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
    parser.add_argument("--ticker", type=str, default="7203.T", help="Ticker symbol (default: Toyota 7203.T)")
    parser.add_argument("--start", type=str, default="2023-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2024-01-01", help="End date (YYYY-MM-DD)")
    parser.add_argument("--no-plot", action="store_true", help="Disable plotting (useful for CI)")

    args = parser.parse_args()

    print(f"Fetching data for {args.ticker} from {args.start} to {args.end}...")
    try:
        data_df = fetch_daily_data(args.ticker, args.start, args.end)
        if data_df.empty:
            print("Error: No data fetched. Please check the ticker or date range.")
            sys.exit(1)
    except Exception as e:
        print(f"Failed to fetch data: {e}")
        sys.exit(1)

    print("Running backtest using SmaCross strategy with friction modeling...\n")
    print("=" * 50)
    print("ORDER & TRADE LOG")
    print("=" * 50)

    metrics, cerebro = run_with_logging(data_df, initial_cash=1_000_000.0)

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
