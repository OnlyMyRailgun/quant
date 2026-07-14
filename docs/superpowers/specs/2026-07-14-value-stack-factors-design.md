# Value-Stack Factor Enhancement (Strategy C) Design

Date: 2026-07-14

## Goal

Extend the existing monthly multi-factor scorer (`score_universe` in
`src/scoring/multi_factor.py`) with three additional point-in-time-safe factors from
the report's Strategy C value stack: **size (small-cap)**, **EV/EBIT**, and
**dividend yield**. This deepens the value/size tilt beyond the current lone P/B proxy
without changing any existing factor's behavior.

## Why This Slice

The repo already implements Strategy C's skeleton (`UniversalMultiFactor` + monthly
rebalance + `score_universe` with momentum, low-vol, mean-reversion, P/B, ROE). The
report and the repo's own README "Known Issues" both note that **P/B alone is a weak
value proxy** — a stronger stack needs EV/EBIT, shareholder yield, and size-aware
normalization. This slice adds three factors that are all obtainable from yfinance and
can reuse the existing 60-day point-in-time (PIT) publication-delay pattern.

Strategy A (earnings-drift, event-driven) is deferred: its single data source
(`/fins/statements`) requires a J-Quants subscription the user does not have. Its spec
is already committed (`2026-07-14-earnings-drift-event-strategy-design.md`) and will be
implemented once data access exists.

## Locked Design Parameters

Decided during brainstorming; fixed for v1:

| Dimension | Decision |
|---|---|
| Factors added | **size**, **EV/EBIT**, **dividend yield** |
| Data source | yfinance (reusing `fundamental_loader.py` conventions) |
| PIT rule | Reuse existing fiscal-period-end + 60-day publication-delay pattern |
| Direction | Long-only; new factors default to weight 0 (no behavior change) |
| Scope | Scoring + loaders only. No new engine, no A, no shorts. |

## Non-Goals (v1)

- Does NOT change any existing factor's raw computation, z-score direction, or default
  weight. New factors default to weight 0 so current results are bit-for-bit unchanged.
- Does NOT touch the event-driven / A pipeline.
- Does NOT add buyback data to dividend yield — yfinance buyback data is unreliable, so
  "shareholder yield" is scoped down to **dividend yield only** in v1.
- Does NOT rework the deferred bugs logged in README Known Issues (treasury
  double-subtraction, non-PIT `get_earnings_yield`, empty-universe schema).
- Does NOT reuse the existing non-PIT `get_earnings_yield` for anything.

## Factor Definitions

All three reuse the existing 60-day PIT pattern: a fundamental from fiscal-period-end
`E` is only usable when scoring as of a date `>= E + 60 days`.

| Factor | Definition | Direction | PIT handling |
|---|---|---|---|
| **size** | market cap = (as-of close price) x (PIT shares outstanding) | lower is better (invert) | shares outstanding via the existing fiscal-year-end + 60d rule |
| **EV/EBIT** | (market cap + total debt - cash) / TTM EBIT | lower is better (invert) | EBIT, debt, cash all resolved with the 60d rule |
| **dividend_yield** | TTM dividends paid per share / (as-of close price) | higher is better | uses yfinance historical `dividends`; only dividends with ex-date <= as-of date |

### Edge-case rules (consistent with existing P/B handling)

- **Negative or zero EBIT** (loss-making): EV/EBIT is undefined -> factor value is NaN
  for that stock. Per the bug #1 fix already merged, a NaN factor is neutralized to
  z=0, so the stock is still ranked on its other factors (not dropped).
- **Missing shares / price / dividends**: factor value NaN -> neutralized to z=0.
- **No dividend history**: dividend_yield = 0.0 (a real economic zero, not missing).
- **Negative EV** (net cash > market cap, rare): EV/EBIT undefined -> NaN -> z=0.

### PIT safety

- Dividend yield uses only dividends with ex-date on or before the as-of date — never
  future dividends. This deliberately avoids the look-ahead hazard of the existing
  `get_earnings_yield`, which reads current `.info` and is explicitly not reused here.
- Size and EV/EBIT reuse the audited 60-day PIT path already covered by tests.

## Architecture / Integration Points

Minimal, additive, following existing patterns.

| Change | File | What |
|---|---|---|
| Three new loaders | `src/data/fundamental_loader.py` | `get_market_caps`, `get_ev_ebit`, `get_dividend_yields` — each mirrors `get_book_values`: json cache, 60d PIT filter, `as_of_date` param, `force_refresh` param, empty-result-not-cached (per bug #3 fix already merged) |
| Extend scorer | `src/scoring/multi_factor.py` | Add `weight_size`, `weight_evebit`, `weight_divy` params (default 0.0) and `market_caps`, `ev_ebit_values`, `dividend_yields` data inputs (default None); compute raw -> z (size/evebit inverted, divy not) -> weighted contribution -> total, mirroring the existing val/qual blocks |
| Propagate weights | `main.py`, `optimize.py`, `strategies/multi_factor.py`, `paper/bot.py` | Thread the three new weights + data inputs through every call site, including closures |

### Signature-expansion safety (AGENTS.md lesson)

`score_universe` and the paper/optimizer call chain will gain new parameters. Per the
AGENTS.md book_values regression lesson: after wiring, **grep every call site** of the
changed functions and visually confirm each forwards the new args, including closures
inside `run_walk_forward_optimization`. An integration test must exercise the full
chain with real (non-monkeypatched) data.

## Testing Strategy (TDD — failing test first)

| Unit | Test type | Key cases |
|---|---|---|
| `get_market_caps` | Unit | PIT boundary (as-of before/after E+60d); missing shares -> None; empty result not cached (bug #3 pattern); cache hit |
| `get_ev_ebit` | Unit | PIT boundary; negative/zero EBIT -> NaN/None; negative EV; missing debt or cash |
| `get_dividend_yields` | Unit | only ex-date <= as-of counted; no-dividend -> 0.0; PIT excludes future dividends |
| `score_universe` | Unit | size/evebit inverted, divy not; **weight-0 regression: results bit-for-bit identical to current output** when new weights are 0; NaN factor neutralized to z=0 (interacts with merged bug #1 fix) |
| full chain | Integration (real data) | new weights flow through optimizer/paper closures with real data — the book_values-regression guard |

## Expected Research Range (not a return promise)

Per the report, Strategy C targets net hit-rate ~54-60%, PF ~1.20-1.55, low turnover,
20-60 day holds. Adding size + EV/EBIT + dividend yield is expected to strengthen the
value/size tilt vs the current P/B-only stack, but this must be validated via
walk-forward, not assumed.

## Deferred to Later

- Shareholder yield including buybacks (needs a reliable buyback data source).
- Sector-aware value normalization beyond the existing industry-neutral z-score.
- EV/FCF and earnings-quality factors.
- The three README-logged deferred bugs.
