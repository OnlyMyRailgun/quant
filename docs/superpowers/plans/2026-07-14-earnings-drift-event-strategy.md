# Earnings / Guidance Surprise Drift Event Strategy (Strategy A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained, long-only, event-driven post-announcement-drift strategy that scores Japanese earnings/guidance disclosures by quantitative surprise, enters at the next trading day's open, and exits on a time/take-profit/stop-loss rule.

**Architecture:** Four independent units with zero coupling to the monthly multi-factor pipeline: a J-Quants `/fins/statements` loader (parquet-cached), a pure surprise-scoring + tagging module, a pure event-filter module, a standalone event-driven backtester, and a metrics aggregator. Data flows loader -> surprise -> filters -> event_runner -> event_backtest.

**Tech Stack:** Python 3.12, pandas, pyarrow, jquants-api-client, pytest, uv.

## Global Constraints

- v1 is **long-only**. No shorts, no TDnet, no NLP, no live/paper execution — research/backtest only.
- Single data source: J-Quants `/fins/statements` (event timing AND surprise inputs both come from here).
- **Look-ahead safety is the top invariant**: surprise scores use only data known as of the disclosure date; entry is the NEXT trading day's open. No score may read a value dated after the disclosure date; no fill may use a price dated on or before the disclosure date.
- Surprise uses **relative** magnitude: `(actual - forecast)/|forecast|`. Missing forecast -> YoY fallback. Both missing -> **drop the event** (never fabricate).
- v1 takes **positive-only** events (long).
- Reuse the existing commission RATE from `src/engine/commission.py` (`JapanStockCommission.params.commission = 0.001`) and the slippage default (`load_live_slippage()`, default 0.0005). The event runner is NOT backtrader-based, so it uses these numbers directly, not the `bt.CommInfoBase` class.
- Follow `src/data/jquants_loader.py` conventions in the new loader: `jquantsapi.ClientV2`, `.T`-suffix stripping (`_codes_to_jquants`), JST date coercion, parquet cache under `.data_cache/jquants/`, exponential-backoff retry on "429".
- Run all commands with `uv run`. Tests live under `tests/`. Ticker symbols carry a `.T` suffix externally.

## SUBSCRIPTION PREREQUISITE (read before starting)

Task 1 fetches live data from J-Quants `/fins/statements`, which requires a paid J-Quants subscription the project does not currently have. **Do not start Task 1 until a subscription with statements access exists.** Two things gate Task 1:

1. Confirm the account tier includes `/fins/statements` and note its history depth.
2. Capture ONE real API response (a few symbols, one fiscal quarter) and save it to `tests/fixtures/fins_statements_sample.json`. The loader's field-mapping and the missing-field test are derived from this real sample, per the AGENTS.md "integration test with real data" lesson. The exact field names below (`NetSales`, `Profit`, `ForecastProfit`, `DisclosedDate`, etc.) are J-Quants' documented names but MUST be reconciled against the captured sample before implementing — adjust the loader's column map if they differ.

Tasks 2-5 (surprise, filters, runner, metrics) are pure/logic modules with synthetic-data tests and can be implemented WITHOUT a subscription. If you want to make progress before the subscription lands, implement Tasks 2-5 first, then Task 1 last.

---

### Task 1: `statements_loader` — fetch and cache /fins/statements

**Files:**
- Create: `src/data/statements_loader.py`
- Create: `tests/data/test_statements_loader.py`
- Create (prerequisite, from real API): `tests/fixtures/fins_statements_sample.json`

**Interfaces:**
- Consumes: `jquantsapi.ClientV2` (via a local `_get_statements_client()`), the `.T`-stripping and JST-date conventions mirrored from `jquants_loader.py`.
- Produces: `fetch_statements(tickers: list[str], start: str, end: str, force_refresh: bool = False) -> dict[str, pd.DataFrame]` where each DataFrame has columns `["disclose_date", "period_end", "actual_profit", "forecast_profit", "prev_forecast_profit", "yoy_prev_profit"]` indexed 0..n, sorted by `disclose_date` ascending. Also `_normalize_statement_rows(raw: pd.DataFrame) -> pd.DataFrame` mapping raw J-Quants columns to that schema, and `_parse_statements_response(records: list[dict]) -> pd.DataFrame`.

- [ ] **Step 0 (prerequisite): Capture the real sample**

With a subscription active, run a one-off script (not committed) to call `ClientV2().get_fins_statements(...)` for ~3 symbols over one quarter, and save the raw JSON records to `tests/fixtures/fins_statements_sample.json`. Inspect the actual field names and reconcile them with the column map in Step 3. This step cannot be automated without credentials.

