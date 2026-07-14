# Dynamic Universe Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let research resolve larger TOPIX universes (up to ~500 names) from J-Quants via reproducible dated snapshots, without changing `get_universe`'s existing behavior, and stamp snapshot date + survivorship warning into artifacts.

**Architecture:** A new `universe_snapshot` module fetches TOPIX `ScaleCat` names and caches them to a dated JSON under `.data_cache/`. A new `resolve_universe(name)` routes static names to the untouched `get_universe` and dynamic names to the snapshot loader. A small metadata helper stamps snapshot provenance into run artifacts.

**Tech Stack:** Python 3.12, pandas, pytest, uv, jquants-api-client.

## Global Constraints

- `get_universe(name)` and its results for the three static universes (`topix_top_10`, `japan_large_30`, `japan_broad_50`) MUST stay unchanged — local dict lookup, no network, no IO.
- Dynamic sizes: `core30`, `large70`, `large100`, `mid400`, `topix500` (the keys `get_topix_universe` accepts).
- Snapshot path: `.data_cache/universe_snapshots/{size}_{as_of}.json`. `as_of` defaults to today (`YYYY-MM-DD`).
- Reproducibility: on a snapshot-file hit, read it and DO NOT call the network.
- NO silent fallback: missing `JQUANTS_API_KEY` / fetch failure on a cache miss raises a clear error naming the env var; never return a static list instead.
- `as_of` is reserved only: a non-today `as_of` changes the snapshot filename but v1 still fetches the CURRENT constituent list (no point-in-time historical lookup).
- Snapshot files live under `.data_cache/` (git-ignored). Do not commit them.
- Snapshot JSON must contain: `size`, `snapshot_date`, `source`, `survivorship_warning`, `symbols`.
- Run all commands with `uv run`. Tests live under `tests/`.
- This environment has NO token: tests mock the jquants client. A real fetch is verified manually by the user later.

---

### Task 1: `universe_snapshot` module — fetch, snapshot, read back

**Files:**
- Create: `src/data/universe_snapshot.py`
- Create: `tests/data/test_universe_snapshot.py`

**Interfaces:**
- Consumes: `src.data.jquants_universe.get_topix_universe(size)` (returns `list[str]` of `.T` tickers).
- Produces: `load_or_fetch(size: str, as_of: str | None = None, snapshot_dir: Path | None = None, fetcher=None) -> tuple[list[str], dict]` returning `(symbols, snapshot_meta)`. `snapshot_meta` has keys `size, snapshot_date, source, survivorship_warning, symbols`. `fetcher` defaults to `get_topix_universe` and is injectable for tests. Also `_snapshot_path(size, as_of, snapshot_dir) -> Path`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/data/test_universe_snapshot.py
import json
from pathlib import Path

import pytest

from src.data import universe_snapshot as us


def test_cache_hit_reads_back_without_calling_fetcher(tmp_path: Path):
    snap_dir = tmp_path / "universe_snapshots"
    snap_dir.mkdir(parents=True)
    (snap_dir / "topix500_2026-07-14.json").write_text(json.dumps({
        "size": "topix500", "snapshot_date": "2026-07-14",
        "source": "jquants get_list ScaleCat",
        "survivorship_warning": "current constituents only; not point-in-time",
        "symbols": ["7203.T", "6758.T"],
    }))

    def boom(size):  # must NOT be called on a hit
        raise AssertionError("fetcher should not be called on cache hit")

    symbols, meta = us.load_or_fetch("topix500", as_of="2026-07-14",
                                     snapshot_dir=snap_dir, fetcher=boom)
    assert symbols == ["7203.T", "6758.T"]
    assert meta["snapshot_date"] == "2026-07-14"


def test_cache_miss_fetches_and_writes_snapshot(tmp_path: Path):
    snap_dir = tmp_path / "universe_snapshots"

    def fake_fetch(size):
        assert size == "mid400"
        return ["1301.T", "1332.T"]

    symbols, meta = us.load_or_fetch("mid400", as_of="2026-07-14",
                                     snapshot_dir=snap_dir, fetcher=fake_fetch)
    assert symbols == ["1301.T", "1332.T"]
    written = json.loads((snap_dir / "mid400_2026-07-14.json").read_text())
    assert written["symbols"] == ["1301.T", "1332.T"]
    assert written["snapshot_date"] == "2026-07-14"
    assert "survivorship_warning" in written


