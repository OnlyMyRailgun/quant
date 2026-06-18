from pathlib import Path
import sqlite3

import pandas as pd
import pytest

import src.paper.bot as bot
from src.research.artifacts import DEFAULT_ARTIFACT_DIR


def _setup_test_db_and_mocks(monkeypatch, tmp_path: Path, with_filled_orders: bool = False):
    """Shared setup for paper bot tests. Returns captured dict and the DB path."""
    original_connect = sqlite3.connect
    db_path = tmp_path / "paper_trading.db"

    monkeypatch.setattr(bot, "DB_PATH", db_path)
    monkeypatch.setattr(bot, "get_wallet_balance", lambda: 100_000.0)
    monkeypatch.setattr(bot, "place_pending_order", lambda *args, **kwargs: 1)
    monkeypatch.setattr(bot, "send_daily_report", lambda *args, **kwargs: None)

    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE portfolio (symbol TEXT, shares INTEGER, avg_price REAL)")
    db.execute(
        "CREATE TABLE orders (id INTEGER, date TEXT, symbol TEXT, action TEXT,"
        " target_shares INTEGER, theoretical_price REAL, actual_price REAL,"
        " slippage_pct REAL, status TEXT)"
    )
    if with_filled_orders:
        # Simulate a filled order from earlier this month
        filled_date = pd.Timestamp.today().strftime("%Y-%m-%d")
        db.execute(
            "INSERT INTO orders (date, symbol, action, target_shares, theoretical_price, status)"
            " VALUES (?, 'AAA.T', 'BUY', 100, 5000.0, 'FILLED')",
            (filled_date,),
        )
    db.commit()
    db.close()

    monkeypatch.setattr(bot.sqlite3, "connect", lambda *a, **kw: original_connect(db_path))
    monkeypatch.setattr("src.data.universe.get_topix_top_10", lambda: ["AAA.T"])
    monkeypatch.setattr(
        "src.data.bulk_loader.fetch_universe",
        lambda symbols, start_date, end_date: {"AAA.T": pd.DataFrame({"Close": [100.0, 101.0, 102.0]})},
    )

    captured = {}

    def fake_calculate_current_signals(data_dfs, top_n=3, **kwargs):
        captured["top_n"] = top_n
        captured.update(kwargs)
        return pd.DataFrame([
            {"symbol": "AAA.T", "price": 102.0, "total_score": 1.0}
        ])

    monkeypatch.setattr(bot, "calculate_current_signals", fake_calculate_current_signals)
    return captured


def test_generate_rebalance_orders_uses_default_approved_params_artifact_dir(monkeypatch, tmp_path: Path):
    captured = _setup_test_db_and_mocks(monkeypatch, tmp_path)

    bot.generate_rebalance_orders()

    assert captured.get("artifact_dir") == DEFAULT_ARTIFACT_DIR
    assert captured["top_n"] == 10


def test_generate_rebalance_orders_uses_roe_values_for_quality_factor(monkeypatch, tmp_path: Path):
    captured = _setup_test_db_and_mocks(monkeypatch, tmp_path)

    monkeypatch.setattr("src.data.fundamental_loader.get_book_values", lambda symbols: {"AAA.T": 100.0})
    monkeypatch.setattr("src.data.fundamental_loader.get_roe_values", lambda symbols: {"AAA.T": 0.12})

    bot.generate_rebalance_orders()

    assert captured["book_values"] == {"AAA.T": 100.0}
    assert captured["roe_values"] == {"AAA.T": 0.12}


def test_monthly_guard_skips_when_already_rebalanced_this_month(monkeypatch, tmp_path: Path):
    """If a FILLED order exists from this month, generate_rebalance_orders should return early."""
    _setup_test_db_and_mocks(monkeypatch, tmp_path, with_filled_orders=True)
    called = {}

    def fake_fetch(symbols, start, end):
        called["fetch"] = True
        return {}

    monkeypatch.setattr("src.data.bulk_loader.fetch_universe", fake_fetch)

    bot.generate_rebalance_orders()

    # Should have returned before fetching any data
    assert "fetch" not in called