- [ ] **Step 1: Write the failing test (uses the real sample fixture, not a mock)**

```python
# tests/data/test_statements_loader.py
import json
from pathlib import Path

import pandas as pd

from src.data.statements_loader import (
    _normalize_statement_rows,
    _parse_statements_response,
    fetch_statements,
)

FIXTURE = Path("tests/fixtures/fins_statements_sample.json")


def test_parse_real_sample_has_expected_schema():
    records = json.loads(FIXTURE.read_text())
    df = _parse_statements_response(records)
    for col in [
        "disclose_date", "period_end", "actual_profit",
        "forecast_profit", "prev_forecast_profit", "yoy_prev_profit",
    ]:
        assert col in df.columns
    assert df["disclose_date"].is_monotonic_increasing


def test_normalize_tolerates_missing_forecast_field():
    # A period where the company published no forecast: forecast_profit must be
    # NaN, not a crash, and the row is still returned (surprise.py decides drop).
    raw = pd.DataFrame([{
        "DisclosedDate": "2024-05-10", "CurrentPeriodEndDate": "2024-03-31",
        "Profit": "1000", "ForecastProfit": "",  # empty forecast
    }])
    out = _normalize_statement_rows(raw)
    assert pd.isna(out.loc[0, "forecast_profit"])
    assert out.loc[0, "actual_profit"] == 1000.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/data/test_statements_loader.py -v`
Expected: FAIL (`ModuleNotFoundError: src.data.statements_loader`).

- [ ] **Step 3: Write minimal implementation**

```python
# src/data/statements_loader.py
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import time

import pandas as pd

CACHE_DIR = Path(".data_cache/jquants")
JST = timezone(timedelta(hours=9))

# Reconcile these names against tests/fixtures/fins_statements_sample.json (Step 0).
_COLMAP = {
    "DisclosedDate": "disclose_date",
    "CurrentPeriodEndDate": "period_end",
    "Profit": "actual_profit",
    "ForecastProfit": "forecast_profit",
}


def _get_statements_client():
    from jquantsapi import ClientV2
    return ClientV2()


def _codes_to_jquants(tickers: list[str]) -> list[str]:
    return [t.replace(".T", "") for t in tickers]


def _to_num(value) -> float:
    if value is None or value == "":
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _normalize_statement_rows(raw: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["disclose_date"] = pd.to_datetime(raw.get("DisclosedDate"), errors="coerce")
    out["period_end"] = pd.to_datetime(raw.get("CurrentPeriodEndDate"), errors="coerce")
    out["actual_profit"] = raw.get("Profit").map(_to_num) if "Profit" in raw else float("nan")
    out["forecast_profit"] = raw.get("ForecastProfit").map(_to_num) if "ForecastProfit" in raw else float("nan")
    # prev_forecast and yoy are derived downstream from the ordered history:
    out["prev_forecast_profit"] = float("nan")
    out["yoy_prev_profit"] = float("nan")
    return out


def _parse_statements_response(records: list[dict]) -> pd.DataFrame:
    raw = pd.DataFrame(records)
    out = _normalize_statement_rows(raw)
    out = out.dropna(subset=["disclose_date"]).sort_values("disclose_date").reset_index(drop=True)
    # prev_forecast_profit = the previous row's forecast for the same period_end;
    # yoy_prev_profit = actual_profit from ~1 year earlier (same fiscal quarter).
    out["prev_forecast_profit"] = out.groupby("period_end")["forecast_profit"].shift(1)
    out["yoy_prev_profit"] = out["actual_profit"].shift(4)  # 4 quarters back
    return out


def _fetch_with_retry(cli, codes, start_dt, end_dt, max_retries=3):
    for attempt in range(max_retries):
        try:
            return cli.get_fins_statements(code=codes, from_yyyymmdd=start_dt, to_yyyymmdd=end_dt)
        except Exception as e:  # noqa: BLE001 - mirror jquants_loader retry policy
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise


def _parquet_path(code: str) -> Path:
    return CACHE_DIR / f"statements_{code}.parquet"


def fetch_statements(
    tickers: list[str],
    start: str,
    end: str,
    force_refresh: bool = False,
) -> dict[str, pd.DataFrame]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    codes = _codes_to_jquants(tickers)
    result: dict[str, pd.DataFrame] = {}
    cli = None
    for ticker, code in zip(tickers, codes):
        path = _parquet_path(code)
        if path.exists() and not force_refresh:
            result[ticker] = pd.read_parquet(path)
            continue
        if cli is None:
            cli = _get_statements_client()
        raw = _fetch_with_retry(cli, code, start.replace("-", ""), end.replace("-", ""))
        records = raw if isinstance(raw, list) else raw.to_dict("records")
        df = _parse_statements_response(records)
        if not df.empty:
            df.to_parquet(path)
        result[ticker] = df
    return result
```

