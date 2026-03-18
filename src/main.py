import argparse
import sys
from src.data.yfinance_loader import fetch_daily_data
from src.strategies.sma_crossover import SmaCross
from src.engine.runner import run_backtest

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

    print("Running backtest using SmaCross strategy with friction modeling...")
    results = run_backtest(data_df, SmaCross, initial_cash=1000000.0)
    
    metrics = results["metrics"]
    cerebro = results["cerebro"]

    print("\n" + "="*40)
    print("BACKTEST RESULTS")
    print("="*40)
    print(f"Initial Capital : ¥1,000,000.00")
    print(f"Final Capital   : ¥{metrics['final_value']:,.2f}")
    # Backtrader 'rtot' return from analyzer is already compounded relative return, typically given as log return or simple return depending on mode.
    # However we compute simple total return ourselves here directly to be safe:
    simple_return = (metrics['final_value'] - 1000000.0) / 1000000.0 * 100
    print(f"Total Return    : {simple_return:.2f}%")
    print(f"Max Drawdown    : {metrics['max_drawdown']:.2f}%")
    sharpe_val = metrics['sharpe'] if metrics['sharpe'] is not None else 0.0
    print(f"Sharpe Ratio    : {sharpe_val:.4f}")
    print("="*40 + "\n")

    if not args.no_plot:
        print("Rendering chart... (Close the chart window to exit the program)")
        cerebro.plot(style='bar')

if __name__ == "__main__":
    main()
