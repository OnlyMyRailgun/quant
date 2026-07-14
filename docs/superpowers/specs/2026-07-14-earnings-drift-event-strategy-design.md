# Earnings / Guidance Surprise Drift Event Strategy (Strategy A) Design

Date: 2026-07-14

## Goal

Add a new, self-contained **event-driven, long-only** research strategy that trades
the post-announcement drift after Japanese earnings and guidance disclosures
(the report's "Strategy A"). The strategy scores each disclosure by a quantitative
financial *surprise*, enters at the **next trading day's open** after disclosure, and
exits on a time stop, take-profit, or stop-loss.

This strategy runs on a **new event-driven backtester** and shares nothing with the
existing monthly cross-sectional multi-factor pipeline other than the Japan commission
model.

## Why This Slice

The existing repo already implements the report's Strategy C (monthly multi-factor,
long-only) as `UniversalMultiFactor` + `src/scoring/multi_factor.py`. Strategy A is
genuinely absent: there is no disclosure/earnings event data source, no surprise
scoring, and no event-driven execution path. Per the report, A has the strongest and
most durable edge (global PEAD evidence) but a different execution model than C, so it
warrants its own subsystem and its own spec.

## Locked Design Parameters

These were decided during brainstorming and are fixed for v1:

| Dimension | Decision |
|---|---|
| Scope | Strategy A only. C-enhancement is a separate later spec. |
| Data source | J-Quants `/fins/statements` as the single v1 source (event timing + surprise inputs both come from here). |
| Event tagging | Quantitative financial *surprise* only — **no Japanese-text NLP** in v1. |
| Direction | **Long-only**. Shorts (and buyback/dividend events needing TDnet) are deferred to v2. |
| Entry | **Next trading day's open** after disclosure. |
| Engine | New dedicated **event-driven backtester**. |

## Non-Goals (v1)

- Does NOT modify `src/scoring/multi_factor.py`, `src/strategies/multi_factor.py`,
  the `simple`/`vectorbt`/`backtrader` engines, or paper-trading defaults.
- Does NOT add an `event_mode` branch to the existing monthly engine.
- Does NOT integrate TDnet (deferred to v2 for buyback / dividend-revision events).
- Does NOT trade shorts (avoids Japan uptick / borrow-availability modeling).
- Does NOT add live/paper execution for A in v1 — research/backtest only.
- Does NOT do Japanese-language NLP classification.

## Architecture

Four independent, individually testable units. Zero coupling to the monthly pipeline
except the reused `JapanStockCommission`.

```
src/data/statements_loader.py   -> fetch /fins/statements, parquet cache
        |  (statement rows + disclosure timestamps)
        v
src/events/surprise.py          -> compute surprise scores, tag + filter events (pure)
        |  (event list: symbol, disclose_date, event_type, score)
        v
src/engine/event_runner.py      -> event-driven backtest: next-day-open entry -> timed exit
        |  (per-trade P&L + equity curve)
        v
src/research/event_backtest.py  -> aggregate hit-rate/PF/Sharpe/MDD, robustness hooks
```

### Unit boundaries

| Unit | Responsibility | Input -> Output | Depends on |
|---|---|---|---|
| `statements_loader` | Fetch financial statements, reusing the existing `jquantsapi.ClientV2` + parquet cache + exponential-backoff retry + `.T`-stripping conventions from `jquants_loader.py` | tickers, start, end -> `{symbol: DataFrame(disclose_date, actual profit, company forecast, guidance revision)}` | jquantsapi |
| `surprise` | Pure functions: compute surprise, tag event type, apply filters | statements df -> event list | none (pure pandas) |
| `event_runner` | Event-driven backtest: next-day-open entry, independent per-trade timed exit | event list + daily bars -> per-trade P&L + equity | existing `JapanStockCommission` |
| `event_backtest` | Aggregate metrics, attach robustness / regime-break checks | backtest result -> metrics + diagnostics | reuse `src/research/` utilities |

## Signal Definition (`surprise.py`)

### Event types (v1, all from `/fins/statements`)

| Type | Trigger | Direction |
|---|---|---|
| earnings surprise | actual recurring/net profit vs **prior company forecast**, or vs same period last year (YoY) | positive surprise -> long |
| guidance revision | this disclosure's **guidance revision amount** (upward) | upward -> long |

v1 takes **positive-only** events (long-only). Shorts, buybacks, dividend revisions
are deferred to v2.

### Surprise scoring

```
earnings_surprise = (actual_profit - forecast_profit) / |forecast_profit|
guidance_surprise = (new_forecast   - prev_forecast)   / |prev_forecast|
event_score       = z-score(surprise, cross-sectional / rolling window)
```

- Use **relative** revision magnitude, not absolute, so large caps do not dominate.
- If `forecast` is missing, fall back to YoY same-period comparison.
- If **both** forecast and YoY are missing, **drop the event** (never guess).

### Filters (required by the report; enforced in v1)

1. **Liquidity**: minimum 20-day ADV percentile (parameterized).
2. **Coarse tick / spread**: exclude low-price small caps (price floor, parameterized).
3. **Limit-up / gap**: if next-day open gaps from disclosure-day close beyond a
   threshold, skip (the bulk of the move is unreachable).
4. **Duplicate events**: a symbol already held does not stack a re-triggered event.

### Exit rules (`event_runner`)

- Time stop: hold **N days** (default 5, parameterized 2-8).
- ATR / spread-adjusted stop-loss (not a mechanical fixed percentage).
- Take-profit target.
- First-to-trigger wins.

## Look-Ahead Safety

- `surprise` computes scores using only data known **as of the disclosure date**.
- `event_runner` enters at the **next-day open**.
- Together this structurally prevents look-ahead — the concern that motivated the
  repo's prior look-ahead repairs.

## Data Risk

`/fins/statements` field names and the "company forecast" structure must be confirmed
against a **real API response**; fields can be missing across fiscal periods. v1 will:

- validate field presence in the loader with an explicit missing-field fallback, and
- cover the missing-field path with a test using a **real sample** (not a mock),
  per the AGENTS.md "integration test with real data" lesson.

## Testing Strategy (TDD — failing test first)

| Unit | Test type | Key cases |
|---|---|---|
| `surprise.py` | Pure unit (write first) | positive/negative surprise; forecast-missing -> YoY fallback; both-missing -> drop; z-score edges; each filter rule |
| `statements_loader.py` | Integration (real sample) | real-response field presence; missing-field fallback; parquet cache hit; `.T` stripping; 429 retry |
| `event_runner.py` | Unit + integration | next-day-open entry; N-day time exit; stop-loss precedence; no duplicate stacking within hold; **no-look-ahead** (entry uses only next-day open) |
| `event_backtest.py` | Unit | hit-rate / PF / Sharpe / MDD; regime-break sub-sampling |

**Most important**: one end-to-end integration test running the full chain with
**real (non-monkeypatched)** statements + daily data — the explicit AGENTS.md
book_values-regression lesson.

## Expected Research Range (not a return promise)

Per the report, Strategy A targets net hit-rate ~55-62%, PF ~1.20-1.50, hold 2-8 days,
under conservative cost assumptions. These are research targets to validate, not
guarantees.

## Deferred to v2

- TDnet integration for buyback / dividend-revision / capital-policy events.
- Short leg (with borrow-availability and uptick modeling).
- Paper-trading / live execution path for A.
- Japanese-text classification of disclosure titles.