Note: `get_fins_statements` argument names (`code`, `from_yyyymmdd`, `to_yyyymmdd`) and the raw-return shape MUST be reconciled against the real client during Step 0 and adjusted here if they differ.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/data/test_statements_loader.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data/statements_loader.py tests/data/test_statements_loader.py tests/fixtures/fins_statements_sample.json
git commit -m "feat: add J-Quants /fins/statements loader for Strategy A"
```

---

### Task 2: `surprise` — compute surprise scores and tag events

**Files:**
- Create: `src/events/__init__.py`
- Create: `src/events/surprise.py`
- Create: `tests/events/__init__.py`
- Create: `tests/events/test_surprise.py`

**Interfaces:**
- Consumes: statement DataFrames with the Task 1 schema (`disclose_date, period_end, actual_profit, forecast_profit, prev_forecast_profit, yoy_prev_profit`).
- Produces: `compute_events(statements: dict[str, pd.DataFrame]) -> pd.DataFrame` with columns `["symbol", "disclose_date", "event_type", "raw_surprise", "event_score"]`, where `event_type` is `"earnings"` or `"guidance"`, `raw_surprise` is the relative magnitude, and `event_score` is its cross-sectional z-score. Also pure helpers `earnings_surprise(actual, forecast, yoy_prev) -> float` and `guidance_surprise(new_forecast, prev_forecast) -> float`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/events/test_surprise.py
import math

import pandas as pd

from src.events.surprise import compute_events, earnings_surprise, guidance_surprise


def test_earnings_surprise_uses_forecast_when_present():
    # (1200 - 1000)/1000 = 0.2
    assert earnings_surprise(1200.0, 1000.0, yoy_prev=800.0) == 0.2


def test_earnings_surprise_falls_back_to_yoy_when_forecast_missing():
    # forecast NaN -> use YoY: (1200 - 800)/800 = 0.5
    assert earnings_surprise(1200.0, math.nan, yoy_prev=800.0) == 0.5


def test_earnings_surprise_drops_when_both_missing():
    # both forecast and yoy missing -> NaN signals "drop"
    assert math.isnan(earnings_surprise(1200.0, math.nan, yoy_prev=math.nan))


def test_guidance_surprise_relative_upward():
    # (1500 - 1000)/1000 = 0.5
    assert guidance_surprise(1500.0, 1000.0) == 0.5


def test_compute_events_drops_unscorable_and_zscores_the_rest():
    statements = {
        "AAA.T": pd.DataFrame([
            {"disclose_date": pd.Timestamp("2024-05-10"), "period_end": pd.Timestamp("2024-03-31"),
             "actual_profit": 1200.0, "forecast_profit": 1000.0,
             "prev_forecast_profit": math.nan, "yoy_prev_profit": 800.0},
        ]),
        "BBB.T": pd.DataFrame([
            {"disclose_date": pd.Timestamp("2024-05-10"), "period_end": pd.Timestamp("2024-03-31"),
             "actual_profit": 900.0, "forecast_profit": 1000.0,
             "prev_forecast_profit": math.nan, "yoy_prev_profit": 950.0},
        ]),
        "CCC.T": pd.DataFrame([
            {"disclose_date": pd.Timestamp("2024-05-10"), "period_end": pd.Timestamp("2024-03-31"),
             "actual_profit": 500.0, "forecast_profit": math.nan,
             "prev_forecast_profit": math.nan, "yoy_prev_profit": math.nan},  # unscorable -> dropped
        ]),
    }
    events = compute_events(statements)
    assert "CCC.T" not in set(events["symbol"])
    assert set(events["symbol"]) == {"AAA.T", "BBB.T"}
    # AAA has positive surprise (+0.2), BBB negative (-0.1) -> AAA's z-score is higher
    aaa = events.set_index("symbol").loc["AAA.T", "event_score"]
    bbb = events.set_index("symbol").loc["BBB.T", "event_score"]
    assert aaa > bbb
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/events/test_surprise.py -v`
Expected: FAIL (`ModuleNotFoundError: src.events.surprise`).

- [ ] **Step 3: Write minimal implementation**

