import os
import smtplib
import sqlite3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path

from src.paper.db import DB_PATH, FRICTION_FILE


def _build_html_report(
    winners: list[dict],
    orders: list[tuple],
    cash: float,
    portfolio: list[tuple],
    slippage: float,
) -> str:
    """Builds a beautiful HTML email body."""
    date_str = datetime.now().strftime("%Y年%m月%d日 (%A)")

    # Build holdings table rows
    holdings_rows = ""
    if portfolio:
        for sym, shares, avg in portfolio:
            holdings_rows += f"<tr><td>{sym}</td><td>{shares:,}</td><td>¥{avg:,.2f}</td></tr>"
    else:
        holdings_rows = "<tr><td colspan='3' style='color:#888;text-align:center'>No current holdings</td></tr>"

    # Build winner ranking rows
    winner_rows = ""
    medals = ["🥇", "🥈", "🥉"]
    for i, w in enumerate(winners):
        medal = medals[i] if i < 3 else "  "
        winner_rows += f"<tr><td>{medal} {w['symbol']}</td><td>¥{w['price']:,.2f}</td><td>{w['score']:.4f}</td></tr>"

    # Build pending orders
    order_rows = ""
    if orders:
        for oid, date, sym, action, shares, theo, *_ in orders:
            color = "#16a34a" if action == "BUY" else "#dc2626"
            order_rows += f"<tr><td>#{oid}</td><td style='color:{color};font-weight:bold'>{action}</td><td>{sym}</td><td>{shares:,}</td><td>¥{theo:,.2f}</td></tr>"
    else:
        order_rows = "<tr><td colspan='5' style='color:#888;text-align:center'>No pending orders today</td></tr>"

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; margin: 0; padding: 20px; }}
  .card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  h1 {{ color: #0f172a; font-size: 22px; margin: 0 0 4px; }}
  h2 {{ color: #334155; font-size: 15px; font-weight: 600; margin: 0 0 16px; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }}
  .subtitle {{ color: #64748b; font-size: 13px; margin-bottom: 24px; }}
  .metric {{ display: inline-block; background: #f1f5f9; border-radius: 8px; padding: 12px 20px; margin-right: 12px; }}
  .metric-label {{ color: #64748b; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .metric-value {{ color: #0f172a; font-size: 20px; font-weight: 700; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th {{ background: #f8fafc; color: #475569; font-weight: 600; text-align: left; padding: 10px 12px; border-bottom: 2px solid #e2e8f0; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #f1f5f9; color: #334155; }}
  tr:last-child td {{ border-bottom: none; }}
  .footer {{ color: #94a3b8; font-size: 11px; text-align: center; margin-top: 24px; }}
  .badge {{ background: #dbeafe; color: #1d4ed8; font-size: 11px; padding: 2px 8px; border-radius: 99px; font-weight: 600; }}
</style>
</head>
<body>
<div style="max-width:640px;margin:0 auto;">

  <div class="card">
    <h1>📊 Quant Engine Daily Report</h1>
    <div class="subtitle">{date_str} · <span class="badge">Paper Trading</span></div>
    <div>
      <div class="metric">
        <div class="metric-label">Virtual Cash</div>
        <div class="metric-value">¥{cash:,.0f}</div>
      </div>
      <div class="metric">
        <div class="metric-label">Live Slippage</div>
        <div class="metric-value">{slippage*100:.3f}%</div>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>🏆 Today's Factor Winners (Target Portfolio)</h2>
    <table>
      <thead><tr><th>Symbol</th><th>Last Close</th><th>Factor Score</th></tr></thead>
      <tbody>{winner_rows}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>⏳ Pending Orders — Execute These on Your Broker App</h2>
    <table>
      <thead><tr><th>Order ID</th><th>Action</th><th>Symbol</th><th>Shares</th><th>Theoretical Price</th></tr></thead>
      <tbody>{order_rows}</tbody>
    </table>
    <p style="color:#64748b;font-size:12px;margin-top:12px">
      After you execute on your app, run:<br>
      <code>python3 src/paper/bot.py fill &lt;ORDER_ID&gt; &lt;YOUR_ACTUAL_PRICE&gt;</code>
    </p>
  </div>

  <div class="card">
    <h2>📦 Current Holdings</h2>
    <table>
      <thead><tr><th>Symbol</th><th>Shares</th><th>Avg Price</th></tr></thead>
      <tbody>{holdings_rows}</tbody>
    </table>
  </div>

  <div class="footer">
    This report was generated automatically by your Quant Engine.<br>
    Slippage data auto-calibrated from real paper trading executions via feedback loop.
  </div>
</div>
</body>
</html>
"""


def send_daily_report(winners: list[dict], orders: list[tuple], cash: float, portfolio: list[tuple]):
    """
    Reads SMTP credentials from environment variables and sends the daily
    HTML summary email. This function is called at the end of `bot.py generate`.
    """
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    notify_email = os.environ.get("NOTIFY_EMAIL", smtp_user)

    if not smtp_user or not smtp_pass:
        print("[Notifier] SMTP_USER / SMTP_PASS not set. Skipping email. (Set them in .env)")
        return

    # Load current live slippage for display
    slippage = 0.0005
    if FRICTION_FILE.exists():
        import json
        with open(FRICTION_FILE) as f:
            slippage = json.load(f).get("default_slippage_pct", 0.0005)

    html_body = _build_html_report(winners, orders, cash, portfolio, slippage)
    date_str = datetime.now().strftime("%Y-%m-%d")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Quant Engine Daily Signal — {date_str}"
    msg["From"] = smtp_user
    msg["To"] = notify_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, notify_email, msg.as_string())
        print(f"[Notifier] ✅ Daily report sent to {notify_email}")
    except Exception as e:
        print(f"[Notifier] ❌ Failed to send email: {e}")
