# Professionalization Repair Design

## Goal

Repair the high-confidence defects found in the professional finance review that can be fixed locally and verified with automated tests, while documenting remaining issues that require external point-in-time data sources or broader research policy decisions.

## In Scope

- Restore a green test baseline by removing date-fragile paper-trading tests.
- Correct the `simple` engine evaluation-window accounting so warmup trading before `evaluation_start` does not contaminate validation returns.
- Align paper-trading order generation with Japanese equity execution constraints:
  - 100-share lot sizing.
  - Side-aware slippage in auto-fill.
  - Better theoretical cash allocation that includes liquidating non-target holdings when prices are available.
- Ensure `research_scoring` either implements quality factor scoring when `roe_values` are provided or does not silently ignore `weight_qual`.
- Make `vectorbt` slippage behavior explicit and test-backed instead of accepting a parameter that has no execution effect.
- Update documentation claims that are contradicted by current tests or execution behavior.

## Out of Scope

- Full point-in-time constituent history for TOPIX/Nikkei universes.
- Real filing publication dates for fundamental factors.
- Independent vendor price audit for splits, dividends, suspensions, and delistings.
- Live broker integration or real-money order routing.
- Research validation policy changes that require an investment committee decision, such as approved benchmark gates or OOS acceptance thresholds.

These out-of-scope items remain professional-risk gaps. They should not be described as fixed unless a proper data source and verification protocol are added.

## Requirements

1. `uv run pytest -q` must pass locally after the repair batch.
2. Tests must be written or updated before production-code fixes, and each new regression test must be observed failing for the expected reason before implementation.
3. The `simple` engine must calculate `return_pct` over `evaluation_start..evaluation_end` from the portfolio value at the first evaluation record, not from original `initial_cash` when warmup records exist.
4. `simple` engine drawdown and Sharpe should be computed from the same evaluation value series used for return.
5. Paper generated buy orders must be rounded down to 100-share lots by default.
6. Paper auto-fill must make buys more expensive and sells cheaper under positive slippage.
7. `research_scoring` must include quality z-scores and contributions when `roe_values` and `weight_qual` are supplied.
8. `vectorbt` runner must either apply slippage to order execution prices or reject non-zero slippage with a clear error. The preferred repair is to apply side-aware adverse slippage where order side is known.
9. README must stop claiming a stale passing-test count and must clearly label remaining professional limitations.

## Risks

- Some tests currently use mocks around paper-trading data and order placement. New tests should exercise real sizing and price transformations as directly as possible.
- `vectorbt` target-percent orders do not expose a simple buy/sell row before portfolio construction. A minimal, honest fix may require rejecting `slippage_pct != 0` until a side-aware order path exists, rather than pretending slippage is modeled.
- Full professionalization cannot be completed without external historical constituents and fundamental publication dates.