```python
# src/events/__init__.py
```
```python
# src/events/surprise.py
from __future__ import annotations

import math

import pandas as pd


def earnings_surprise(actual: float, forecast: float, yoy_prev: float) -> float:
    if forecast is not None and not math.isnan(forecast) and forecast != 0.0:
        return (actual - forecast) / abs(forecast)
    if yoy_prev is not None and not math.isnan(yoy_prev) and yoy_prev != 0.0:
        return (actual - yoy_prev) / abs(yoy_prev)
    return math.nan


def guidance_surprise(new_forecast: float, prev_forecast: float) -> float:
    if prev_forecast is None or math.isnan(prev_forecast) or prev_forecast == 0.0:
        return math.nan
    if new_forecast is None or math.isnan(new_forecast):
        return math.nan
    return (new_forecast - prev_forecast) / abs(prev_forecast)


def _zscore(values: list[float]) -> list[float]:
    if len(values) < 2:
        return [0.0] * len(values)
    s = pd.Series(values, dtype="float64")
    std = s.std(ddof=1)
    if pd.isna(std) or std == 0.0:
        return [0.0] * len(values)
    mean = s.mean()
    return [(v - mean) / std for v in values]


def compute_events(statements: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for symbol, df in statements.items():
        if df is None or df.empty:
            continue
        for _, r in df.iterrows():
            es = earnings_surprise(
                r["actual_profit"], r.get("forecast_profit", math.nan), r.get("yoy_prev_profit", math.nan)
            )
            if not math.isnan(es):
                rows.append({"symbol": symbol, "disclose_date": r["disclose_date"],
                             "event_type": "earnings", "raw_surprise": es})
            gs = guidance_surprise(r.get("forecast_profit", math.nan), r.get("prev_forecast_profit", math.nan))
            if not math.isnan(gs):
                rows.append({"symbol": symbol, "disclose_date": r["disclose_date"],
                             "event_type": "guidance", "raw_surprise": gs})
    if not rows:
        return pd.DataFrame(columns=["symbol", "disclose_date", "event_type", "raw_surprise", "event_score"])
    out = pd.DataFrame(rows)
    # cross-sectional z-score within each (disclose_date, event_type) cohort
    out["event_score"] = 0.0
    for _, idx in out.groupby(["disclose_date", "event_type"]).groups.items():
        vals = out.loc[idx, "raw_surprise"].tolist()
        out.loc[idx, "event_score"] = _zscore(vals)
    return out.reset_index(drop=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/events/test_surprise.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/events/__init__.py src/events/surprise.py tests/events/__init__.py tests/events/test_surprise.py
git commit -m "feat: add earnings/guidance surprise scoring for Strategy A"
```

---

### Task 3: `filters` — liquidity, price, gap, duplicate filters

**Files:**
- Create: `src/events/filters.py`
- Create: `tests/events/test_filters.py`

**Interfaces:**
- Consumes: the event DataFrame from Task 2 (`symbol, disclose_date, event_type, raw_surprise, event_score`) and a `bars: dict[str, pd.DataFrame]` of daily OHLCV (columns `Open, High, Low, Close, Volume`, DatetimeIndex) — the same shape the existing `jquants_loader.fetch_daily_bars` returns.
- Produces: `apply_filters(events, bars, *, min_adv=0.0, min_price=0.0, max_gap=0.10, adv_lookback=20) -> pd.DataFrame` returning only surviving events, plus a `next_open_date` and `next_open_price` column added (the entry reference). Positive-only: also drops events with `event_score <= 0`. Helper `_next_trading_day_open(bar_df, disclose_date) -> tuple[pd.Timestamp | None, float | None]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/events/test_filters.py
import pandas as pd

from src.events.filters import apply_filters, _next_trading_day_open


def _bars(dates, closes, vols, opens=None):
    opens = opens or closes
    return pd.DataFrame(
        {"Open": opens, "High": closes, "Low": closes, "Close": closes, "Volume": vols},
        index=pd.to_datetime(dates),
    )


def test_next_trading_day_open_picks_first_bar_after_disclosure():
    bars = _bars(["2024-05-10", "2024-05-13"], [100.0, 105.0], [1000, 1000], opens=[100.0, 104.0])
    d, p = _next_trading_day_open(bars, pd.Timestamp("2024-05-10"))
    assert d == pd.Timestamp("2024-05-13")
    assert p == 104.0


def test_apply_filters_drops_low_price_low_liquidity_and_nonpositive():
    dates = pd.date_range("2024-04-01", periods=40, freq="B")
    events = pd.DataFrame([
        {"symbol": "GOOD.T", "disclose_date": dates[30], "event_type": "earnings",
         "raw_surprise": 0.2, "event_score": 1.5},
        {"symbol": "CHEAP.T", "disclose_date": dates[30], "event_type": "earnings",
         "raw_surprise": 0.2, "event_score": 1.2},
        {"symbol": "NEG.T", "disclose_date": dates[30], "event_type": "earnings",
         "raw_surprise": -0.2, "event_score": -1.5},
    ])
    bars = {
        "GOOD.T": _bars(dates, [1000.0] * 40, [100000] * 40),
        "CHEAP.T": _bars(dates, [80.0] * 40, [100] * 40),   # low price + low ADV
        "NEG.T": _bars(dates, [1000.0] * 40, [100000] * 40),
    }
    out = apply_filters(events, bars, min_adv=1_000_000, min_price=100.0, max_gap=0.10)
    assert set(out["symbol"]) == {"GOOD.T"}  # CHEAP dropped (price/ADV), NEG dropped (score<=0)
    assert "next_open_price" in out.columns
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/events/test_filters.py -v`
Expected: FAIL (`ModuleNotFoundError: src.events.filters`).

