import sqlite3
from pathlib import Path

import pytest

from src.paper import db as paper_db


def _setup_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(paper_db, "DB_PATH", db_path)
    monkeypatch.setattr(paper_db, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(paper_db, "FRICTION_FILE", tmp_path / "friction.json")
    paper_db.init_db()
    return db_path


def _portfolio(db_path, symbol):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT shares, avg_price FROM portfolio WHERE symbol=?", (symbol,))
    row = cur.fetchone()
    conn.close()
    return row


def test_fill_sell_of_unowned_symbol_does_not_create_phantom_cash(tmp_path: Path, monkeypatch):
    """Selling a symbol with no position must not credit the wallet (Finding 2)."""
    db_path = _setup_db(tmp_path, monkeypatch)
    start_cash = paper_db.get_wallet_balance()
    oid = paper_db.place_pending_order("GHOST.T", "SELL", 100, 1000.0)

    paper_db.fill_order(oid, 1000.0)

    # No position existed -> wallet must be unchanged, order not marked FILLED as a real sale.
    assert paper_db.get_wallet_balance() == start_cash
    assert _portfolio(db_path, "GHOST.T") is None


def test_fill_sell_cannot_oversell_more_than_held(tmp_path: Path, monkeypatch):
    """Selling more shares than held must not over-credit cash or go negative (Finding 3)."""
    db_path = _setup_db(tmp_path, monkeypatch)
    # Establish a 100-share position via a BUY fill.
    buy = paper_db.place_pending_order("AAA.T", "BUY", 100, 1000.0)
    paper_db.fill_order(buy, 1000.0)
    cash_after_buy = paper_db.get_wallet_balance()

    # Attempt to sell 300 (only 100 held).
    oversell = paper_db.place_pending_order("AAA.T", "SELL", 300, 1000.0)
    paper_db.fill_order(oversell, 1000.0)

    # At most the 100 held may be sold -> cash credited by exactly 100*1000, position cleared to 0/removed.
    assert paper_db.get_wallet_balance() == cash_after_buy + 100 * 1000.0
    pos = _portfolio(db_path, "AAA.T")
    assert pos is None or pos[0] == 0


def test_fill_order_is_atomic_wallet_and_portfolio_move_together(tmp_path: Path, monkeypatch):
    """A BUY fill must update wallet AND portfolio as one unit (Finding 1)."""
    db_path = _setup_db(tmp_path, monkeypatch)
    start_cash = paper_db.get_wallet_balance()
    buy = paper_db.place_pending_order("AAA.T", "BUY", 100, 1000.0)
    paper_db.fill_order(buy, 1000.0)

    # Wallet debited exactly and portfolio reflects the shares — consistent state.
    assert paper_db.get_wallet_balance() == start_cash - 100 * 1000.0
    pos = _portfolio(db_path, "AAA.T")
    assert pos is not None and pos[0] == 100


def test_place_pending_order_returns_order_id(tmp_path: Path, monkeypatch):
    """place_pending_order must return the new row ID so auto-fill can use it."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(paper_db, "DB_PATH", db_path)
    monkeypatch.setattr(paper_db, "CACHE_DIR", tmp_path)
    # init_db creates tables — run it against the test db
    paper_db.init_db()

    oid = paper_db.place_pending_order("AAA.T", "BUY", 100, 5000.0)

    assert oid is not None
    assert isinstance(oid, int)
    assert oid >= 1

    # Verify the order was actually inserted
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, symbol, action, target_shares, theoretical_price, status FROM orders WHERE id=?", (oid,))
    row = cur.fetchone()
    conn.close()

    assert row is not None
    assert row[1] == "AAA.T"
    assert row[2] == "BUY"
    assert row[3] == 100
    assert row[4] == 5000.0
    assert row[5] == "PENDING"


def test_place_pending_order_returns_unique_ids(tmp_path: Path, monkeypatch):
    """Each call returns a monotonically increasing order ID."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(paper_db, "DB_PATH", db_path)
    monkeypatch.setattr(paper_db, "CACHE_DIR", tmp_path)
    paper_db.init_db()

    oid1 = paper_db.place_pending_order("AAA.T", "BUY", 100, 5000.0)
    oid2 = paper_db.place_pending_order("BBB.T", "SELL", 50, 3000.0)
    oid3 = paper_db.place_pending_order("CCC.T", "BUY", 200, 7000.0)

    assert oid1 < oid2 < oid3
    assert oid3 - oid1 >= 2
