# Quant

Japanese equities research and paper-trading platform. Monthly-rebalance, multi-factor, long-only.

## Current State (2026-06-18)

**Active research signal**: 12_1 momentum, low volatility, P/B value, quality/ROE, reversal filter. Monthly execution at month-start first trading day. 100-share lot minimum in the `simple` engine and paper-order target sizing. `top_n` is configurable; the default remains a 3-stock equal-weight portfolio.

**Legacy OOS snapshot** (2025-01 to 2026-03, japan_large_30, realistic execution):

| Config | Return | Sharpe | MaxDD | vs N225 |
|--------|------:|------:|------:|------:|
| mom=0.5 + vol=1.0 | 7.14% | 1.51 | -2.15% | -26.21% |
| + P/B=0.5 | 12.53% | 2.11 | -2.12% | -20.82% |
| N225 (benchmark) | 33.35% | | | |

These numbers predate the 2026-06-18 repair batch. They must be treated as stale and non-decision-grade until walk-forward and OOS reports are regenerated from fresh artifacts.

**Paper trading**: Running in Docker, weekdays 15:45 JST, side-aware adverse auto-fill slippage, daily email report. Universe: japan_large_30. Parameters: approved via walk-forward.

**Tests**: Run `uv run pytest -q` for the current count. The suite includes regression coverage for evaluation-window returns, symbol-level diagnostics, `top_n` propagation, CLI engine dispatch, paper-trading lot sizing/slippage, TTM ROE, quality scoring, vectorbt slippage rejection, and point-in-time book-value providers.

## 2026-06-18 Repair Batch

Locally repaired:

- `top_n` is now propagated through `evaluate_weight_tuple`, walk-forward optimization, optimizer CLI, and simple/vectorbt engine dispatch instead of being hard-coded in execution paths.
- The `simple` engine now marks to market on every trading day through `evaluation_end`; return, Sharpe, and drawdown are computed from the evaluation-window daily equity series.
- The `simple` engine returns symbol-level P&L diagnostics for walk-forward contributor and hit-rate reporting.
- The 12_1 paper-signal path now forwards quality/ROE inputs into research scoring.
- Approved walk-forward parameters preserve optional value and quality weights (`val`, `qual`).
- `src.main --engine simple|vectorbt|backtrader` now routes to the requested engine; Backtrader logging is used only for `--engine backtrader`.

Still not locally fixed:

- Historical TOPIX/Nikkei constituents are not point-in-time. The named universes remain curated static lists, so survivorship and selection bias remain.
- Fundamental release timing is estimated. P/B uses as-of scoring dates, but true filing timestamps are not available in the local data.
- Adjusted prices, corporate actions, suspensions, delistings, and restatements have not been independently audited against a paid vendor.
- Live broker fills are not reconciled against production execution records; paper auto-fill remains a simulation.
- Institutional acceptance gates are not formalized: minimum OOS length, deflated Sharpe, multiple-testing controls, capacity/liquidity limits, stop/retire rules, and approval thresholds still need a research policy.
- Asset-allocation material in this repo should be treated as exploratory notes unless a dedicated research engine and artifacts are added.

## Factors

| Factor | Definition | Direction | Lookback |
|--------|-----------|-----------|----------|
| 12_1 Momentum | (Close{t-21} / Close{t-251}) - 1 | Higher is better | 252 days |
| Low Volatility | Std dev of daily returns | Lower is better | 20 days |
| P/B Value | Close / Book-value-per-share (annual, as-of scoring date, estimated PIT +60d) | Lower is better | N/A |
| Quality | TTM net income / equity | Higher is better | 4 quarters |
| Reversal Filter | Close drawdown from 20-day high > 10% | Entry gate | 20 days |

Cross-sectional Z-scores, configurable weights. Grid search: product({0.0, 0.5, 1.0}, repeat=4) = 80 combinations.

## Architecture

```
Data layer (yfinance + local Parquet store)
    ↓
Shared scorer (multi_factor.py + reversal filter)
    ↓
Engine dispatch (--engine simple|vectorbt|backtrader, default: simple)
    ↓
Walk-forward optimization (optimize.py, 80-combo grid)
    ↓
Artifact store + approval CLI
    ↓
Paper trading bot (Docker, cron, auto-fill, email)
```

