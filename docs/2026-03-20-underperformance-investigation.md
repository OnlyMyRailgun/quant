# Underperformance Investigation

Date: 2026-03-20

## Question

Why does the current multi-factor walk-forward workflow underperform TOPIX / Nikkei benchmarks, especially after expanding the universe beyond `topix_top_10`?

## Scope

This note documents:

- confirmed findings from the current `main` branch
- direct evidence from recent walk-forward runs
- validation experiments for two hypotheses:
  - removing the `(0.0, 0.0, 0.0)` weight tuple from the optimization grid
  - increasing `top_n` for larger universes

## Baseline Evidence

Recent walk-forward artifacts:

- `topix_top_10`: `/Users/y-yang/Developer/quant/.research_artifacts/walk_forward/20260320T114525Z-20260320T114525Z-8a4c5548`
- `japan_large_30`: `/Users/y-yang/Developer/quant/.research_artifacts/walk_forward/20260320T114724Z-20260320T114724Z-95af8c25`
- `japan_broad_50`: `/Users/y-yang/Developer/quant/.research_artifacts/walk_forward/20260320T114922Z-20260320T114922Z-39cb64e5`

Baseline summary:

| Universe | Walk-forward | TOPX | N225 | Excess vs TOPX |
| --- | ---: | ---: | ---: | ---: |
| `topix_top_10` | `8.7062%` | `24.1043%` | `23.0408%` | `-15.3981%` |
| `japan_large_30` | `-7.0522%` | `24.1043%` | `23.0408%` | `-31.1565%` |
| `japan_broad_50` | `-10.9657%` | `24.1043%` | `23.0408%` | `-35.0700%` |

All three runs reported full universe participation coverage:

- `avg_coverage_ratio = 1.0`
- `min_coverage_ratio = 1.0`

This rules out incomplete validation-window loading as the primary cause.

## Confirmed Issues

### 1. Training-window optimization is overfitting

The optimizer selects weights by training-window `return_pct`, with `sharpe` only as a secondary tie-breaker in the sort order.

Relevant code:

- [/Users/y-yang/Developer/quant/src/research/walk_forward.py](/Users/y-yang/Developer/quant/src/research/walk_forward.py#L224)
- [/Users/y-yang/Developer/quant/src/research/walk_forward.py](/Users/y-yang/Developer/quant/src/research/walk_forward.py#L247)

Observed behavior from the recent runs:

| Universe | Avg train return | Avg validation return | Mean train-validation gap |
| --- | ---: | ---: | ---: |
| `topix_top_10` | `17.7870%` | `2.1766%` | `15.6105%` |
| `japan_large_30` | `18.7464%` | `-1.7630%` | `20.5095%` |
| `japan_broad_50` | `32.9476%` | `-2.7414%` | `35.6890%` |

Interpretation:

- training windows look consistently strong
- validation windows degrade sharply as the universe broadens
- the gap is too large to treat as ordinary variance

### 2. The portfolio is too concentrated for broader universes

The strategy always holds only `top_n=3` names by default, regardless of whether the universe has `10`, `30`, or `50` symbols.

Relevant code:

- [/Users/y-yang/Developer/quant/src/strategies/multi_factor.py](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py#L17)
- [/Users/y-yang/Developer/quant/src/strategies/multi_factor.py](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py#L24)
- [/Users/y-yang/Developer/quant/src/strategies/multi_factor.py](/Users/y-yang/Developer/quant/src/strategies/multi_factor.py#L175)

Implication:

- on `30` or `50` names, the system still collapses the whole cross-section into 3 equal-weight positions
- single-stock misses have outsized impact
- broader universes introduce more ranking noise, but the portfolio construction does not diversify that noise away

### 3. The default weight grid contains a degenerate no-signal configuration

The optimization grid includes `(0.0, 0.0, 0.0)`.

Relevant code:

- [/Users/y-yang/Developer/quant/src/optimize.py](/Users/y-yang/Developer/quant/src/optimize.py#L25)

The scorer ranks by `total_score`, which is just the weighted sum of factor contributions:

- [/Users/y-yang/Developer/quant/src/scoring/multi_factor.py](/Users/y-yang/Developer/quant/src/scoring/multi_factor.py#L147)
- [/Users/y-yang/Developer/quant/src/scoring/multi_factor.py](/Users/y-yang/Developer/quant/src/scoring/multi_factor.py#L156)

With all-zero weights:

- every symbol gets the same `total_score`
- sorting falls back to input order under stable sorting
- the optimizer can accidentally reward a no-signal portfolio if the first few universe names happened to do well in-sample

This is not hypothetical:

- the `japan_large_30` artifact selected `(0.0, 0.0, 0.0)` for the `2022-01-01` rebalance window

### 4. Factor definitions are simple and short-horizon

The current factor set is:

- `90`-day momentum
- `20`-day volatility
- `20`-day mean reversion

Relevant code:

- [/Users/y-yang/Developer/quant/src/scoring/multi_factor.py](/Users/y-yang/Developer/quant/src/scoring/multi_factor.py#L8)
- [/Users/y-yang/Developer/quant/src/scoring/multi_factor.py](/Users/y-yang/Developer/quant/src/scoring/multi_factor.py#L41)

Inference from the code and results:

- this is a lightweight cross-sectional signal set
- there is no sector neutralization, liquidity control, quality filter, or portfolio risk balancing
- once the universe broadens, the ranking model appears less stable than the current top-3 construction requires

## Hypotheses To Validate

### Hypothesis A

Removing `(0.0, 0.0, 0.0)` from the optimization grid should reduce degenerate in-sample selections and modestly improve walk-forward robustness.

### Hypothesis B

Increasing `top_n` for broader universes should reduce concentration risk and improve out-of-sample performance, even if it does not fully close the benchmark gap.

## Validation Results

### Hypothesis A: Remove `(0.0, 0.0, 0.0)` from the grid

Controlled walk-forward reruns used the same date range and windowing as the baseline:

- `start=2021-01-01`
- `end=2024-01-01`
- `train_months=12`
- `validation_months=6`
- `step_months=6`

Results:

| Universe | Full grid walk-forward | No-zero grid walk-forward | Change |
| --- | ---: | ---: | ---: |
| `japan_large_30` | `-7.0522%` | `-1.1334%` | `+5.9188%` |
| `japan_broad_50` | `-10.9657%` | `-10.9657%` | `0.0000%` |

Interpretation:

- removing the degenerate tuple materially helped `japan_large_30`
- it had no effect on `japan_broad_50`, because the all-zero tuple was not the winning configuration there

Most important detail:

- in `japan_large_30`, the first validation window stopped selecting `(0.0, 0.0, 0.0)` and instead selected `(0.0, 1.0, 1.0)`
- that window's validation return moved from `-5.5734%` to `0.3454%`

Conclusion:

- Hypothesis A is confirmed as a real issue
- but it is a secondary issue, not the dominant explanation for broader-universe underperformance

### Hypothesis B: Increase `top_n` for broader universes

Walk-forward reruns with the no-zero grid:

| Universe | Setting | Walk-forward | Change vs smaller `top_n` |
| --- | --- | ---: | ---: |
| `japan_large_30` | `top_n=3` | `-1.1334%` | baseline |
| `japan_large_30` | `top_n=10` | `1.0971%` | `+2.2305%` |
| `japan_broad_50` | `top_n=3` | `-10.9657%` | baseline |
| `japan_broad_50` | `top_n=10` | `-7.0896%` | `+3.8761%` |

Supplementary fixed-weight sensitivity test on `japan_broad_50` over `2022-01-01` to `2024-01-01` with weights `(1.0, 1.0, 1.0)`:

| `top_n` | Return |
| --- | ---: |
| `3` | `-8.4093%` |
| `5` | `-10.5442%` |
| `10` | `5.7026%` |
| `15` | `16.0805%` |
| `20` | `15.2299%` |

Benchmarks for the same fixed-weight sensitivity window:

- `1306.T`: `22.1856%`
- `1321.T`: `18.8410%`

Interpretation:

- increasing `top_n` consistently improves broader-universe behavior once the portfolio is allowed to hold meaningfully more names
- the improvement is large enough to confirm that concentration is a structural drag
- even so, the strategy still does not convincingly beat `TOPIX`, so concentration is not the only problem

Conclusion:

- Hypothesis B is confirmed
- broader universes need broader portfolios; keeping `top_n=3` is too concentrated for the current signal quality

## Current Takeaway

The current evidence points to a combination of:

1. optimization overfitting
2. overly concentrated portfolio construction
3. a weak default search space that includes a no-signal tuple
4. a factor set that does not appear strong enough to support top-3 concentration in larger universes

## Updated Takeaway

After validation, the current priority order looks like this:

1. `top_n` / portfolio breadth is the strongest confirmed structural issue
2. the all-zero tuple is a genuine optimizer flaw, but not the main reason `broad_50` loses
3. even after addressing those two issues directionally, the current factor model still appears too weak to reliably beat `TOPIX`