def test_monthly_guard_allows_rebalance_when_last_filled_is_previous_month(monkeypatch, tmp_path: Path):
    """If the most recent FILLED order is from a previous month, rebalance proceeds."""
    original_connect = sqlite3.connect
    db_path = tmp_path / "paper_trading.db"

    monkeypatch.setattr(bot, "DB_PATH", db_path)
    monkeypatch.setattr(bot, "get_wallet_balance", lambda: 100_000.0)
    monkeypatch.setattr(bot, "place_pending_order", lambda *args, **kwargs: 1)
    monkeypatch.setattr(bot, "send_daily_report", lambda *args, **kwargs: None)

    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE portfolio (symbol TEXT, shares INTEGER, avg_price REAL)")
    db.execute(
        "CREATE TABLE orders (id INTEGER, date TEXT, symbol TEXT, action TEXT,"
        " target_shares INTEGER, theoretical_price REAL, actual_price REAL,"
        " slippage_pct REAL, status TEXT)"
    )
    # Filled order from previous month
    db.execute(
        "INSERT INTO orders (date, symbol, action, target_shares, theoretical_price, status)"
        " VALUES ('2026-03-28', 'AAA.T', 'BUY', 100, 5000.0, 'FILLED')"
    )
    db.commit()
    db.close()

    monkeypatch.setattr(bot.sqlite3, "connect", lambda *a, **kw: original_connect(db_path))
    monkeypatch.setattr("src.data.universe.get_topix_top_10", lambda: ["AAA.T"])
    monkeypatch.setattr(
        "src.data.bulk_loader.fetch_universe",
        lambda symbols, start_date, end_date: {"AAA.T": pd.DataFrame({"Close": [100.0, 101.0, 102.0]})},
    )

    captured = {}

    def fake_calculate_current_signals(data_dfs, top_n=3, **kwargs):
        captured["called"] = True
        captured["top_n"] = top_n
        captured.update(kwargs)
        return pd.DataFrame([
            {"symbol": "AAA.T", "price": 102.0, "total_score": 1.0}
        ])

    monkeypatch.setattr(bot, "calculate_current_signals", fake_calculate_current_signals)

    bot.generate_rebalance_orders()

    assert captured.get("called") is True


def test_email_sent_in_auto_fill_mode(monkeypatch, tmp_path: Path):
    """In auto-fill mode, send_daily_report is still called."""
    captured = _setup_test_db_and_mocks(monkeypatch, tmp_path)

    email_called = {}

    def fake_send_daily_report(winners=None, orders=None, cash=None, portfolio=None):
        email_called["called"] = True
        email_called["winners"] = winners
        email_called["cash"] = cash

    monkeypatch.setattr(bot, "send_daily_report", fake_send_daily_report)
    # Both load_live_slippage and fill_order are imported locally inside
    # generate_rebalance_orders — stub their source modules
    monkeypatch.setattr("src.engine.commission.load_live_slippage", lambda: 0.0005)
    monkeypatch.setattr("src.paper.db.fill_order", lambda oid, price: None)

    bot.generate_rebalance_orders(auto_fill=True)

    assert email_called.get("called") is True
    assert email_called["winners"] is not None
    assert len(email_called["winners"]) == 1
    assert email_called["winners"][0]["symbol"] == "AAA.T"
    assert email_called["cash"] == 100_000.0


