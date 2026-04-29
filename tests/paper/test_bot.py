from pathlib import Path
import sqlite3

import pandas as pd

import src.paper.bot as bot
from src.research.artifacts import DEFAULT_ARTIFACT_DIR


def test_generate_rebalance_orders_uses_default_approved_params_artifact_dir(monkeypatch, tmp_path: Path):
    original_connect = sqlite3.connect

    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "paper_trading.db")
    monkeypatch.setattr(bot, "get_wallet_balance", lambda: 100_000.0)
    monkeypatch.setattr(bot, "place_pending_order", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "send_daily_report", lambda *args, **kwargs: None)

    db = sqlite3.connect(bot.DB_PATH)
    db.execute("CREATE TABLE portfolio (symbol TEXT, shares INTEGER, avg_price REAL)")
    db.execute(
        "CREATE TABLE orders (id INTEGER, date TEXT, symbol TEXT, action TEXT, target_shares INTEGER, theoretical_price REAL, actual_price REAL, slippage_pct REAL, status TEXT)"
    )
    db.commit()
    db.close()

    monkeypatch.setattr(bot.sqlite3, "connect", lambda *args, **kwargs: original_connect(bot.DB_PATH))
    monkeypatch.setattr("src.data.universe.get_topix_top_10", lambda: ["AAA.T"])
    monkeypatch.setattr(
        "src.data.bulk_loader.fetch_universe",
        lambda symbols, start_date, end_date: {"AAA.T": pd.DataFrame({"Close": [100.0, 101.0, 102.0]})},
    )

    captured = {}

    def fake_calculate_current_signals(data_dfs, top_n=3, **kwargs):
        captured["artifact_dir"] = kwargs.get("artifact_dir")
        return pd.DataFrame(
            [
                {
                    "symbol": "AAA.T",
                    "price": 102.0,
                    "total_score": 1.0,
                }
            ]
        )

    monkeypatch.setattr(bot, "calculate_current_signals", fake_calculate_current_signals)

    bot.generate_rebalance_orders()

    assert captured["artifact_dir"] == DEFAULT_ARTIFACT_DIR