- [ ] **Step 3: Write minimal implementation**

```python
# src/events/filters.py
from __future__ import annotations

import pandas as pd


def _next_trading_day_open(bar_df: pd.DataFrame, disclose_date: pd.Timestamp):
    after = bar_df.loc[bar_df.index > disclose_date]
    if after.empty:
        return None, None
    first = after.iloc[0]
    return after.index[0], float(first["Open"])


def apply_filters(
    events: pd.DataFrame,
    bars: dict[str, pd.DataFrame],
    *,
    min_adv: float = 0.0,
    min_price: float = 0.0,
    max_gap: float = 0.10,
    adv_lookback: int = 20,
) -> pd.DataFrame:
    kept = []
    for _, e in events.iterrows():
        if e["event_score"] <= 0:  # positive-only (long)
            continue
        sym = e["symbol"]
        bar_df = bars.get(sym)
        if bar_df is None or bar_df.empty:
            continue
        hist = bar_df.loc[bar_df.index <= e["disclose_date"]]
        if len(hist) < adv_lookback:
            continue
        disclose_close = float(hist.iloc[-1]["Close"])
        if disclose_close < min_price:
            continue
        adv = float((hist["Close"] * hist["Volume"]).iloc[-adv_lookback:].mean())
        if adv < min_adv:
            continue
        next_date, next_open = _next_trading_day_open(bar_df, e["disclose_date"])
        if next_date is None:
            continue
        gap = abs(next_open - disclose_close) / disclose_close if disclose_close else 1.0
        if gap > max_gap:
            continue
        row = e.to_dict()
        row["next_open_date"] = next_date
        row["next_open_price"] = next_open
        kept.append(row)
    cols = list(events.columns) + ["next_open_date", "next_open_price"]
    if not kept:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(kept).reset_index(drop=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/events/test_filters.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/events/filters.py tests/events/test_filters.py
git commit -m "feat: add liquidity/price/gap/positive-only event filters for Strategy A"
```

---

### Task 4: `event_runner` — event-driven backtest with timed exits

**Files:**
- Create: `src/engine/event_runner.py`
- Create: `tests/engine/test_event_runner.py`

**Interfaces:**
- Consumes: filtered events from Task 3 (with `symbol, disclose_date, next_open_date, next_open_price, event_score`), `bars: dict[str, pd.DataFrame]` daily OHLCV, and the commission rate from `src/engine/commission.py`.
- Produces: `run_event_backtest(events, bars, *, hold_days=5, stop_loss_pct=0.08, take_profit_pct=0.15, commission=0.001, slippage=0.0005, capital_per_trade=100_000.0) -> pd.DataFrame` returning one row per trade with columns `["symbol", "entry_date", "entry_price", "exit_date", "exit_price", "exit_reason", "gross_return", "net_return"]`. `exit_reason` in `{"time", "stop", "take"}`. Enforces no-duplicate-stacking: a symbol already held does not open a second position until its current position exits.

- [ ] **Step 1: Write the failing tests**

