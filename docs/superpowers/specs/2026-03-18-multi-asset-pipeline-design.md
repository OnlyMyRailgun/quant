# Multi-Asset Data Pipeline Design

## Objective

To upgrade the quantitative backtesting data infrastructure to support fetching, caching, and serving historical data for a "Universe" of stocks (e.g., TOPIX 100), rather than a single hardcoded symbol. This lays the groundwork for evaluating multiple assets simultaneously and calculating ranking "Factors."

## Core Challenges Addressed

*   **API Rate Limits & Speed**: Fetching 100+ daily stock series directly from `yfinance` takes minutes and risks Yahoo Finance rate limits/banning.
*   **Offline Reproducibility**: Quants need to test strategies over the exact same data without drift. Data should be downloaded once and re-read from disk forever locally.
*   **Universe Definition**: Need a structured way to request logical groups (`TOPIX100`, `NIKKEI225`) instead of passing raw lists of 100 strings.

## Architecture & Data Flow

1.  **Local Data Cache Store (`src/data/cache/`)**
    *   We will adopt **Parquet** (via `pandas` and `pyarrow`) as our fast, efficient local cache format. CSV is too slow for 100+ daily OHLCV files.
    *   File naming convention: `<CACHE_DIR>/<TICKER>.parquet`.

2.  **Universe Definition (`src/data/universe.py`)**
    *   Creates a module mapping strategic names to symbol lists.
    *   Provides functional helpers: `get_topix_top_10()`, `get_topix_30()` (we will hardcode a static subset for MVP, then scale to 100).
    *   *Note on ticker formatting*: Yahoo requires `.T` for Tokyo effectively, so `7203.T`, `6758.T`, etc.

3.  **Bulk Fetcher (`src/data/bulk_loader.py`)**
    *   Exposes `fetch_universe(symbols: list[str], start_date, end_date) -> dict[str, pd.DataFrame]`.
    *   **Logic**:
        *   Iterate over each symbol.
        *   Check if ` cache/<ticker>.parquet` exists and contains requested date range.
        *   If it does, load from disk instantly (Cache HIT).
        *   If not, use `yfinance` to download it (Cache MISS) -> Convert to Parquet -> Save to disk -> Return DataFrame.
    *   *Future-proofing*: Includes a `sleep(0.1)` on Yahoo API misses to prevent getting immediately blocked.

4.  **Integration into Engine (`src/engine/runner.py`)**
    *   The runner must be updated to accept a `dict[str, pd.DataFrame]` instead of a single `pd.DataFrame`.
    *   It will map each symbol to a separate `bt.feeds.PandasData(...)` and add it to `cerebro` with a named dataset constraint.

## Trade-offs

*   **Parquet vs CSV**: Parquet requires `pyarrow` to be added to `requirements.txt`, but significantly improves load times for large universes avoiding string parsing per row. **Recommendation: Use Parquet.**
*   **Dynamic vs Static Universe**: Real quants face survivorship bias (TOPIX 100 in 2013 was different than in 2023). For our MVP, we will use a **Static Universe** (current components) scaled to just the Top 30 first to test the pipeline before hitting 100 or attempting point-in-time index memberships.

## Implementation Steps

1. Add `pyarrow` to `requirements.txt`.
2. Implement caching logic in `bulk_loader.py`.
3. Hardcode a small `universe.py` module with top Japanese stocks.
4. Update `main.py` entry point to utilize `fetch_universe` instead of `fetch_daily_data`.
5. Write unit tests ensuring the cache hit prevents network requests (using Python mock or simple file exists checks).