def test_fetch_failure_raises_and_does_not_fall_back(tmp_path: Path):
    snap_dir = tmp_path / "universe_snapshots"

    def failing_fetch(size):
        raise RuntimeError("no token")

    with pytest.raises(RuntimeError):
        us.load_or_fetch("topix500", as_of="2026-07-14",
                         snapshot_dir=snap_dir, fetcher=failing_fetch)
    # No snapshot file written on failure.
    assert not (snap_dir / "topix500_2026-07-14.json").exists()


def test_non_today_as_of_names_file_with_that_date(tmp_path: Path):
    snap_dir = tmp_path / "universe_snapshots"
    # v1: as_of only pins the filename; symbols are still whatever fetcher returns.
    us.load_or_fetch("core30", as_of="2024-01-01",
                     snapshot_dir=snap_dir, fetcher=lambda size: ["7203.T"])
    assert (snap_dir / "core30_2024-01-01.json").exists()


def test_corrupt_snapshot_is_treated_as_miss(tmp_path: Path):
    snap_dir = tmp_path / "universe_snapshots"
    snap_dir.mkdir(parents=True)
    (snap_dir / "core30_2026-07-14.json").write_text("{ not json")
    symbols, _ = us.load_or_fetch("core30", as_of="2026-07-14",
                                  snapshot_dir=snap_dir, fetcher=lambda size: ["7203.T"])
    assert symbols == ["7203.T"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/data/test_universe_snapshot.py -v`
Expected: FAIL (`ModuleNotFoundError: src.data.universe_snapshot`).

- [ ] **Step 3: Write minimal implementation**

```python
# src/data/universe_snapshot.py
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

DEFAULT_SNAPSHOT_DIR = Path(".data_cache/universe_snapshots")
_SURVIVORSHIP_WARNING = "current constituents only; not point-in-time"
_SOURCE = "jquants get_list ScaleCat"
VALID_SIZES = ("core30", "large70", "large100", "mid400", "topix500")


def _snapshot_path(size: str, as_of: str, snapshot_dir: Path) -> Path:
    return snapshot_dir / f"{size}_{as_of}.json"


def load_or_fetch(size, as_of=None, snapshot_dir=None, fetcher=None):
    if size not in VALID_SIZES:
        raise KeyError(f"Unknown dynamic universe size '{size}'. Valid: {list(VALID_SIZES)}")
    if as_of is None:
        as_of = date.today().strftime("%Y-%m-%d")
    if snapshot_dir is None:
        snapshot_dir = DEFAULT_SNAPSHOT_DIR
    else:
        snapshot_dir = Path(snapshot_dir)
    if fetcher is None:
        from src.data.jquants_universe import get_topix_universe
        fetcher = get_topix_universe

    path = _snapshot_path(size, as_of, snapshot_dir)
    if path.exists():
        try:
            meta = json.loads(path.read_text())
            return list(meta["symbols"]), meta
        except (json.JSONDecodeError, KeyError):
            pass  # corrupt -> treat as miss, re-fetch below

    # Cache miss: fetch. Let fetch errors propagate (no silent fallback).
    symbols = fetcher(size)
    meta = {
        "size": size,
        "snapshot_date": as_of,
        "source": _SOURCE,
        "survivorship_warning": _SURVIVORSHIP_WARNING,
        "symbols": list(symbols),
    }
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2))
    return list(symbols), meta
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/data/test_universe_snapshot.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data/universe_snapshot.py tests/data/test_universe_snapshot.py
git commit -m "feat: add reproducible dated universe snapshot loader"
```

---

### Task 2: `resolve_universe` — unified static/dynamic entry point

**Files:**
- Modify: `src/data/universe.py`
- Test: `tests/data/test_universe.py`

**Interfaces:**
- Consumes: existing `get_universe(name)` and `_UNIVERSES` (static dict) from `universe.py`; `universe_snapshot.load_or_fetch` (Task 1); `universe_snapshot.VALID_SIZES`.
- Produces: `resolve_universe(name: str, as_of: str | None = None) -> list[str]`. Static names delegate to `get_universe` unchanged; dynamic names (in `VALID_SIZES`) route to the snapshot loader (symbols only); unknown names raise `KeyError` listing both static and dynamic valid names.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/data/test_universe.py
from src.data.universe import resolve_universe, get_universe


def test_resolve_static_name_matches_get_universe():
    assert resolve_universe("japan_large_30") == get_universe("japan_large_30")


def test_resolve_dynamic_name_routes_to_snapshot(monkeypatch):
    called = {}

    def fake_load_or_fetch(size, as_of=None, **kwargs):
        called["size"] = size
        return (["7203.T", "6758.T"], {"snapshot_date": "2026-07-14"})

    monkeypatch.setattr("src.data.universe_snapshot.load_or_fetch", fake_load_or_fetch)
    result = resolve_universe("topix500")
    assert result == ["7203.T", "6758.T"]
    assert called["size"] == "topix500"


def test_resolve_unknown_name_raises_keyerror():
    import pytest
    with pytest.raises(KeyError):
        resolve_universe("not_a_universe")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/data/test_universe.py -k "resolve" -v`