```python
# tests/engine/test_event_runner.py
import pandas as pd

from src.engine.event_runner import run_event_backtest


def _bars(dates, prices):
    idx = pd.to_datetime(dates)
    return pd.DataFrame(
        {"Open": prices, "High": prices, "Low": prices, "Close": prices, "Volume": [1] * len(prices)},
        index=idx,
    )


def test_time_exit_after_hold_days_uses_next_open_entry():
    dates = ["2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16",
             "2024-05-17", "2024-05-20", "2024-05-21"]
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 110.0, 111.0]
    bars = {"AAA.T": _bars(dates, prices)}
    events = pd.DataFrame([{
        "symbol": "AAA.T", "disclose_date": pd.Timestamp("2024-05-10"),
        "next_open_date": pd.Timestamp("2024-05-13"), "next_open_price": 100.0,
        "event_score": 1.5,
    }])
    trades = run_event_backtest(events, bars, hold_days=5, stop_loss_pct=0.9,
                                take_profit_pct=0.9, commission=0.0, slippage=0.0)
    t = trades.iloc[0]
    assert t["entry_price"] == 100.0
    assert t["entry_date"] == pd.Timestamp("2024-05-13")
    assert t["exit_reason"] == "time"
    assert t["exit_date"] == pd.Timestamp("2024-05-20")  # 5 trading days after entry
    assert round(t["gross_return"], 4) == round((110.0 - 100.0) / 100.0, 4)


def test_stop_loss_triggers_before_time_exit():
    dates = ["2024-05-13", "2024-05-14", "2024-05-15"]
    prices = [100.0, 90.0, 95.0]  # -10% on day 2
    bars = {"AAA.T": _bars(dates, prices)}
    events = pd.DataFrame([{
        "symbol": "AAA.T", "disclose_date": pd.Timestamp("2024-05-10"),
        "next_open_date": pd.Timestamp("2024-05-13"), "next_open_price": 100.0,
        "event_score": 1.5,
    }])
    trades = run_event_backtest(events, bars, hold_days=5, stop_loss_pct=0.08,
                                take_profit_pct=0.9, commission=0.0, slippage=0.0)
    assert trades.iloc[0]["exit_reason"] == "stop"


def test_no_duplicate_stacking_within_hold():
    dates = ["2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16",
             "2024-05-17", "2024-05-20", "2024-05-21", "2024-05-22"]
    prices = [100.0] * 8
    bars = {"AAA.T": _bars(dates, prices)}
    events = pd.DataFrame([
        {"symbol": "AAA.T", "disclose_date": pd.Timestamp("2024-05-10"),
         "next_open_date": pd.Timestamp("2024-05-13"), "next_open_price": 100.0, "event_score": 1.5},
        {"symbol": "AAA.T", "disclose_date": pd.Timestamp("2024-05-13"),
         "next_open_date": pd.Timestamp("2024-05-14"), "next_open_price": 100.0, "event_score": 1.5},
    ])
    trades = run_event_backtest(events, bars, hold_days=5, commission=0.0, slippage=0.0)
    # Second event fires while first position is still open -> only one trade.
    assert len(trades) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_event_runner.py -v`
Expected: FAIL (`ModuleNotFoundError: src.engine.event_runner`).

- [ ] **Step 3: Write minimal implementation**

```python
# src/engine/event_runner.py
from __future__ import annotations

import pandas as pd


def _future_bars(bar_df: pd.DataFrame, entry_date: pd.Timestamp) -> pd.DataFrame:
    return bar_df.loc[bar_df.index >= entry_date]


def run_event_backtest(
    events: pd.DataFrame,
    bars: dict[str, pd.DataFrame],
    *,
    hold_days: int = 5,
    stop_loss_pct: float = 0.08,
    take_profit_pct: float = 0.15,
    commission: float = 0.001,
    slippage: float = 0.0005,
    capital_per_trade: float = 100_000.0,
) -> pd.DataFrame:
    trades = []
    # Track, per symbol, the date until which a position is open (inclusive).
    held_until: dict[str, pd.Timestamp] = {}
    events_sorted = events.sort_values("next_open_date").reset_index(drop=True)
    for _, e in events_sorted.iterrows():
        sym = e["symbol"]
        entry_date = e["next_open_date"]
        if sym in held_until and entry_date <= held_until[sym]:
            continue  # no duplicate stacking
        bar_df = bars.get(sym)
        if bar_df is None or entry_date not in bar_df.index:
            continue
        entry_price = float(e["next_open_price"]) * (1 + slippage)
        fwd = _future_bars(bar_df, entry_date)
        if len(fwd) < 2:
            continue
        exit_reason, exit_date, exit_price = "time", None, None
        # iterate forward bars after entry (position holds from day after entry)
        for i in range(1, len(fwd)):
            bar = fwd.iloc[i]
            ret = (float(bar["Close"]) - entry_price) / entry_price
            if ret <= -stop_loss_pct:
                exit_reason, exit_date, exit_price = "stop", fwd.index[i], float(bar["Close"])
                break
            if ret >= take_profit_pct:
                exit_reason, exit_date, exit_price = "take", fwd.index[i], float(bar["Close"])
                break
            if i >= hold_days:
                exit_reason, exit_date, exit_price = "time", fwd.index[i], float(bar["Close"])
                break
        if exit_date is None:  # ran out of bars before hold_days
            exit_date, exit_price = fwd.index[-1], float(fwd.iloc[-1]["Close"])
        exit_price_after_slip = exit_price * (1 - slippage)
        gross = (exit_price - entry_price) / entry_price
        net = (exit_price_after_slip - entry_price) / entry_price - 2 * commission
        held_until[sym] = exit_date
        trades.append({
            "symbol": sym, "entry_date": entry_date, "entry_price": entry_price,
            "exit_date": exit_date, "exit_price": exit_price, "exit_reason": exit_reason,
            "gross_return": gross, "net_return": net,
        })
    cols = ["symbol", "entry_date", "entry_price", "exit_date", "exit_price",
            "exit_reason", "gross_return", "net_return"]
    if not trades:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(trades)[cols]
```

