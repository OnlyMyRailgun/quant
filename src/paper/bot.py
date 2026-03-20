import sys
import argparse
from pathlib import Path
import pandas as pd
from datetime import datetime
from tabulate import tabulate

from src.research.artifacts import build_scoring_metadata, write_scoring_run
from src.scoring.multi_factor import (
    DEFAULT_LOOKBACK_MOM,
    DEFAULT_LOOKBACK_REV,
    DEFAULT_LOOKBACK_VOL,
    score_universe,
)
from src.paper.db import DB_PATH, get_wallet_balance, place_pending_order
from src.paper.notifier import send_daily_report
import sqlite3


def _build_signal_run(
    data_dfs,
    top_n=3,
    weight_mom=1.0,
    weight_vol=1.0,
    weight_rev=1.0,
    lookback_mom=DEFAULT_LOOKBACK_MOM,
    lookback_vol=DEFAULT_LOOKBACK_VOL,
    lookback_rev=DEFAULT_LOOKBACK_REV,
):
    ranked = score_universe(
        data_dfs,
        top_n=top_n,
        weight_mom=weight_mom,
        weight_vol=weight_vol,
        weight_rev=weight_rev,
        lookback_mom=lookback_mom,
        lookback_vol=lookback_vol,
        lookback_rev=lookback_rev,
    )
    return ranked


def _with_legacy_factor_aliases(ranked: pd.DataFrame) -> pd.DataFrame:
    winners = ranked.copy()
    winners["mom"] = winners["mom_raw"]
    winners["vol"] = winners["vol_raw"]
    winners["rev"] = winners["rev_raw"]
    return winners


def calculate_current_signals(
    data_dfs,
    top_n=3,
    weight_mom=1.0,
    weight_vol=1.0,
    weight_rev=1.0,
    lookback_mom=DEFAULT_LOOKBACK_MOM,
    lookback_vol=DEFAULT_LOOKBACK_VOL,
    lookback_rev=DEFAULT_LOOKBACK_REV,
    artifact_dir: Path | None = None,
):
    """
    Shared paper-trading scorer for generating today's live signals.

    This delegates to the same ranking logic used by the research layer so
    paper-trading recommendations stay aligned with backtests.
    """
    ranked = _build_signal_run(
        data_dfs,
        top_n=top_n,
        weight_mom=weight_mom,
        weight_vol=weight_vol,
        weight_rev=weight_rev,
        lookback_mom=lookback_mom,
        lookback_vol=lookback_vol,
        lookback_rev=lookback_rev,
    )

    if artifact_dir is not None:
        winners = ranked.head(top_n)
        metadata = build_scoring_metadata(
            scores=ranked,
            top_n=top_n,
            weights={"mom": weight_mom, "vol": weight_vol, "rev": weight_rev},
            lookbacks={
                "mom": lookback_mom,
                "vol": lookback_vol,
                "rev": lookback_rev,
            },
        )
        write_scoring_run(
            base_dir=Path(artifact_dir),
            run_name="paper_signal",
            metadata=metadata,
            scores=ranked,
            summary={"top_n": top_n, "winner_count": len(winners)},
        )

    return _with_legacy_factor_aliases(ranked.head(top_n))

