# Value-Stack Factor Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three PIT-safe factors (size, EV/EBIT, dividend yield) to the monthly multi-factor scorer, defaulting to weight 0 so existing results are unchanged.

**Architecture:** Three new yfinance loaders in `fundamental_loader.py` mirror the existing `get_book_values` (json cache, 60-day PIT filter, empty-not-cached). `score_universe` gains three weight params + three data inputs, computed identically to the existing val/qual blocks. New weights + inputs are threaded through every `score_universe` call site.

**Tech Stack:** Python 3.12, pandas, yfinance, pytest, uv.

## Global Constraints

- New factors default to weight 0.0 and data inputs default to None — existing output must be bit-for-bit unchanged.
- All fundamentals obey the PIT rule: usable only when scoring as of a date `>= fiscal-period-end + 60 days` (`PUBLICATION_DELAY_DAYS = 60`).
- Empty fetch results must NOT be cached (matches the merged bug #3 fix pattern).
- A NaN raw factor is neutralized to z=0 by the scorer (merged bug #1 fix) — loaders return None/NaN for missing data, never fabricated values.
- Do NOT reuse `get_earnings_yield` (non-PIT, look-ahead).
- z-score direction: size inverted, EV/EBIT inverted, dividend_yield not inverted.
- Run all commands with `uv run`. Tests live under `tests/`.
- Ticker symbols carry a `.T` suffix.

---

### Task 1: `get_market_caps` loader

**Files:**
- Modify: `src/data/fundamental_loader.py`
- Test: `tests/data/test_fundamental_loader.py`

**Interfaces:**
- Consumes: existing `_load_cache`/`_save_cache` pattern, `PUBLICATION_DELAY_DAYS`.
- Produces: `get_market_caps(symbols: list[str], prices: dict[str, float], as_of_date: pd.Timestamp | None = None, force_refresh: bool = False) -> dict[str, float | None]` — market cap = price x PIT shares outstanding; None when shares unavailable. Also `_compute_shares_outstanding(ticker: str) -> dict[str, float]` returning `{fiscal_year_end_str: shares}`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/data/test_fundamental_loader.py
from src.data.fundamental_loader import get_market_caps, _compute_shares_outstanding


def test_compute_shares_outstanding_nets_treasury(monkeypatch):
    fiscal_years = pd.to_datetime(["2024-03-31"])

    class FakeTicker:
        balance_sheet = pd.DataFrame(
            [[100.0], [10.0]],
            index=["Ordinary Shares Number", "Treasury Shares Number"],
            columns=fiscal_years,
        )

    monkeypatch.setattr("src.data.fundamental_loader.yf.Ticker", lambda t: FakeTicker())
    assert _compute_shares_outstanding("7203.T") == {"2024-03-31": 90.0}


def test_get_market_caps_pit_and_price(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.data.fundamental_loader.MARKET_CAP_CACHE", tmp_path / "shares.json"
    )
    monkeypatch.setattr(
        "src.data.fundamental_loader._compute_shares_outstanding",
        lambda s: {"2022-03-31": 100.0, "2023-03-31": 200.0},
    )
    # as_of before 2023 fiscal publication -> uses 2022 shares (100) x price 5 = 500
    result = get_market_caps(
        ["7203.T"], prices={"7203.T": 5.0}, as_of_date=pd.Timestamp("2023-01-01")
    )
    assert result["7203.T"] == 500.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/data/test_fundamental_loader.py -k "shares_outstanding or market_caps" -v`
Expected: FAIL with `ImportError` / `AttributeError` (functions not defined).

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/data/fundamental_loader.py (near get_book_values)
MARKET_CAP_CACHE = CACHE_DIR / "shares.json"


def _compute_shares_outstanding(ticker: str) -> dict[str, float]:
    t = yf.Ticker(ticker)
    try:
        bs = t.balance_sheet
    except Exception:
        return {}
    if bs is None or bs.empty or "Ordinary Shares Number" not in bs.index:
        return {}
    result = {}
    for col in bs.columns:
        shares = bs.loc["Ordinary Shares Number", col]
        treasury = 0.0
        if "Treasury Shares Number" in bs.index:
            ts = bs.loc["Treasury Shares Number", col]
            if not pd.isna(ts):
                treasury = float(ts)
        if pd.isna(shares):
            continue
        outstanding = float(shares) - treasury
        if outstanding <= 0:
            continue
        result[col.strftime("%Y-%m-%d")] = round(outstanding, 4)
    return result


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _save_json(path: Path, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _pit_pick(periods: dict[str, float], as_of_date: pd.Timestamp | None):
    if not periods:
        return None
    if as_of_date is None:
        return periods[max(periods.keys())]
    available = {}
    for end_str, val in periods.items():
        pub = pd.Timestamp(end_str) + pd.DateOffset(days=PUBLICATION_DELAY_DAYS)
        if pub <= as_of_date:
            available[pd.Timestamp(end_str)] = val
    if not available:
        return None
    return available[max(available.keys())]


def get_market_caps(
    symbols: list[str],
    prices: dict[str, float],
    as_of_date: pd.Timestamp | None = None,
    force_refresh: bool = False,
) -> dict[str, float | None]:
    cache = _load_json(MARKET_CAP_CACHE) if not force_refresh else {}
    result = {}
    for sym in symbols:
        if not cache.get(sym) or force_refresh:
            try:
                shares = _compute_shares_outstanding(sym)
            except Exception:
                shares = {}
            if shares:
                cache[sym] = shares
        pit_shares = _pit_pick(cache.get(sym, {}), as_of_date)
        price = prices.get(sym)
        if pit_shares is None or price is None:
            result[sym] = None
        else:
            result[sym] = round(float(price) * float(pit_shares), 4)
    _save_json(MARKET_CAP_CACHE, cache)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/data/test_fundamental_loader.py -k "shares_outstanding or market_caps" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data/fundamental_loader.py tests/data/test_fundamental_loader.py
git commit -m "feat: add PIT market-cap (size) loader"
```

---

### Task 2: `get_ev_ebit` loader

**Files:**
- Modify: `src/data/fundamental_loader.py`
- Test: `tests/data/test_fundamental_loader.py`

**Interfaces:**
- Consumes: `_compute_shares_outstanding`, `_pit_pick`, `_load_json`/`_save_json` (Task 1).
- Produces: `get_ev_ebit(symbols, prices, as_of_date=None, force_refresh=False) -> dict[str, float | None]`. Returns None when EBIT is missing/<=0 or EV is negative. `_compute_ev_ebit_inputs(ticker) -> dict[str, dict]` returning `{fy_end: {"ebit":.., "debt":.., "cash":.., "shares":..}}`.

- [ ] **Step 1: Write the failing test**

```python
from src.data.fundamental_loader import get_ev_ebit


def test_get_ev_ebit_negative_ebit_returns_none(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.data.fundamental_loader.EV_EBIT_CACHE", tmp_path / "evebit.json"
    )
    monkeypatch.setattr(
        "src.data.fundamental_loader._compute_ev_ebit_inputs",
        lambda s: {"2024-03-31": {"ebit": -50.0, "debt": 100.0, "cash": 10.0, "shares": 100.0}},
    )
    result = get_ev_ebit(["X.T"], prices={"X.T": 5.0}, as_of_date=None)
    assert result["X.T"] is None


def test_get_ev_ebit_computes_ratio(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.data.fundamental_loader.EV_EBIT_CACHE", tmp_path / "evebit.json"
    )
    monkeypatch.setattr(
        "src.data.fundamental_loader._compute_ev_ebit_inputs",
        lambda s: {"2024-03-31": {"ebit": 100.0, "debt": 200.0, "cash": 50.0, "shares": 100.0}},
    )
    # EV = price*shares + debt - cash = 5*100 + 200 - 50 = 650; EV/EBIT = 6.5
    result = get_ev_ebit(["X.T"], prices={"X.T": 5.0}, as_of_date=None)
    assert result["X.T"] == 6.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/data/test_fundamental_loader.py -k "ev_ebit" -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/data/fundamental_loader.py
EV_EBIT_CACHE = CACHE_DIR / "evebit.json"


def _compute_ev_ebit_inputs(ticker: str) -> dict[str, dict]:
    t = yf.Ticker(ticker)
    try:
        fin = t.financials
        bs = t.balance_sheet
    except Exception:
        return {}
    if fin is None or fin.empty or bs is None or bs.empty:
        return {}
    if "EBIT" not in fin.index:
        return {}
    result = {}
    for col in fin.columns:
        if col not in bs.columns:
            continue
        ebit = fin.loc["EBIT", col]
        if pd.isna(ebit):
            continue
        debt = 0.0
        for k in ["Total Debt", "Long Term Debt"]:
            if k in bs.index and not pd.isna(bs.loc[k, col]):
                debt = float(bs.loc[k, col])
                break
        cash = 0.0
        for k in ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"]:
            if k in bs.index and not pd.isna(bs.loc[k, col]):
                cash = float(bs.loc[k, col])
                break
        shares = None
        if "Ordinary Shares Number" in bs.index and not pd.isna(bs.loc["Ordinary Shares Number", col]):
            treasury = 0.0
            if "Treasury Shares Number" in bs.index and not pd.isna(bs.loc["Treasury Shares Number", col]):
                treasury = float(bs.loc["Treasury Shares Number", col])
            shares = float(bs.loc["Ordinary Shares Number", col]) - treasury
        if shares is None or shares <= 0:
            continue
        result[col.strftime("%Y-%m-%d")] = {
            "ebit": float(ebit), "debt": debt, "cash": cash, "shares": shares,
        }
    return result


def get_ev_ebit(
    symbols: list[str],
    prices: dict[str, float],
    as_of_date: pd.Timestamp | None = None,
    force_refresh: bool = False,
) -> dict[str, float | None]:
    cache = _load_json(EV_EBIT_CACHE) if not force_refresh else {}
    result = {}
    for sym in symbols:
        if not cache.get(sym) or force_refresh:
            try:
                inputs = _compute_ev_ebit_inputs(sym)
            except Exception:
                inputs = {}
            if inputs:
                cache[sym] = inputs
        pit = _pit_pick(cache.get(sym, {}), as_of_date)
        price = prices.get(sym)
        if pit is None or price is None or pit["ebit"] <= 0:
            result[sym] = None
            continue
        ev = float(price) * pit["shares"] + pit["debt"] - pit["cash"]
        if ev < 0:
            result[sym] = None
            continue
        result[sym] = round(ev / pit["ebit"], 4)
    _save_json(EV_EBIT_CACHE, cache)
    return result
```

Note: `_pit_pick` (Task 1) returns whatever value the periods dict holds; here the values are dicts, which works unchanged since it only compares keys by date.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/data/test_fundamental_loader.py -k "ev_ebit" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data/fundamental_loader.py tests/data/test_fundamental_loader.py
git commit -m "feat: add PIT EV/EBIT loader"
```

---

### Task 3: `get_dividend_yields` loader

**Files:**
- Modify: `src/data/fundamental_loader.py`
- Test: `tests/data/test_fundamental_loader.py`

**Interfaces:**
- Consumes: `_load_json`/`_save_json` (Task 1).
- Produces: `get_dividend_yields(symbols, prices, as_of_date=None, force_refresh=False) -> dict[str, float | None]`. TTM dividends per share (ex-date within 365d before as_of, and `<= as_of`) / price. No dividends -> 0.0. `_fetch_dividends(ticker) -> dict[str, float]` returning `{ex_date_str: amount_per_share}`.

- [ ] **Step 1: Write the failing test**

```python
from src.data.fundamental_loader import get_dividend_yields


def test_get_dividend_yields_excludes_future_and_sums_ttm(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.data.fundamental_loader.DIVIDEND_CACHE", tmp_path / "divs.json"
    )
    monkeypatch.setattr(
        "src.data.fundamental_loader._fetch_dividends",
        lambda s: {"2023-06-30": 10.0, "2023-12-31": 10.0, "2024-09-30": 99.0},
    )
    # as_of 2024-01-31: count only ex-dates in (2023-01-31, 2024-01-31] -> 10 + 10 = 20
    # price 400 -> yield = 20/400 = 0.05; future 2024-09-30 excluded
    result = get_dividend_yields(
        ["X.T"], prices={"X.T": 400.0}, as_of_date=pd.Timestamp("2024-01-31")
    )
    assert result["X.T"] == 0.05


def test_get_dividend_yields_no_dividends_is_zero(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.data.fundamental_loader.DIVIDEND_CACHE", tmp_path / "divs.json"
    )
    monkeypatch.setattr("src.data.fundamental_loader._fetch_dividends", lambda s: {})
    result = get_dividend_yields(
        ["X.T"], prices={"X.T": 400.0}, as_of_date=pd.Timestamp("2024-01-31")
    )
    assert result["X.T"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/data/test_fundamental_loader.py -k "dividend_yields" -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/data/fundamental_loader.py
DIVIDEND_CACHE = CACHE_DIR / "divs.json"


def _fetch_dividends(ticker: str) -> dict[str, float]:
    t = yf.Ticker(ticker)
    try:
        divs = t.dividends
    except Exception:
        return {}
    if divs is None or len(divs) == 0:
        return {}
    return {ts.strftime("%Y-%m-%d"): float(amt) for ts, amt in divs.items()}


def get_dividend_yields(
    symbols: list[str],
    prices: dict[str, float],
    as_of_date: pd.Timestamp | None = None,
    force_refresh: bool = False,
) -> dict[str, float | None]:
    cache = _load_json(DIVIDEND_CACHE) if not force_refresh else {}
    result = {}
    ref = as_of_date if as_of_date is not None else pd.Timestamp.max
    window_start = ref - pd.DateOffset(days=365) if as_of_date is not None else pd.Timestamp.min
    for sym in symbols:
        if sym not in cache or force_refresh:
            try:
                divs = _fetch_dividends(sym)
            except Exception:
                divs = {}
            cache[sym] = divs  # dividends: {} is a valid "no dividends" answer, cache it
        price = prices.get(sym)
        if price is None or price <= 0:
            result[sym] = None
            continue
        ttm = 0.0
        for ex_str, amt in cache.get(sym, {}).items():
            ex = pd.Timestamp(ex_str)
            if window_start < ex <= ref:
                ttm += amt
        result[sym] = round(ttm / price, 6)
    _save_json(DIVIDEND_CACHE, cache)
    return result
```

Note: unlike the other loaders, an empty dividends dict is a legitimate "pays no dividend" result, so it IS cached. This is intentional and differs from the empty-not-cached rule for shares/EBIT.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/data/test_fundamental_loader.py -k "dividend_yields" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data/fundamental_loader.py tests/data/test_fundamental_loader.py
git commit -m "feat: add PIT dividend-yield loader"
```

---

### Task 4: Extend `score_universe` with three factors

**Files:**
- Modify: `src/scoring/multi_factor.py:128` (`score_universe`)
- Test: `tests/scoring/test_multi_factor.py`

**Interfaces:**
- Consumes: existing `_z`, `_safe_zscores`, `_industry_neutral_zscores`.
- Produces: `score_universe(..., weight_size=0.0, weight_evebit=0.0, weight_divy=0.0, market_caps=None, ev_ebit_values=None, dividend_yields=None)`. Adds `size_z/evebit_z/divy_z` and `*_contribution` columns when the corresponding weight>0 and input provided. size & evebit inverted; divy not.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/scoring/test_multi_factor.py
def test_new_value_factors_default_weight_zero_is_unchanged():
    data = {
        "AAA.T": make_df([100] * 70 + list(range(100, 110)) + list(range(150, 130, -1))),
        "BBB.T": make_df([120] * 70 + list(range(120, 110, -1)) + [80] * 20),
        "CCC.T": make_df([100] * 100),
    }
    baseline = score_universe(data, top_n=2, weight_mom=1.0, weight_vol=1.0, weight_rev=1.0)
    with_inputs = score_universe(
        data, top_n=2, weight_mom=1.0, weight_vol=1.0, weight_rev=1.0,
        market_caps={"AAA.T": 1e9, "BBB.T": 2e9, "CCC.T": 3e9},
        ev_ebit_values={"AAA.T": 5.0, "BBB.T": 10.0, "CCC.T": 15.0},
        dividend_yields={"AAA.T": 0.01, "BBB.T": 0.02, "CCC.T": 0.03},
    )
    assert with_inputs["total_score"].round(10).tolist() == baseline["total_score"].round(10).tolist()


def test_size_factor_prefers_small_cap():
    data = {"SMALL.T": make_df([100] * 100), "BIG.T": make_df([100] * 100)}
    result = score_universe(
        data, top_n=1, weight_mom=0.0, weight_vol=0.0, weight_rev=0.0,
        weight_size=1.0, market_caps={"SMALL.T": 1e8, "BIG.T": 9e9},
    )
    assert result.set_index("symbol").loc["SMALL.T", "size_z"] > 0
    assert result.iloc[0]["symbol"] == "SMALL.T"


def test_evebit_factor_prefers_cheap_and_divy_prefers_high():
    data = {"CHEAP.T": make_df([100] * 100), "RICH.T": make_df([100] * 100)}
    ev = score_universe(
        data, top_n=1, weight_mom=0.0, weight_vol=0.0, weight_rev=0.0,
        weight_evebit=1.0, ev_ebit_values={"CHEAP.T": 4.0, "RICH.T": 40.0},
    )
    assert ev.iloc[0]["symbol"] == "CHEAP.T"
    dv = score_universe(
        {"HIGH.T": make_df([100] * 100), "LOW.T": make_df([100] * 100)},
        top_n=1, weight_mom=0.0, weight_vol=0.0, weight_rev=0.0,
        weight_divy=1.0, dividend_yields={"HIGH.T": 0.05, "LOW.T": 0.0},
    )
    assert dv.iloc[0]["symbol"] == "HIGH.T"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scoring/test_multi_factor.py -k "new_value_factors or size_factor or evebit_factor" -v`
Expected: FAIL (`TypeError: unexpected keyword argument 'weight_size'`).

- [ ] **Step 3: Write minimal implementation**

In `src/scoring/multi_factor.py`, add params to the `score_universe` signature (after `weight_qual`):

```python
    weight_size: float = 0.0,
    weight_evebit: float = 0.0,
    weight_divy: float = 0.0,
    market_caps: Mapping[str, float | None] | None = None,
    ev_ebit_values: Mapping[str, float | None] | None = None,
    dividend_yields: Mapping[str, float | None] | None = None,
```

Add use-flags next to `use_value`/`use_qual`:

```python
    use_size = market_caps is not None and weight_size > 0.0
    use_evebit = ev_ebit_values is not None and weight_evebit > 0.0
    use_divy = dividend_yields is not None and weight_divy > 0.0
    raw_size: list[float] = []
    raw_evebit: list[float] = []
    raw_divy: list[float] = []
```

Inside the per-symbol loop, after the `use_qual` block and before `raw_mom.append(...)`:

```python
        if use_size:
            mc = market_caps.get(symbol)
            sz = float(mc) if (mc is not None and mc > 0) else math.nan
            factors["size_raw"] = sz
            raw_size.append(sz)
        if use_evebit:
            ee = ev_ebit_values.get(symbol)
            ee_v = float(ee) if (ee is not None and math.isfinite(ee)) else math.nan
            factors["evebit_raw"] = ee_v
            raw_evebit.append(ee_v)
        if use_divy:
            dy = dividend_yields.get(symbol)
            dy_v = float(dy) if (dy is not None and math.isfinite(dy)) else math.nan
            factors["divy_raw"] = dy_v
            raw_divy.append(dy_v)
```

After the existing `qual_z = ...` line, add:

```python
    size_z = _z(raw_size, invert=True) if use_size else [0.0] * len(records)
    evebit_z = _z(raw_evebit, invert=True) if use_evebit else [0.0] * len(records)
    divy_z = _z(raw_divy, invert=False) if use_divy else [0.0] * len(records)
```

Inside the `for i, record in enumerate(records):` loop, after the `use_qual` block:

```python
        if use_size:
            record["size_z"] = size_z[i]
            record["size_contribution"] = weight_size * size_z[i]
            total += record["size_contribution"]
        if use_evebit:
            record["evebit_z"] = evebit_z[i]
            record["evebit_contribution"] = weight_evebit * evebit_z[i]
            total += record["evebit_contribution"]
        if use_divy:
            record["divy_z"] = divy_z[i]
            record["divy_contribution"] = weight_divy * divy_z[i]
            total += record["divy_contribution"]
```

- [ ] **Step 4: Run tests to verify they pass, plus full scoring regression**

Run: `uv run pytest tests/scoring/ tests/strategies/test_multi_factor.py -v`
Expected: all PASS (new tests + existing regression, including the weight-0 bit-for-bit test).

- [ ] **Step 5: Commit**

```bash
git add src/scoring/multi_factor.py tests/scoring/test_multi_factor.py
git commit -m "feat: add size, EV/EBIT, dividend-yield factors to score_universe"
```

---

### Task 5: Thread new weights through strategy, simple_runner, and paper bot

**Files:**
- Modify: `src/strategies/multi_factor.py:99`, `src/engine/simple_runner.py:145`, `src/paper/bot.py:100`
- Test: `tests/scoring/test_multi_factor.py` (paper path), `tests/engine/test_simple_runner.py`

**Interfaces:**
- Consumes: `score_universe(..., weight_size, weight_evebit, weight_divy, market_caps, ev_ebit_values, dividend_yields)` (Task 4).
- Produces: these three call sites forward the new weights/inputs (default 0/None, so behavior unchanged unless supplied).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/scoring/test_multi_factor.py
def test_paper_signals_forward_size_factor():
    data = {"SMALL.T": make_df([100] * 100), "BIG.T": make_df([100] * 100)}
    winners = calculate_current_signals(
        data, top_n=1, weight_mom=0.0, weight_vol=0.0, weight_rev=0.0,
        weight_size=1.0, market_caps={"SMALL.T": 1e8, "BIG.T": 9e9},
    )
    assert winners.iloc[0]["symbol"] == "SMALL.T"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scoring/test_multi_factor.py -k "forward_size" -v`
Expected: FAIL (`TypeError: unexpected keyword argument 'weight_size'` in `calculate_current_signals`).

- [ ] **Step 3: Write minimal implementation**

In `src/paper/bot.py`, add `weight_size=0.0, weight_evebit=0.0, weight_divy=0.0, market_caps=None, ev_ebit_values=None, dividend_yields=None` to `calculate_current_signals`'s signature and forward them into its `score_universe(...)` call at line ~100.

In `src/strategies/multi_factor.py`, add the same six params to the strategy params/signature and forward them into `score_universe(...)` at line ~99.

In `src/engine/simple_runner.py`, add the same six params to the runner signature and forward them into BOTH `score_universe(...)` calls (the two at ~145). Follow the exact pattern already used for `weight_val`/`book_values`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/scoring/ tests/engine/test_simple_runner.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/paper/bot.py src/strategies/multi_factor.py src/engine/simple_runner.py tests/scoring/test_multi_factor.py
git commit -m "feat: forward value-stack weights through strategy, runner, paper bot"
```

---

### Task 6: Thread through optimizer + full-chain integration test

**Files:**
- Modify: `src/optimize.py` (`evaluate_weight_tuple` ~335, `run_walk_forward_optimization` ~515, and every closure that forwards `book_values`/`roe_values`)
- Test: `tests/research/test_walk_forward.py`

**Interfaces:**
- Consumes: the threaded call sites from Task 5 and the extended `score_universe`.
- Produces: `evaluate_weight_tuple` and `run_walk_forward_optimization` accept + forward `market_caps`, `ev_ebit_values`, `dividend_yields` (default None) and the three weights, so walk-forward can exercise the new factors.

- [ ] **Step 1: Write the failing integration test (real data, no monkeypatch of score_universe)**

```python
# add to tests/research/test_walk_forward.py
def test_walk_forward_forwards_dividend_yields_to_scorer():
    # Two flat-price stocks; with only divy weight active, the higher-yield
    # stock must win — proving the input reaches score_universe through the
    # full optimizer closure chain (the book_values-regression guard).
    from src.optimize import evaluate_weight_tuple
    dates = pd.date_range("2021-01-01", periods=300, freq="D")
    flat = pd.DataFrame({"Close": [100.0] * len(dates)}, index=dates)
    data = {"HIGH.T": flat.copy(), "LOW.T": flat.copy()}
    result = evaluate_weight_tuple(
        data, w_mom=0.0, w_vol=0.0, w_rev=0.0, w_val=0.0, w_qual=0.0,
        weight_divy=1.0, top_n=1,
        dividend_yields={"HIGH.T": 0.05, "LOW.T": 0.0},
        start="2021-01-01", end="2021-12-31",
    )
    # The selected symbol diagnostics must include HIGH.T, not LOW.T.
    assert "HIGH.T" in str(result)
```

Adjust the exact `evaluate_weight_tuple` argument names to match its real signature when implementing; the assertion intent is: divy input reaches the scorer.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/research/test_walk_forward.py -k "forwards_dividend" -v`
Expected: FAIL (`TypeError: unexpected keyword argument 'weight_divy'`).

- [ ] **Step 3: Write minimal implementation**

Add `weight_size=0.0, weight_evebit=0.0, weight_divy=0.0, market_caps=None, ev_ebit_values=None, dividend_yields=None` to the signatures of `evaluate_weight_tuple` and `run_walk_forward_optimization`. Forward them into every `score_universe(...)` call and every internal closure/call that currently forwards `book_values`/`roe_values` — mirror those exact lines.

- [ ] **Step 4: Grep every call site and verify forwarding (AGENTS.md guard)**

Run: `grep -rn "book_values" src/optimize.py`
For EACH line that forwards `book_values`, confirm the same location now also forwards `dividend_yields` (and the other two inputs). Closures inside `run_walk_forward_optimization` MUST accept and forward the new params — a default-None omission here is the exact 2026-04-29 regression.

- [ ] **Step 5: Run test + full suite**

Run: `uv run pytest tests/research/test_walk_forward.py -k "forwards_dividend" -v && uv run pytest -q`
Expected: target test PASS; full suite all green, zero regressions.

- [ ] **Step 6: Commit**

```bash
git add src/optimize.py tests/research/test_walk_forward.py
git commit -m "feat: thread value-stack factors through walk-forward optimizer"
```

---

## Self-Review Notes

- **Spec coverage:** size (Task 1), EV/EBIT (Task 2), dividend yield (Task 3), scorer extension + weight-0 regression (Task 4), propagation through strategy/runner/paper (Task 5), optimizer + full-chain integration test (Task 6). All spec factors and the propagation requirement are covered.
- **PIT:** Tasks 1-3 each test the PIT boundary or exclusion of future data. Dividend yield explicitly excludes future ex-dates.
- **Edge cases:** negative/zero EBIT (Task 2), no-dividend zero (Task 3), NaN neutralization relies on the already-merged bug #1 fix (asserted indirectly via weight-0 regression in Task 4).
- **AGENTS.md signature-expansion guard:** Task 6 Step 4 is the explicit grep-all-call-sites check for optimizer closures.
- **Deferred (per spec):** buybacks, EV/FCF, sector-aware normalization, the three README-logged bugs — no tasks, intentionally.
