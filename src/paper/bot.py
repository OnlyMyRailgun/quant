import sys
import argparse
from pathlib import Path
import pandas as pd
from datetime import datetime
from tabulate import tabulate

from src.research.artifacts import DEFAULT_ARTIFACT_DIR, build_scoring_metadata, build_scoring_summary, write_scoring_run
from src.research.approved_params import resolve_approved_weight_values, load_approved_paper_trading_params
from src.scoring.multi_factor import (
    DEFAULT_LOOKBACK_MOM,
    DEFAULT_LOOKBACK_REV,
    DEFAULT_LOOKBACK_VOL,
    score_universe,
)
from src.paper.db import DB_PATH, get_wallet_balance, place_pending_order
from src.paper.notifier import send_daily_report
import sqlite3


DEFAULT_SIGNAL_WEIGHT_MOM = 1.0
DEFAULT_SIGNAL_WEIGHT_VOL = 1.0
DEFAULT_SIGNAL_WEIGHT_REV = 1.0
DEFAULT_LOT_SIZE = 100


def _round_down_to_lot(shares: int, lot_size: int = DEFAULT_LOT_SIZE) -> int:
    if lot_size < 1:
        raise ValueError("lot_size must be >= 1")
    if shares <= 0:
        return 0
    return (shares // lot_size) * lot_size


def _apply_adverse_slippage(action: str, theoretical_price: float, slippage: float) -> float:
    if slippage < 0:
        raise ValueError("slippage must be non-negative")
    if action == "BUY":
        return theoretical_price * (1 + slippage)
    if action == "SELL":
        return theoretical_price * (1 - slippage)
    raise ValueError(f"Unsupported action: {action}")


def _resolve_signal_weights(
    artifact_dir: Path | None,
    weight_mom: float | None,
    weight_vol: float | None,
    weight_rev: float | None,
) -> tuple[float, float, float]:
    resolved = resolve_approved_weight_values(
        artifact_dir=artifact_dir,
        weight_mom=weight_mom,
        weight_vol=weight_vol,
        weight_rev=weight_rev,
        fallback=(
            DEFAULT_SIGNAL_WEIGHT_MOM,
            DEFAULT_SIGNAL_WEIGHT_VOL,
            DEFAULT_SIGNAL_WEIGHT_REV,
        ),
    )
    return resolved["mom"], resolved["vol"], resolved["rev"]


def _build_signal_run(
    data_dfs,
    top_n=3,
    weight_mom=1.0,
    weight_vol=1.0,
    weight_rev=1.0,
    weight_val=0.0,
    weight_qual=0.0,
    lookback_mom=DEFAULT_LOOKBACK_MOM,
    lookback_vol=DEFAULT_LOOKBACK_VOL,
    lookback_rev=DEFAULT_LOOKBACK_REV,
    momentum_definition="90d",
    book_values=None,
    roe_values=None,
):
    if momentum_definition != "90d":
        from src.research.research_scoring import score_research_universe
        ranked = score_research_universe(
            data_dfs,
            top_n=top_n,
            weight_mom=weight_mom,
            weight_vol=weight_vol,
            weight_rev=weight_rev,
            weight_val=weight_val,
            momentum_definition=momentum_definition,
            book_values=book_values,
        )
        return ranked
    ranked = score_universe(
        data_dfs,
        top_n=top_n,
        weight_mom=weight_mom,
        weight_vol=weight_vol,
        weight_rev=weight_rev,
        weight_val=weight_val,
        weight_qual=weight_qual,
        lookback_mom=lookback_mom,
        lookback_vol=lookback_vol,
        lookback_rev=lookback_rev,
        book_values=book_values,
        roe_values=roe_values,
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
    weight_mom: float | None = None,
    weight_vol: float | None = None,
    weight_rev: float | None = None,
    weight_val: float = 0.0,
    weight_qual: float = 0.0,
    lookback_mom=DEFAULT_LOOKBACK_MOM,
    lookback_vol=DEFAULT_LOOKBACK_VOL,
    lookback_rev=DEFAULT_LOOKBACK_REV,
    artifact_dir: Path | None = None,
    reversal_filter_params=None,
    momentum_definition="90d",
    book_values=None,
    roe_values=None,
):
    """
    Shared paper-trading scorer for generating today's live signals.

    This delegates to the same ranking logic used by the research layer so
    paper-trading recommendations stay aligned with backtests.
    """
    resolved_weight_mom, resolved_weight_vol, resolved_weight_rev = _resolve_signal_weights(
        artifact_dir=artifact_dir,
        weight_mom=weight_mom,
        weight_vol=weight_vol,
        weight_rev=weight_rev,
    )
    # val/qual weights: use approved JSON if available, otherwise passed values
    if artifact_dir is not None:
        approved = load_approved_paper_trading_params(Path(artifact_dir))
        aw = approved["weights"] if approved else {}
    else:
        aw = {}
    resolved_weight_val = float(aw.get("val", weight_val)) if weight_val == 0.0 else weight_val
    resolved_weight_qual = float(aw.get("qual", weight_qual)) if weight_qual == 0.0 else weight_qual

    ranked = _build_signal_run(
        data_dfs,
        top_n=top_n,
        weight_mom=resolved_weight_mom,
        weight_vol=resolved_weight_vol,
        weight_rev=resolved_weight_rev,
        weight_val=resolved_weight_val,
        weight_qual=resolved_weight_qual,
        lookback_mom=lookback_mom,
        lookback_vol=lookback_vol,
        lookback_rev=lookback_rev,
        momentum_definition=momentum_definition,
        book_values=book_values,
        roe_values=roe_values,
    )

    if reversal_filter_params is not None:
        from src.research.reversal_filter import apply_reversal_filter
        result = apply_reversal_filter(ranked, data_dfs, reversal_filter_params)
        ranked = result["filtered_scores"]

    if artifact_dir is not None:
        winners = ranked.head(top_n)
        metadata = build_scoring_metadata(
            scores=ranked,
            top_n=top_n,
            weights={"mom": resolved_weight_mom, "vol": resolved_weight_vol, "rev": resolved_weight_rev},
            lookbacks={
                "mom": lookback_mom,
                "vol": lookback_vol,
                "rev": lookback_rev,
            },
        )
        summary = build_scoring_summary(
            scores=ranked,
            top_n=top_n,
        )
        write_scoring_run(
            base_dir=Path(artifact_dir),
            run_name="paper_signal",
            metadata=metadata,
            scores=ranked,
            summary=summary,
        )

    return _with_legacy_factor_aliases(ranked.head(top_n))

def generate_rebalance_orders(
    universe_name="topix_top_10",
    momentum_definition="90d",
    reversal_filter_params=None,
    auto_fill=False,
):
    from src.data.universe import get_universe
    from src.data.bulk_loader import fetch_universe

    # Monthly guard: skip if already rebalanced this month
    today = pd.Timestamp.today()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT MAX(date) FROM orders WHERE status='FILLED'")
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        last_date = pd.Timestamp(row[0])
        if last_date.year == today.year and last_date.month == today.month:
            print(f"Already rebalanced this month (last fill: {row[0]}). Skipping.")
            return

    symbols = get_universe(universe_name)

    print(f"Fetching latest data for {len(symbols)} symbols ({universe_name})...")
    # Need at least 300 days for 12_1 momentum lookback
    history_days = 400 if momentum_definition == "12_1" else 200
    start_date = (pd.Timestamp.today() - pd.Timedelta(days=history_days)).strftime("%Y-%m-%d")
    end_date = pd.Timestamp.today().strftime("%Y-%m-%d")

    dfs = fetch_universe(symbols, start_date, end_date)

    # Fetch fundamental data for value and quality factors
    from src.data.fundamental_loader import get_book_values, get_roe_values
    book_vals = get_book_values(symbols)
    roe_vals = get_roe_values(symbols)

    print("\nRunning Multi-Factor Scoring Engine on Latest Close...")
    winners = calculate_current_signals(
        dfs, top_n=3, artifact_dir=DEFAULT_ARTIFACT_DIR,
        momentum_definition=momentum_definition,
        reversal_filter_params=reversal_filter_params,
        weight_val=0.5, weight_qual=1.0,
        book_values=book_vals, roe_values=roe_vals,
    )
    
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

    order_ids: list[tuple[int, str, float]] = []
    projected_cash = wallet_cash

    # 1. Determine SELL orders (what we hold but shouldn't)
    for sym, shares in current_portfolio.items():
        if sym not in target_symbols:
            price = dfs[sym]['Close'].iloc[-1]
            oid = place_pending_order(sym, 'SELL', shares, theoretical_price=price)
            order_ids.append((oid, 'SELL', price))
            projected_cash += shares * price

    # 2. Determine BUY orders (allocating cash equally)
    # Note: A real system handles sell proceeds simultaneously.
    # For MVP we simply assume we divide current + theoretical proceeds equally.
    # To keep it safe, we just use the fixed theoretical target weight
    target_value_per_stock = projected_cash * 0.95 / len(target_symbols)

    for _, row in winners.iterrows():
        sym = row['symbol']
        price = row['price']

        current_shares = current_portfolio.get(sym, 0)
        target_shares = _round_down_to_lot(int(target_value_per_stock / price))

        diff = target_shares - current_shares

        if diff > 0:
            oid = place_pending_order(sym, 'BUY', diff, theoretical_price=price)
            order_ids.append((oid, 'BUY', price))
        elif diff < 0:
            oid = place_pending_order(sym, 'SELL', abs(diff), theoretical_price=price)
            order_ids.append((oid, 'SELL', price))
            
    print("\n✅ Target orders staged in the paper trading database.")

    if not auto_fill:
        print("Run this script using 'fill <ORDER_ID> <YOUR_ACTUAL_EXECUTION_PRICE>' tomorrow after you trade them on your app!")

    if auto_fill:
        from src.engine.commission import load_live_slippage
        from src.paper.db import fill_order

        slippage = load_live_slippage()
        filled: list[tuple[int, str, float, float]] = []
        for oid, action, tprice in order_ids:
            actual_price = _apply_adverse_slippage(action, tprice, slippage)
            fill_order(oid, actual_price)
            filled.append((oid, action, tprice, actual_price))

        print(f"\n✅ Auto-filled {len(filled)} orders (slippage {slippage*100:.2f}%):")
        print(tabulate(
            [(oid, action, f"¥{tp:,.2f}", f"¥{ap:,.2f}") for oid, action, tp, ap in filled],
            headers=["Order ID", "Action", "Theoretical Price", "Fill Price"],
            tablefmt='psql',
        ))

    # Always send daily summary email
    conn2 = sqlite3.connect(DB_PATH)
    cur2 = conn2.cursor()
    cur2.execute("SELECT id, date, symbol, action, target_shares, theoretical_price, actual_price, status FROM orders ORDER BY id DESC LIMIT 20")
    recent_orders = cur2.fetchall()
    cur2.execute('SELECT symbol, shares, avg_price FROM portfolio')
    full_portfolio = cur2.fetchall()
    wallet_cash = get_wallet_balance()
    conn2.close()

    winners_list = [
        {'symbol': row['symbol'], 'price': row['price'], 'score': row['total_score']}
        for _, row in winners.iterrows()
    ]
    send_daily_report(
        winners=winners_list,
        orders=recent_orders,
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
    p_gen.add_argument(
        "--universe-name",
        default="topix_top_10",
        help="Named universe from src.data.universe (default: topix_top_10)",
    )
    p_gen.add_argument(
        "--momentum-definition",
        choices=["90d", "12_1"],
        default="90d",
        help="Momentum definition (default: 90d)",
    )
    p_gen.add_argument(
        "--reversal-filter",
        action="store_true",
        help="Enable reversal filter with default params",
    )
    p_gen.add_argument(
        "--reversal-lookback",
        type=int,
        default=20,
        help="Reversal filter lookback days",
    )
    p_gen.add_argument(
        "--reversal-threshold",
        type=float,
        default=0.10,
        help="Reversal filter drawdown threshold",
    )
    p_gen.add_argument(
        "--auto-fill",
        action="store_true",
        help="Auto-fill orders at close price minus slippage",
    )
    
    # 'fill' command
    p_fill = subparsers.add_parser('fill', help='Register manual paper execution to trigger the Slippage Feedback Loop')
    p_fill.add_argument('order_id', type=int, help='The ID of the pending order shown in status')
    p_fill.add_argument('actual_price', type=float, help='The exact price you executed it at in your broker app')

    args = parser.parse_args()

    if args.command == 'status':
        print_status()
    elif args.command == 'generate':
        reversal_filter_params = None
        if args.reversal_filter:
            from src.research.reversal_filter import ReversalFilterParams
            reversal_filter_params = ReversalFilterParams(
                lookback_days=args.reversal_lookback,
                threshold=args.reversal_threshold,
            )
        generate_rebalance_orders(
            universe_name=args.universe_name,
            momentum_definition=args.momentum_definition,
            reversal_filter_params=reversal_filter_params,
            auto_fill=args.auto_fill,
        )
    elif args.command == 'fill':
        fill_order(args.order_id, args.actual_price)
    else:
        parser.print_help()
