import sys
import pandas as pd
import backtrader as bt
from src.data.bulk_loader import fetch_universe
from src.data.universe import get_topix_top_10
from src.strategies.multi_factor import UniversalMultiFactor
from src.engine.commission import JapanStockCommission

def suppress_output(strategy_class):
    """Temporarily suppresses noisy print statements from strategy during optimization."""
    strategy_class.notify_order = lambda self, order: None
    strategy_class.notify_trade = lambda self, trade: None

def run_is_oos_optimization(data_dfs, is_start, is_end, oos_start, oos_end):
    """
    Implements a strict In-Sample (IS) vs Out-Of-Sample (OOS) Overfitting Prevention Test.
    1. Grid searches across multiple weight combinations strictly on IS data.
    2. Selects the absolute best performing parameter set.
    3. Blinds tests that parameter set on OOS data (the 'future').
    """
    suppress_output(UniversalMultiFactor)

    # 1. SPLIT DATA INTO IN-SAMPLE AND OUT-OF-SAMPLE
    is_dfs = {}
    oos_dfs = {}
    for symbol, df in data_dfs.items():
        # Pandas loc slicing is inclusive
        try:
            is_df = df.loc[is_start:is_end]
            oos_df = df.loc[oos_start:oos_end]
            if not is_df.empty: is_dfs[symbol] = is_df
            if not oos_df.empty: oos_dfs[symbol] = oos_df
        except KeyError:
            pass # Ignore if dates don't perfectly align globally

    # ---------------------------------------------------------
    # PHASE 1: IN-SAMPLE OPTIMIZATION
    # ---------------------------------------------------------
    print("=" * 60)
    print(f"🧪 [PHASE 1] RUNNING IN-SAMPLE OPTIMIZATION ({is_start} to {is_end})")
    print("=" * 60)
    
    # maxcpus=1 disables multiprocessing because dynamically generating classes (Backtrader symbols with .T) fails to pickle in Python 3.13
    cerebro_is = bt.Cerebro(optreturn=False, maxcpus=1)
    
    # Configure parameter sweep grid (3 x 3 x 3 = 27 combinations)
    cerebro_is.optstrategy(
        UniversalMultiFactor,
        weight_mom=(0.0, 0.5, 1.0),
        weight_vol=(0.0, 0.5, 1.0),
        weight_rev=(0.0, 0.5, 1.0)
    )

    for symbol, df in is_dfs.items():
        cerebro_is.adddata(bt.feeds.PandasData(dataname=df), name=symbol)
        
    cerebro_is.broker.setcash(1_000_000.0)
    cerebro_is.broker.addcommissioninfo(JapanStockCommission())
    cerebro_is.broker.set_coc(True)
    cerebro_is.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro_is.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')

    print("Running 27 Parallel Backtests. This might take a moment...")
    results_is = cerebro_is.run()
    
    # Extract results
    leaderboard = []
    for run in results_is:
        strat = run[0]
        p = strat.params
        
        # Analyze performance
        ret_dict = strat.analyzers.returns.get_analysis()
        total_return = ret_dict.get('rtot', 0) * 100  # Convert to percentage
        
        sharpe = strat.analyzers.sharpe.get_analysis().get('sharperatio')
        sharpe = sharpe if sharpe is not None else 0.0

        leaderboard.append({
            'Mom': p.weight_mom,
            'Vol': p.weight_vol,
            'Rev': p.weight_rev,
            'IS Return %': round(total_return, 2),
            'IS Sharpe': round(sharpe, 4)
        })
        
    # Sort by highest return
    df_is = pd.DataFrame(leaderboard).sort_values(by='IS Return %', ascending=False)
    
    print("\n🏆 IN-SAMPLE LEADERBOARD (Top 10):")
    print(df_is.head(10).to_string(index=False))
    
    best_params = df_is.iloc[0]
    print(f"\n🎯 THE WINNER (IS): Mom={best_params['Mom']}, Vol={best_params['Vol']}, Rev={best_params['Rev']} ")
    print(f"   Generated a return of {best_params['IS Return %']}%")

    # ---------------------------------------------------------
    # PHASE 2: OUT-OF-SAMPLE VALIDATION
    # ---------------------------------------------------------
    print("\n" + "=" * 60)
    print(f"🔮 [PHASE 2] OUT-OF-SAMPLE BLIND TEST ({oos_start} to {oos_end})")
    print("=" * 60)

    # Use the absolute best parameters found on the past data
    cerebro_oos = bt.Cerebro()
    cerebro_oos.addstrategy(
        UniversalMultiFactor, 
        weight_mom=best_params['Mom'],
        weight_vol=best_params['Vol'],
        weight_rev=best_params['Rev']
    )
    
    for symbol, df in oos_dfs.items():
        cerebro_oos.adddata(bt.feeds.PandasData(dataname=df), name=symbol)
        
    cerebro_oos.broker.setcash(1_000_000.0)
    cerebro_oos.broker.addcommissioninfo(JapanStockCommission())
    cerebro_oos.broker.set_coc(True)
    cerebro_oos.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro_oos.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    
    strat_oos = cerebro_oos.run()[0]
    
    # OOS Metrics
    oos_ret_dict = strat_oos.analyzers.returns.get_analysis()
    oos_total_return = oos_ret_dict.get('rtot', 0) * 100
    oos_drawdown = strat_oos.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0.0)
    
    # Calculate simple Baseline Buy-and-Hold for comparison
    # We simulate an equal-weight baseline (1.0 / 1.0 / 1.0) on OOS just to show generic market performance
    cerebro_base = bt.Cerebro()
    cerebro_base.addstrategy(UniversalMultiFactor, weight_mom=1.0, weight_vol=1.0, weight_rev=1.0)
    for symbol, df in oos_dfs.items():
        cerebro_base.adddata(bt.feeds.PandasData(dataname=df), name=symbol)
    cerebro_base.broker.setcash(1_000_000.0)
    cerebro_base.broker.addcommissioninfo(JapanStockCommission())
    cerebro_base.broker.set_coc(True)
    cerebro_base.addanalyzer(bt.analyzers.Returns, _name='returns')
    base_strat = cerebro_base.run()[0]
    base_return = base_strat.analyzers.returns.get_analysis().get('rtot', 0) * 100
    
    print(f"OOS Baseline (Generic 1:1:1 weighting) Return: {base_return:.2f}%")
    print(f"OOS Optimized Parameter Return         : {oos_total_return:.2f}%")
    print(f"OOS Optimized Max Drawdown             : {oos_drawdown:.2f}%")
    
    if oos_total_return > base_return and oos_total_return > 0:
        print("\n✅ PASSED ANTI-OVERFITTING TEST: The parameters discovered in the past generalized successfully to the future!")
    elif oos_total_return > 0:
        print("\n⚠️ PARTIAL PASS: The strategy made money in the future, but actually underperformed a naive equal-weight guess. It may be slightly overfit to the past.")
    else:
        print("\n❌ FAILED (OVERFIT CONFIRMED): The parameters that ranked #1 in the past completely lost money in the future. The strategy memorized the training data instead of learning true alpha.")

if __name__ == "__main__":
    symbols = get_topix_top_10()
    # Fetch 3 years of data
    print("Fetching 3 years of historical data for the Universe...")
    try:
        # Full scope: 2021-01-01 to 2024-01-01
        data_dfs = fetch_universe(symbols, "2021-01-01", "2024-01-01")
    except Exception as e:
        print(f"Data fetch failed: {e}")
        sys.exit(1)
        
    # IS: 2021 to end of 2022. OOS: 2023 to end of 2023.
    run_is_oos_optimization(
        data_dfs, 
        is_start="2021-01-01", is_end="2022-12-31",
        oos_start="2023-01-01", oos_end="2023-12-31"
    )