def generate_rebalance_orders():
    from src.data.universe import get_topix_top_10
    from src.data.bulk_loader import fetch_universe

    print("Fetching latest data from Yahoo Finance for live signal generation...")
    symbols = get_topix_top_10()
    # Need at least 150 days to ensure enough history for our indicators
    start_date = (pd.Timestamp.today() - pd.Timedelta(days=200)).strftime("%Y-%m-%d")
    end_date = pd.Timestamp.today().strftime("%Y-%m-%d")
    
    dfs = fetch_universe(symbols, start_date, end_date)
    
    print("\nRunning UniversalMultiFactor Scoring Engine on Latest Close...")
    winners = calculate_current_signals(dfs, top_n=3)
    
    print("\n🏆 TODAY'S WINNING PORTFOLIO:")
    print(tabulate(winners[['symbol', 'price', 'total_score']], headers='keys', tablefmt='psql', showindex=False))
    
    wallet_cash = get_wallet_balance()
    
    # Read current portfolio
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT symbol, shares FROM portfolio')
    current_portfolio = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    
    print(f"\nEvaluating Rebalance Diff. Available Cash: ¥{wallet_cash:,.2f}")
    
    target_symbols = winners['symbol'].tolist()
    
    # 1. Determine SELL orders (what we hold but shouldn't)
    for sym, shares in current_portfolio.items():
        if sym not in target_symbols:
            price = dfs[sym]['Close'].iloc[-1]
            place_pending_order(sym, 'SELL', shares, theoretical_price=price)
            
    # 2. Determine BUY orders (allocating cash equally)
    # Note: A real system handles sell proceeds simultaneously.
    # For MVP we simply assume we divide current + theoretical proceeds equally.
    # To keep it safe, we just use the fixed theoretical target weight
    target_value_per_stock = wallet_cash * 0.95 / len(target_symbols)
    
    for _, row in winners.iterrows():
        sym = row['symbol']
        price = row['price']
        
        current_shares = current_portfolio.get(sym, 0)
        target_shares = int(target_value_per_stock / price)
        
        diff = target_shares - current_shares
        
        if diff > 0:
            place_pending_order(sym, 'BUY', diff, theoretical_price=price)
        elif diff < 0:
            place_pending_order(sym, 'SELL', abs(diff), theoretical_price=price)
            
    print("\n✅ Target orders staged in the paper trading database.")
    print("Run this script using 'fill <ORDER_ID> <YOUR_ACTUAL_EXECUTION_PRICE>' tomorrow after you trade them on your app!")

    # Send daily summary email
    conn2 = sqlite3.connect(DB_PATH)
    cur2 = conn2.cursor()
    cur2.execute("SELECT id, date, symbol, action, target_shares, theoretical_price FROM orders WHERE status='PENDING'")
    pending_orders = cur2.fetchall()
    cur2.execute('SELECT symbol, shares, avg_price FROM portfolio')
    full_portfolio = cur2.fetchall()
    conn2.close()

    winners_list = [
        {'symbol': row['symbol'], 'price': row['price'], 'score': row['total_score']}
        for _, row in winners.iterrows()
    ]
    send_daily_report(
        winners=winners_list,
        orders=pending_orders,
        cash=wallet_cash,
        portfolio=full_portfolio,
    )

def print_status():
    wallet_cash = get_wallet_balance()
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT symbol, shares, avg_price FROM portfolio')
    holdings = cur.fetchall()
    
    print("\n🏦 PAPER TRADER STATUS")
    print("="*40)
    print(f"💰 Available Cash: ¥{wallet_cash:,.2f}")
    
    print("\n📦 CURRENT HOLDINGS:")
    if holdings:
        headers = ["Symbol", "Shares", "Avg Avg Price (¥)"]
        print(tabulate(holdings, headers=headers, tablefmt='grid'))
    else:
        print("   (Empty Portfolio)")
    
    cur.execute("SELECT id, date, symbol, action, target_shares, theoretical_price FROM orders WHERE status='PENDING'")
    orders = cur.fetchall()
    print("\n⏳ PENDING ORDERS (Waiting for your manual execution feedback):")
    if orders:
        headers = ["Order ID", "Date Generated", "Symbol", "Action", "Shares", "Engine Theoretical Price (¥)"]
        print(tabulate(orders, headers=headers, tablefmt='grid'))
    else:
        print("   (No pending orders)")

    conn.close()

if __name__ == "__main__":
    from src.paper.db import fill_order, init_db

    init_db()
    
    parser = argparse.ArgumentParser(description="Daily Live Signal Generator & Paper Trading Hub")
    subparsers = parser.add_subparsers(dest='command', help='Sub-command to run')
    
    # 'status' command
    p_status = subparsers.add_parser('status', help='View current cash, holdings, and pending orders')
    
    # 'generate' command
    p_gen = subparsers.add_parser('generate', help='Fetch latest prices and generate tomorrow\'s target BUY/SELL orders')
    
    # 'fill' command
    p_fill = subparsers.add_parser('fill', help='Register manual paper execution to trigger the Slippage Feedback Loop')
    p_fill.add_argument('order_id', type=int, help='The ID of the pending order shown in status')
    p_fill.add_argument('actual_price', type=float, help='The exact price you executed it at in your broker app')

    args = parser.parse_args()

    if args.command == 'status':
        print_status()
    elif args.command == 'generate':
        generate_rebalance_orders()
    elif args.command == 'fill':
        fill_order(args.order_id, args.actual_price)
    else:
        parser.print_help()