Note: entry uses `next_open_price` (the NEXT day's open, from Task 3) and exits scan only bars strictly after entry — this is the structural look-ahead guard. The stop/take/time precedence is "first to trigger scanning forward".

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine/test_event_runner.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/engine/event_runner.py tests/engine/test_event_runner.py
git commit -m "feat: add event-driven backtester with timed/stop/take exits for Strategy A"
```

---

### Task 5: `event_backtest` — metrics aggregation + end-to-end integration

**Files:**
- Create: `src/research/event_backtest.py`
- Create: `tests/research/test_event_backtest.py`

**Interfaces:**
- Consumes: the trades DataFrame from Task 4, and (for the integration test) `compute_events` (Task 2), `apply_filters` (Task 3), `run_event_backtest` (Task 4).
- Produces: `summarize_trades(trades: pd.DataFrame) -> dict` returning `{"n_trades", "hit_rate", "profit_factor", "avg_net_return", "total_net_return", "max_drawdown"}`. Also `run_strategy_a(statements, bars, **params) -> dict` that chains compute_events -> apply_filters -> run_event_backtest -> summarize_trades and returns `{"trades": DataFrame, "metrics": dict}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/research/test_event_backtest.py
import pandas as pd

from src.research.event_backtest import summarize_trades, run_strategy_a


def test_summarize_trades_computes_hit_rate_and_profit_factor():
    trades = pd.DataFrame({
        "net_return": [0.10, -0.05, 0.20, -0.10],
    })
    m = summarize_trades(trades)
    assert m["n_trades"] == 4
    assert m["hit_rate"] == 0.5
    # profit factor = gross wins / gross losses = (0.10+0.20)/(0.05+0.10) = 2.0
    assert round(m["profit_factor"], 4) == 2.0


def test_summarize_trades_handles_empty():
    m = summarize_trades(pd.DataFrame(columns=["net_return"]))
    assert m["n_trades"] == 0
    assert m["hit_rate"] == 0.0


def test_run_strategy_a_end_to_end_positive_surprise_is_traded():
    # Real chain, no mocks: one strong positive-surprise name with a clean uptrend
    # must produce a profitable time-exit trade; a negative-surprise name must not trade.
    import numpy as np
    dates = pd.date_range("2024-04-01", periods=45, freq="B")
    def bars(prices):
        return pd.DataFrame(
            {"Open": prices, "High": prices, "Low": prices, "Close": prices,
             "Volume": [1_000_000] * len(prices)}, index=dates)
    up = list(np.linspace(1000, 1000, 40)) + [1000, 1010, 1020, 1030, 1040]
    statements = {
        "WIN.T": pd.DataFrame([{
            "disclose_date": dates[39], "period_end": pd.Timestamp("2024-03-31"),
            "actual_profit": 1500.0, "forecast_profit": 1000.0,
            "prev_forecast_profit": float("nan"), "yoy_prev_profit": 1000.0}]),
        "LOSE.T": pd.DataFrame([{
            "disclose_date": dates[39], "period_end": pd.Timestamp("2024-03-31"),
            "actual_profit": 700.0, "forecast_profit": 1000.0,
            "prev_forecast_profit": float("nan"), "yoy_prev_profit": 1000.0}]),
    }
    bars_map = {"WIN.T": bars(up), "LOSE.T": bars(up)}
    result = run_strategy_a(statements, bars_map, hold_days=4, min_adv=0.0,
                            min_price=0.0, max_gap=0.5, commission=0.0, slippage=0.0)
    traded = set(result["trades"]["symbol"])
    assert "WIN.T" in traded
    assert "LOSE.T" not in traded  # negative surprise -> score<=0 -> filtered
    assert result["metrics"]["n_trades"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/research/test_event_backtest.py -v`
Expected: FAIL (`ModuleNotFoundError: src.research.event_backtest`).

- [ ] **Step 3: Write minimal implementation**

```python
# src/research/event_backtest.py
from __future__ import annotations

import pandas as pd

from src.events.surprise import compute_events
from src.events.filters import apply_filters
from src.engine.event_runner import run_event_backtest


def summarize_trades(trades: pd.DataFrame) -> dict:
    n = len(trades)
    if n == 0:
        return {"n_trades": 0, "hit_rate": 0.0, "profit_factor": 0.0,
                "avg_net_return": 0.0, "total_net_return": 0.0, "max_drawdown": 0.0}
    r = trades["net_return"]
    wins = r[r > 0].sum()
    losses = -r[r < 0].sum()
    equity = (1 + r).cumprod()
    running_max = equity.cummax()
    max_dd = float(((equity - running_max) / running_max).min())
    return {
        "n_trades": n,
        "hit_rate": float((r > 0).mean()),
        "profit_factor": float(wins / losses) if losses > 0 else float("inf"),
        "avg_net_return": float(r.mean()),
        "total_net_return": float(equity.iloc[-1] - 1),
        "max_drawdown": max_dd,
    }


def run_strategy_a(
    statements: dict[str, pd.DataFrame],
    bars: dict[str, pd.DataFrame],
    *,
    hold_days: int = 5,
    min_adv: float = 0.0,
    min_price: float = 0.0,
    max_gap: float = 0.10,
    adv_lookback: int = 20,
    stop_loss_pct: float = 0.08,
    take_profit_pct: float = 0.15,
    commission: float = 0.001,
    slippage: float = 0.0005,
) -> dict:
    events = compute_events(statements)
    filtered = apply_filters(events, bars, min_adv=min_adv, min_price=min_price,
                             max_gap=max_gap, adv_lookback=adv_lookback)
    trades = run_event_backtest(filtered, bars, hold_days=hold_days,
                                stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
                                commission=commission, slippage=slippage)
    return {"trades": trades, "metrics": summarize_trades(trades)}
```

- [ ] **Step 4: Run tests to verify they pass, plus full suite**

Run: `uv run pytest tests/events/ tests/engine/test_event_runner.py tests/research/test_event_backtest.py -v && uv run pytest -q`
Expected: all PASS; full suite green, zero regressions to the existing pipeline.

- [ ] **Step 5: Commit**

```bash
git add src/research/event_backtest.py tests/research/test_event_backtest.py
git commit -m "feat: add Strategy A metrics aggregation and end-to-end backtest chain"
```

---

## Self-Review Notes

- **Spec coverage:** statements_loader (Task 1), surprise scoring + tagging + drop-rule (Task 2), the four filters incl. positive-only/liquidity/price/gap/duplicate — duplicate is enforced in the runner, Task 4 (Task 3), event-driven runner with next-day-open entry + time/stop/take exits (Task 4), metrics + end-to-end integration test (Task 5). All spec sections map to a task.
- **Look-ahead safety:** surprise uses only disclosure-date fields (Task 2); entry is `next_open_price` and exits scan only bars strictly after entry (Task 4); the end-to-end test (Task 5) exercises the real chain.
- **Subscription blocker:** documented at top and in Task 1 Step 0. Tasks 2-5 are subscription-independent and can proceed first.
- **Data-risk / field reconciliation:** Task 1's `_COLMAP` and `get_fins_statements` argument names are flagged as needing reconciliation against the captured real sample before implementation.
- **Placeholder scan:** no TBD/TODO; every code step has complete code.
- **Type consistency:** the event DataFrame schema (`symbol, disclose_date, event_type, raw_surprise, event_score`) is produced by Task 2 and consumed unchanged by Tasks 3-4; `next_open_date`/`next_open_price` added by Task 3 and consumed by Task 4; trades schema produced by Task 4 and consumed by Task 5.
- **Deferred (per spec):** TDnet, shorts, paper/live execution, NLP — no tasks, intentionally.
- **Commission reuse:** the runner takes commission/slippage as numeric params (defaults 0.001/0.0005 matching `JapanStockCommission`), not the backtrader class, because the event runner is not backtrader-based.
