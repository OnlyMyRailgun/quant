# Dynamic Universe via Reproducible Snapshots Design

Date: 2026-07-14

## Goal

Let research use larger TOPIX universes (up to ~500 names) sourced from J-Quants,
instead of only the three hand-written static lists (30/50 names). Fetches are
snapshotted to dated local files so backtests are reproducible, and every run's
artifacts record the snapshot date and a survivorship-bias warning.

## Why This Slice

The current `get_universe(name)` resolves only three static lists
(`topix_top_10`, `japan_large_30`, `japan_broad_50`), max 50 names. The repo's own
README Known Issues flags this: the static universes are too small for institutional
cross-sectional factor claims (IC, industry-neutralization, idiosyncratic-risk control
all need breadth). `jquants_universe.get_topix_universe()` can already fetch ~500 names
by `ScaleCat`, but nothing wires it into universe resolution. This slice connects them
and makes the result reproducible and honestly labeled.

## Scope Boundary (read first)

This slice fixes **sample size** (30 → up to ~500). It does NOT fix **survivorship
bias**: the names come from J-Quants' *current* `ScaleCat` classification, so a backtest
uses today's constituents over historical prices — delisted / demoted / merged names
are absent. That is a separate, larger effort ("point-in-time universe"). This spec
deliberately does not solve it, but it **reserves the interface** (`as_of` parameter) so
point-in-time can be added later with minimal change. When `as_of` is set to a non-today
date in v1, the snapshot filename records that date but the constituent list is still the
current one — v1 does not perform historical constituent lookup.

## Locked Design Parameters

Decided during brainstorming; fixed for this slice:

| Dimension | Decision |
|---|---|
| Data source | `jquants_universe.get_topix_universe(size)` (free-tier `cli.get_list()` by `ScaleCat`) |
| Sizes | `core30`, `large70`, `large100`, `mid400`, `topix500` |
| Reproducibility | Fetch once, snapshot to a dated local JSON; backtests read the snapshot, not a re-fetch |
| Survivorship | Explicitly labeled — snapshot date + `survivorship_bias: true` written into run artifacts; positioned as research-grade, not decision-grade |
| Resolution entry | New `resolve_universe(name)`; existing `get_universe(name)` stays local-only and unchanged |
| No silent fallback | Missing token / fetch failure raises a clear error; never silently returns a static list |

## Non-Goals

- Does NOT change `get_universe(name)` behavior or its callers' results for the three
  static universes.
- Does NOT implement point-in-time historical constituents (only reserves `as_of`).
- Does NOT add delisted-stock handling or corporate-action reconstruction.
- Does NOT modify the scoring, engine, or paper pipelines beyond passing a larger symbol
  list and stamping two artifact metadata fields.
- Does NOT commit snapshot files to git (they live under `.data_cache/`, git-ignored).

## Architecture

Three units. `get_universe` is untouched; only code paths that opt into dynamic
universes call `resolve_universe`.

```
src/data/universe_snapshot.py   -> fetch TOPIX ScaleCat, snapshot to dated JSON, read back
        |  (symbols + snapshot metadata)
        v
src/data/universe.py            -> new resolve_universe(name); get_universe unchanged
        |
        v
callers (optimize / main / paper that opt in) -> switch to resolve_universe
```

### Unit boundaries

| Unit | Responsibility | Input -> Output | Depends on |
|---|---|---|---|
| `universe_snapshot` | Fetch TOPIX classification, snapshot to a dated file, read back; fetch only on cache miss | `size, as_of` -> `(symbols, snapshot_meta)` | `jquants_universe` |
| `resolve_universe` | Single entry point: static names route to `get_universe`, dynamic names route to snapshots | `name` -> `list[str]` | `universe_snapshot` |
| artifact stamping | Write `universe_snapshot_date` + `survivorship_bias` into run artifacts | meta -> artifact | reuse `src/research/artifacts` |

## Snapshot File Format

Path: `.data_cache/universe_snapshots/{size}_{as_of}.json`
Example: `.data_cache/universe_snapshots/topix500_2026-07-14.json`

```json
{
  "size": "topix500",
  "snapshot_date": "2026-07-14",
  "source": "jquants get_list ScaleCat",
  "survivorship_warning": "current constituents only; not point-in-time",
  "symbols": ["7203.T", "6758.T", "..."]
}
```

Dated filename means: same-day re-runs reuse one snapshot; different dates each keep
their own file, so past snapshots remain traceable. Stored under `.data_cache/`
(git-ignored, consistent with existing parquet / friction files).

## Data Flow

`resolve_universe(name)`:
1. `name` in the three static lists -> return `get_universe(name)` (unchanged local path).
2. `name` in the dynamic set (`core30`/`large70`/`large100`/`mid400`/`topix500`) ->
   `universe_snapshot.load_or_fetch(size=name)`.
3. Otherwise -> `KeyError` with the list of valid names.

`load_or_fetch(size, as_of=today)`:
1. Look for `.data_cache/universe_snapshots/{size}_{as_of}.json` -> hit: read it, no network.
2. Miss -> call `get_topix_universe(size)`, write the snapshot file, return.
3. No token / fetch failure -> raise a clear error naming `JQUANTS_API_KEY`. Never
   silently fall back to a static list (which would mask "I thought I ran 500 names but
   ran 30").

`as_of` defaults to today. In v1 it only pins/records the snapshot for reproducibility;
it does not retrieve historical constituents. (Point-in-time later: pass `date_yyyymmdd`
to `get_list` when `as_of` is not today — a few lines, out of scope here.)

## Artifact Stamping

Backtest / optimizer artifacts gain two metadata fields so any result is self-describing:
- `universe_snapshot_date`: the snapshot's date.
- `survivorship_bias`: `true` for dynamic universes.

## Error Handling

- Missing/invalid `JQUANTS_API_KEY` on a cache miss: raise `RuntimeError` with a message
  telling the user to set the token; do not fall back.
- Unknown universe name: `KeyError` listing valid static + dynamic names.
- Corrupt/unreadable snapshot file: treat as a miss and re-fetch (do not crash).

## Testing Strategy (TDD — failing test first)

| Unit | Test type | Key cases |
|---|---|---|
| `universe_snapshot` | Unit (mock jquants client) | cache hit -> reads back, no client call; miss -> fetch + write; missing token / fetch error -> raises, no silent fallback; snapshot file contains `snapshot_date` + `survivorship_warning` |
| `resolve_universe` | Unit | static name -> delegates to `get_universe` (unchanged result); dynamic name -> snapshot path; unknown name -> `KeyError` |
| `as_of` reservation | Unit | non-today `as_of` -> snapshot filename carries that date, but symbols are still the current list (assert v1 does NOT do point-in-time, to prevent misreading) |
| artifact stamping | Unit | dynamic-universe run metadata includes `universe_snapshot_date` and `survivorship_bias: true` |

**Live fetch caveat**: this environment has no `JQUANTS_API_KEY`, so a real
`get_list()` call cannot run in CI. Tests use a mock client for all logic; the real
fetch must be verified once manually by the user with a token set. This mirrors the
Strategy A loader's honest positioning.

## Deferred

- Point-in-time historical constituents via `get_list(date_yyyymmdd=...)` (interface
  reserved via `as_of`).
- Delisted-stock inclusion / corporate-action reconstruction.
- Paid-tier data depth needed for 5-10 year point-in-time backtests.