Expected: FAIL (`ImportError: cannot import name 'resolve_universe'`).

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/data/universe.py (near get_universe)
def resolve_universe(name: str, as_of: str | None = None) -> list[str]:
    """Resolve a universe name to tickers.

    Static names (the hand-written lists) use the local dict, unchanged and
    offline. Dynamic sizes (core30/large70/large100/mid400/topix500) are fetched
    from J-Quants and read from a reproducible dated snapshot.
    """
    if name in _UNIVERSES:
        return get_universe(name)

    from src.data import universe_snapshot
    if name in universe_snapshot.VALID_SIZES:
        symbols, _meta = universe_snapshot.load_or_fetch(name, as_of=as_of)
        return symbols

    valid = list(_UNIVERSES.keys()) + list(universe_snapshot.VALID_SIZES)
    raise KeyError(f"Unknown universe: {name}. Valid: {valid}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/data/test_universe.py -v`
Expected: PASS (new + existing universe tests).

- [ ] **Step 5: Commit**

```bash
git add src/data/universe.py tests/data/test_universe.py
git commit -m "feat: add resolve_universe for static + dynamic universes"
```

---

### Task 3: Artifact stamping helper — snapshot date + survivorship flag

**Files:**
- Modify: `src/research/artifacts.py`
- Test: `tests/research/test_artifacts.py`

**Interfaces:**
- Consumes: an existing metadata dict (as built by `build_scoring_metadata` / `build_screening_metadata`) and a snapshot meta dict (from Task 1, or `None` for static universes).
- Produces: `stamp_universe_provenance(metadata: dict, snapshot_meta: dict | None) -> dict` returning a NEW dict with `universe_snapshot_date` and `survivorship_bias` added. For a dynamic snapshot: `universe_snapshot_date = snapshot_meta["snapshot_date"]`, `survivorship_bias = True`. For `None` (static universe): `universe_snapshot_date = None`, `survivorship_bias = False`.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/research/test_artifacts.py
from src.research.artifacts import stamp_universe_provenance


def test_stamp_dynamic_universe_sets_date_and_bias_true():
    md = {"top_n": 10}
    out = stamp_universe_provenance(md, {"snapshot_date": "2026-07-14"})
    assert out["universe_snapshot_date"] == "2026-07-14"
    assert out["survivorship_bias"] is True
    assert out["top_n"] == 10  # original preserved
    assert "universe_snapshot_date" not in md  # original not mutated


def test_stamp_static_universe_sets_bias_false():
    out = stamp_universe_provenance({"top_n": 10}, None)
    assert out["universe_snapshot_date"] is None
    assert out["survivorship_bias"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/research/test_artifacts.py -k "stamp" -v`
Expected: FAIL (`ImportError: cannot import name 'stamp_universe_provenance'`).

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/research/artifacts.py
def stamp_universe_provenance(metadata: dict, snapshot_meta: dict | None) -> dict:
    """Return a copy of metadata annotated with universe provenance.

    Dynamic (snapshot-sourced) universes are flagged survivorship-biased and
    carry their snapshot date; static universes are flagged not-biased with a
    null snapshot date.
    """
    out = dict(metadata)
    if snapshot_meta is not None:
        out["universe_snapshot_date"] = snapshot_meta.get("snapshot_date")
        out["survivorship_bias"] = True
    else:
        out["universe_snapshot_date"] = None
        out["survivorship_bias"] = False
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/research/test_artifacts.py -k "stamp" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/research/artifacts.py tests/research/test_artifacts.py
git commit -m "feat: add universe provenance stamping for artifacts"
```

---

### Task 4: Wire `--universe-size` into the optimizer CLI + full-suite check

**Files:**
- Modify: `src/optimize.py` (CLI arg parsing + universe resolution)
- Test: `tests/research/test_walk_forward.py` (or the optimizer CLI test file if present)

**Interfaces:**
- Consumes: `resolve_universe` (Task 2), `stamp_universe_provenance` (Task 3).
- Produces: the optimizer CLI accepts `--universe-size {core30,large70,large100,mid400,topix500}` as an alternative to `--universe-name`; when given, symbols come from `resolve_universe(size)` and the run's artifact metadata is stamped via `stamp_universe_provenance`.

- [ ] **Step 1: Inspect the current optimizer CLI universe handling**

Run: `grep -n "universe-name\|universe_name\|get_universe\|add_argument" src/optimize.py`
Identify where the CLI resolves `--universe-name` to symbols. The new `--universe-size` path mirrors it but calls `resolve_universe` and stamps provenance. (No code block here — this is a read step to locate the exact insertion point in code you have not yet seen.)

- [ ] **Step 2: Write the failing test**

```python
# add to tests/research/test_walk_forward.py (or optimizer CLI test module)
def test_resolve_universe_size_flag_routes_to_dynamic(monkeypatch):
    # The CLI helper that turns args into a symbol list must honor --universe-size
    # by calling resolve_universe with the size.
    import src.optimize as opt
    captured = {}

    def fake_resolve(name, as_of=None):
        captured["name"] = name
        return ["7203.T", "6758.T"]

    monkeypatch.setattr("src.data.universe.resolve_universe", fake_resolve)
    symbols = opt._resolve_cli_universe(universe_name=None, universe_size="topix500")
    assert symbols == ["7203.T", "6758.T"]
    assert captured["name"] == "topix500"
```

Adjust the helper name/shape in Step 3 to match what the optimizer CLI actually needs after the Step 1 inspection; the intent is: `--universe-size` resolves via `resolve_universe`.

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/research/test_walk_forward.py -k "universe_size_flag" -v`
Expected: FAIL (`AttributeError: module 'src.optimize' has no attribute '_resolve_cli_universe'`).

- [ ] **Step 4: Write minimal implementation**

Add an `argparse` argument `--universe-size` with `choices=["core30","large70","large100","mid400","topix500"]` (default `None`). Add a small helper `_resolve_cli_universe(universe_name, universe_size)` that: if `universe_size` is set, returns `resolve_universe(universe_size)`; else falls back to the existing `--universe-name` resolution. Route the CLI's symbol resolution through this helper, and where the run's artifact metadata is built, call `stamp_universe_provenance(metadata, snapshot_meta)` (snapshot_meta from the snapshot loader when a size was used, else `None`).

- [ ] **Step 5: Run test + full suite**

Run: `uv run pytest tests/research/test_walk_forward.py -k "universe_size_flag" -v && uv run pytest -q`
Expected: target test PASS; full suite green, zero regressions.

- [ ] **Step 6: Commit**

```bash
git add src/optimize.py tests/research/test_walk_forward.py
git commit -m "feat: add --universe-size flag to optimizer for dynamic universes"
```

---

## Self-Review Notes

- **Spec coverage:** snapshot loader with hit/miss/failure/corrupt/as_of behavior (Task 1), `resolve_universe` static/dynamic/unknown routing (Task 2), artifact stamping with bias flag (Task 3), CLI wiring so the feature is actually usable + full-suite regression (Task 4). All spec sections map to a task.
- **get_universe untouched:** Task 2 only adds `resolve_universe`; the existing function and its callers are unchanged (asserted by `test_resolve_static_name_matches_get_universe`).
- **No silent fallback:** Task 1 `test_fetch_failure_raises_and_does_not_fall_back` locks this in.
- **as_of reserved, not point-in-time:** Task 1 `test_non_today_as_of_names_file_with_that_date` asserts the filename carries the date while symbols come straight from the fetcher (no historical lookup).
- **Token/live-fetch caveat:** all tests mock the fetcher; the real `get_list()` fetch is verified manually by the user with a token — noted in the spec, not automatable here.
- **Placeholder scan:** Task 4 Steps 1 and 4 are deliberately prose (they act on optimizer CLI code not yet read); every other code step has complete code. Task 4's test helper name is flagged as adjustable after inspection.
- **Deferred (per spec):** point-in-time historical constituents, delisted-stock handling, paid-tier depth — no tasks.