def test_generate_rebalance_orders_rounds_buy_quantity_to_100_share_lot(monkeypatch, tmp_path: Path):
    _setup_test_db_and_mocks(monkeypatch, tmp_path)
    placed_orders = []

    def fake_place_pending_order(symbol, action, shares, theoretical_price):
        placed_orders.append(
            {
                "symbol": symbol,
                "action": action,
                "shares": shares,
                "theoretical_price": theoretical_price,
            }
        )
        return len(placed_orders)

    monkeypatch.setattr(bot, "place_pending_order", fake_place_pending_order)

    bot.generate_rebalance_orders()

    buy_orders = [order for order in placed_orders if order["action"] == "BUY"]
    assert buy_orders == [
        {
            "symbol": "AAA.T",
            "action": "BUY",
            "shares": 900,
            "theoretical_price": 102.0,
        }
    ]


def test_auto_fill_applies_adverse_slippage_by_order_side(monkeypatch, tmp_path: Path):
    _setup_test_db_and_mocks(monkeypatch, tmp_path)

    db = sqlite3.connect(bot.DB_PATH)
    db.execute("INSERT INTO portfolio (symbol, shares, avg_price) VALUES ('6758.T', 100, 200.0)")
    db.commit()
    db.close()

    def fake_fetch_universe(symbols, start_date, end_date):
        return {
            "AAA.T": pd.DataFrame({"Close": [100.0, 101.0, 102.0]}),
            "6758.T": pd.DataFrame({"Close": [200.0, 201.0, 202.0]}),
        }

    monkeypatch.setattr("src.data.bulk_loader.fetch_universe", fake_fetch_universe)

    placed_by_id = {}

    def fake_place_pending_order(symbol, action, shares, theoretical_price):
        order_id = len(placed_by_id) + 1
        placed_by_id[order_id] = {
            "symbol": symbol,
            "action": action,
            "theoretical_price": theoretical_price,
        }
        return order_id

    fills = []

    def fake_fill_order(order_id, actual_price):
        fills.append(
            {
                "action": placed_by_id[order_id]["action"],
                "theoretical_price": placed_by_id[order_id]["theoretical_price"],
                "actual_price": actual_price,
            }
        )

    monkeypatch.setattr(bot, "place_pending_order", fake_place_pending_order)
    monkeypatch.setattr("src.engine.commission.load_live_slippage", lambda: 0.01)
    monkeypatch.setattr("src.paper.db.fill_order", fake_fill_order)

    bot.generate_rebalance_orders(auto_fill=True)

    assert {fill["action"] for fill in fills} == {"BUY", "SELL"}
    assert fills == [
        {"action": "SELL", "theoretical_price": 202.0, "actual_price": pytest.approx(199.98)},
        {"action": "BUY", "theoretical_price": 102.0, "actual_price": pytest.approx(103.02)},
    ]


def test_rebalance_budget_includes_theoretical_non_target_sell_proceeds(monkeypatch, tmp_path: Path):
    _setup_test_db_and_mocks(monkeypatch, tmp_path)

    db = sqlite3.connect(bot.DB_PATH)
    db.execute("INSERT INTO portfolio (symbol, shares, avg_price) VALUES ('6758.T', 100, 200.0)")
    db.commit()
    db.close()

    def fake_fetch_universe(symbols, start_date, end_date):
        return {
            "AAA.T": pd.DataFrame({"Close": [100.0, 101.0, 102.0]}),
            "6758.T": pd.DataFrame({"Close": [200.0, 201.0, 202.0]}),
        }

    placed_orders = []

    def fake_place_pending_order(symbol, action, shares, theoretical_price):
        placed_orders.append(
            {
                "symbol": symbol,
                "action": action,
                "shares": shares,
                "theoretical_price": theoretical_price,
            }
        )
        return len(placed_orders)

    monkeypatch.setattr("src.data.bulk_loader.fetch_universe", fake_fetch_universe)
    monkeypatch.setattr(bot, "place_pending_order", fake_place_pending_order)

    bot.generate_rebalance_orders()

    assert placed_orders == [
        {"symbol": "6758.T", "action": "SELL", "shares": 100, "theoretical_price": 202.0},
        {"symbol": "AAA.T", "action": "BUY", "shares": 1100, "theoretical_price": 102.0},
    ]