### Engines

| Engine | Execution model | Accuracy | Speed |
|--------|----------------|----------|-------|
| `simple` (default) | Month-start, int shares, 100-lot, equal dollar | Ground truth | Fast |
| `vectorbt` | targetpercent, continuous, no slippage | Optimistic reference | Fast |
| `backtrader` | Event-driven, coc, order_target_percent | Reference only | Slow |

`simple` is the only engine modeling realistic execution constraints. `vectorbt` rejects non-zero slippage in this target-percent path because order side is not available before portfolio construction. `vectorbt` and `backtrader` are kept for reference.

## How to Run

```bash
# Sync data
uv run python -m src.main --sync-local --universe-name japan_large_30 --start 2019-01-01 --end 2026-04-30

# Walk-forward optimization (4-factor grid, reversal filter)
uv run python -m src.optimize \
  --start 2020-01-01 --end 2024-12-31 \
  --universe-name japan_large_30 \
  --momentum-definition 12_1 \
  --use-local-store --local-store-root . \
  --local-warmup-bars 240 \
  --reversal-filter

# Approve best run
uv run python -m src.research.approve list
uv run python -m src.research.approve approve --run-id <id>

# Paper trading (manual)
uv run python -m src.paper.bot generate \
  --universe-name japan_large_30 \
  --momentum-definition 12_1 \
  --reversal-filter --auto-fill

# Paper trading status
uv run python -m src.paper.bot status

# Tests
uv run pytest -q

# Docker (automated paper trading)
sudo docker compose up -d
sudo docker compose logs
```

## Optimization

Two weight optimization methods available via `--optimizer`:

| Method | Description | WF Active Return |
|--------|------------|:--:|
| `grid` (default) | Brute-force product({0, 0.5, 1.0}, repeat=4) = 80 combos | -5.2pp |
| `optuna` | TPE sampler, categorical [0, 0.5, 1.0], 50 trials | **+4.1pp** |

Optuna converges at 50 trials; 100 trials produces identical weights.

**Caveat**: These optimization notes predate the 2026-06-18 repair batch. Walk-forward weights from either method did not reliably generalize in the legacy artifacts, but fresh post-repair reruns are required before accepting or rejecting any weight tuple.

## Known Issues

- **Walk-forward overfitting**: In-sample weight optimization (grid or optuna) does not produce weights that generalize to OOS. The signal itself is the limiting factor, not the optimization method.
- **Still trailing N225**: Best configuration is 12.53% vs N225 33.35% over 15 months. Gate FAIL on excess return.
- **100-share lot constraint**: Reduces returns by ~70% vs fractional-share assumption. High-price stocks may be excluded entirely (e.g., stock at ¥5,800 needs ¥580,000 minimum).
- **Static universe**: japan_large_30 is a curated list, not point-in-time constituents. Survivorship bias present.
- **Yahoo Finance data quality**: No independent audit of adjusted prices, suspensions, or delistings.
- **P/B point-in-time**: Book values are now resolved as of each scoring date, but publication dates still use fiscal-year-end + 60-day estimates instead of actual filing timestamps.
- **Vectorbt realism**: The vectorbt path is intentionally optimistic and does not model slippage or 100-share lots.
- **Research acceptance**: Legacy OOS metrics must be regenerated after the 2026-06-18 accounting, parameter-flow, and engine-dispatch fixes.

## Legacy Research Findings

These findings are useful hypotheses, not current evidence. Regenerate them after the 2026-06-18 repair batch before using them in a strategy decision.

1. Reversal filter appeared to add ~13pp OOS improvement by blocking entry when a stock had declined >10% from its 20-day high.
2. P/B value appeared to add ~5pp over the mom+vol baseline.
3. Expanding universe from 30 to 50 stocks appeared to dilute the signal, partly due to shipping-sector concentration in broad_50.
4. Month-start vs month-end execution timing created large divergence across engines.
5. Walk-forward weight selection was unstable across windows; no single weight tuple dominated.
6. The signal tended to pick strong buy-and-hold stocks, but entry timing mattered critically.

## Specs & Plans

Design specs: `docs/superpowers/specs/`
Implementation plans: `docs/superpowers/plans/`
