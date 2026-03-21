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

## Post-Diagnostic Factor Research

After removing look-ahead bias and aligning diagnostics to real monthly rebalance events, the initial factor conclusion changed materially.

Most important correction:

- the earlier "momentum is obviously strong" conclusion was polluted by diagnostic leakage and should not be used
- under the repaired diagnostic path, the current `90`-day momentum signal is weak-to-mixed rather than clearly strong
- `20`-day volatility now looks more credible than previously believed

### Repaired Diagnostic Baseline: `90d` Momentum vs Current `vol` / `rev`

Artifacts from the repaired three-factor reruns:

- `topix_top_10`: `/Users/y-yang/Developer/quant/.research_artifacts/walk_forward/walk_forward/20260321T141103Z-20260321T141103Z-5d89c1fb`
- `japan_large_30`: `/Users/y-yang/Developer/quant/.research_artifacts/walk_forward/walk_forward/20260321T141725Z-20260321T141725Z-81458eba`
- `japan_broad_50`: `/Users/y-yang/Developer/quant/.research_artifacts/walk_forward/walk_forward/20260321T141745Z-20260321T141745Z-fcc5b238`

Window-level mean IC from those repaired runs:

| Universe | `mom` IC mean | `vol` IC mean | `rev` IC mean |
| --- | ---: | ---: | ---: |
| `topix_top_10` | `-0.0382` | `0.0636` | `0.0473` |
| `japan_large_30` | `0.0259` | `0.1140` | `0.0072` |
| `japan_broad_50` | `-0.0029` | `0.0743` | `-0.0190` |

Interpretation:

- current `90d` momentum is not a stable winner under the repaired research path
- `vol` is the most consistently positive factor among the three current factors
- `rev` is weak, but no longer supported as a simple "always negative, definitely remove it" conclusion

### Horizon Check: `90d` Momentum vs Classic `12-1` Momentum

Using the repaired monthly rebalance diagnostics path, a research-only comparison of momentum horizons produced:

| Universe | `90d` mean IC | `12-1` mean IC |
| --- | ---: | ---: |
| `topix_top_10` | `-0.0382` | `-0.0433` |
| `japan_large_30` | `0.0259` | `0.0951` |
| `japan_broad_50` | `-0.0029` | `0.0419` |

Interpretation:

- on the more relevant `japan_large_30` and `japan_broad_50` universes, `12-1` momentum is meaningfully better than the current `90d` definition
- `topix_top_10` remains too noisy to drive the direction of factor redesign
- future momentum research should start from `12-1`, not from the current `90d` lookback

### Research-Only Walk-Forward Approximation

To compare candidate single-factor directions before changing production strategy code, a research-only monthly rebalance approximation was run for:

- `12-1 mom-only`
- `vol-only`
- `12-1 mom + vol`

Important caveat:

- this is not the Backtrader production path
- it does not simulate transaction costs, slippage, or exact live order timing
- the absolute return levels below should not be compared directly to `TOPIX`
- the reliable signal from this experiment is the ranking relationship between factor variants, not the headline return number

Results:

| Universe | `12-1 mom-only` | `vol-only` | `12-1 mom + vol` |
| --- | ---: | ---: | ---: |
| `topix_top_10` | `28.1351%` | `35.5768%` | `14.7990%` |
| `japan_large_30` | `31.4158%` | `43.7148%` | `33.2851%` |
| `japan_broad_50` | `31.5875%` | `36.0344%` | `17.9833%` |

Ordering relationship:

- `vol-only` > `12-1 mom-only` > `12-1 mom + vol`

Interpretation:

- `12-1 mom-only` clearly improves on the old `90d mom-only` direction
- `vol-only` is strong enough to treat as a core candidate factor, not a secondary add-on
- naive linear combination of `12-1` momentum and `vol` degrades results instead of improving them

### Working Hypothesis For The `12-1 + vol` Degradation

The most likely explanation is factor overlap or partial cancellation in the cross-section.

This is still a hypothesis, not a confirmed conclusion.

What is currently justified:

- the combined signal is worse than either single-factor signal in the research-only approximation
- a plausible next check is the cross-sectional correlation between `12-1` momentum and `vol`
- if that correlation is meaningfully negative, simple linear mixing may be diluting both signals instead of improving ranking power

### Follow-Up Diagnostic: Top-of-Book Dilution

That follow-up check was run directly on the repaired monthly rebalance path.

What was tested:

- for each validation window
- for each monthly rebalance event inside that window
- compare the concrete `top_n` names selected by:
  - `12-1 mom-only`
  - `vol-only`

Observed average `top_n` overlap:

| Universe | Effective `top_n` | Mean overlap |
| --- | ---: | ---: |
| `topix_top_10` | `3` | `38.3%` |
| `japan_large_30` | `8` | `32.3%` |
| `japan_broad_50` | `13` | `18.8%` |

Interpretation:

- even when `12-1 mom` and `vol` point in a similar window-level direction, they often select very different top-ranked names
- the mixed signal therefore changes the actual holdings materially, not just the ordering of marginal names
- this strongly supports a top-of-book dilution explanation for why `12-1 mom + vol` underperforms the two single-factor variants

Important boundary condition:

- this conclusion is specific to the current holding-construction style, especially the current `top_n` scale and hard top-`N` equal-weight selection
- if the portfolio moves to wider holdings or layered/graded position sizing, the strength of the dilution effect may change and should be re-validated

### Structural Note: Small Portfolios Amplify Ranking Disturbance

The overlap result also reinforces a broader construction point:

- when the portfolio holds only a small number of names, any factor-combination-induced ranking disturbance becomes a large portfolio weight change
- this is not just a factor-design issue; it is also a portfolio-construction sensitivity issue

Implication:

- some of the observed degradation from factor mixing may be reduced by broader or more graduated portfolio construction, even without changing the underlying factor set

### Updated Research Priority

After the repaired diagnostics and first research-only follow-up, the next research order is:

1. treat current `90d` momentum as a deprecated baseline, not the preferred momentum definition
2. continue factor work with `12-1` momentum and `vol` as the two serious candidates
3. investigate why `12-1 mom + vol` underperforms the single-factor variants before proposing any multi-factor replacement
4. keep absolute-return claims conservative until the candidate factors have been validated through the real production-path strategy implementation

## Next-Stage Research Directions

With the current investigation complete, the next-stage options can now be prioritized more explicitly:

| Direction | Expected impact | Implementation cost | Priority |
| --- | --- | --- | ---: |
| Replace current `90d mom` with `12-1 mom` | High: repaired IC is clearly better on `large_30` and `broad_50` | Low | `1` |
| Change the optimization target away from pure `return_pct` toward a more risk-aware objective such as `Sharpe` | High: directly addresses the confirmed overfitting behavior | Low | `1` |
| Use a dynamic holding-count rule such as `sqrt(N)` | Medium: likely reduces sensitivity to top-rank disturbance | Low | `2` |
| Favor single-factor baselines first, then revisit combination logic | Medium: avoids mixing signals before they are individually validated in the live research path | Low | `2` |
| Introduce a value factor such as `P/B` | Unknown until tested; may offer a more complementary signal family | High: requires financial-data access and integration | `3` |

Recommended order for the next implementation/research slice:

1. migrate momentum research from `90d` to `12-1`
2. change optimizer selection away from pure `return_pct`
3. revisit portfolio breadth, including `sqrt(N)`-style holding rules
4. only after that, test new factor families such as value
