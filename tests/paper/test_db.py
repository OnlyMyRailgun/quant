import sqlite3
from pathlib import Path

from src.paper import db as paper_db


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
