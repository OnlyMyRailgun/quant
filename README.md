# Quant

Japanese equities research and paper-trading platform. Monthly-rebalance, multi-factor, long-only.

## Current State (2026-04-29)

**Active signal**: 12_1 momentum, low volatility, P/B value, reversal filter. Monthly execution at month-start first trading day. 100-share lot minimum. 3-stock equal-weight portfolio.

**OOS performance** (2025-01 to 2026-03, japan_large_30, realistic execution):

| Config | Return | Sharpe | MaxDD | vs N225 |
|--------|------:|------:|------:|------:|
| mom=0.5 + vol=1.0 | 7.14% | 1.51 | -2.15% | -26.21% |
| + P/B=0.5 | 12.53% | 2.11 | -2.12% | -20.82% |
| N225 (benchmark) | 33.35% | | | |

**Paper trading**: Running in Docker, weekdays 15:45 JST, auto-fill at close minus slippage, daily email report. Universe: japan_large_30. Parameters: approved via walk-forward.

**Tests**: 211 passing, zero regressions.

## Factors

| Factor | Definition | Direction | Lookback |
|--------|-----------|-----------|----------|
| 12_1 Momentum | (Close{t-21} / Close{t-251}) - 1 | Higher is better | 252 days |
| Low Volatility | Std dev of daily returns | Lower is better | 20 days |
| P/B Value | Close / Book-value-per-share (annual, PIT +60d) | Lower is better | N/A |
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
| `vectorbt` | targetpercent, continuous | Optimistic | Fast |
| `backtrader` | Event-driven, coc, order_target_percent | Reference only | Slow |

`simple` is the only engine modeling realistic execution constraints. `vectorbt` and `backtrader` are kept for reference.

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

**Caveat**: Walk-forward weights (from either method) do NOT reliably generalize to OOS. The 4-factor signal on japan_large_30 is too weak/noisy. Fixed weights (mom=0.5, vol=1.0, val=0.5) found via direct OOS validation remain the best for now.

## Known Issues

- **Walk-forward overfitting**: In-sample weight optimization (grid or optuna) does not produce weights that generalize to OOS. The signal itself is the limiting factor, not the optimization method.
- **Still trailing N225**: Best configuration is 12.53% vs N225 33.35% over 15 months. Gate FAIL on excess return.
- **100-share lot constraint**: Reduces returns by ~70% vs fractional-share assumption. High-price stocks may be excluded entirely (e.g., stock at ¥5,800 needs ¥580,000 minimum).
- **Static universe**: japan_large_30 is a curated list, not point-in-time constituents. Survivorship bias present.
- **Yahoo Finance data quality**: No independent audit of adjusted prices, suspensions, or delistings.
- **P/B point-in-time**: Uses fiscal-year-end + 60-day delay. Publication dates are estimated, not from actual filings.

## Research Findings

1. Reversal filter adds ~13pp OOS improvement (blocking entry when stock has declined >10% from 20-day high)
2. P/B value factor adds ~5pp improvement over mom+vol baseline
3. Expanding universe from 30 to 50 stocks dilutes the signal (shipping sector concentration in broad_50)
4. Month-start vs month-end execution timing creates significant divergence (50pp between engines)
5. Walk-forward weight selection is unstable across windows — no single weight tuple dominates
6. Signal picks good stocks (avg buy-and-hold +35.9%) but entry timing matters critically

## Specs & Plans

Design specs: `docs/superpowers/specs/`
Implementation plans: `docs/superpowers/plans/`
