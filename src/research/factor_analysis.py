"""Factor analysis adapter: scorer output → alphalens format."""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

import numpy as np
import pandas as pd

from src.scoring.multi_factor import (
    score_universe,
    DEFAULT_LOOKBACK_MOM,
    DEFAULT_LOOKBACK_VOL,
    DEFAULT_LOOKBACK_REV,
)

BookValuesInput = (
    Mapping[str, float | None]
    | Callable[[pd.Timestamp], Mapping[str, float | None] | None]
    | None
)


def _resolve_book_values(
    book_values: BookValuesInput,
    as_of_date: pd.Timestamp,
) -> Mapping[str, float | None] | None:
    if callable(book_values):
        return book_values(as_of_date)
    return book_values


def build_alphalens_factor_data(
    scored: pd.DataFrame,
    date: pd.Timestamp,
    factor_name: str = "total_score",
) -> pd.Series:
    """Convert a single-period scorer output to alphalens-compatible factor data."""
    if factor_name not in scored.columns:
        raise KeyError(
            f"Factor column '{factor_name}' not found. "
            f"Available: {list(scored.columns)}"
        )
    factor_series = scored.set_index("symbol")[factor_name]
    factor_series.index.name = "asset"
    multi_idx = pd.MultiIndex.from_arrays(
        [pd.Index([date] * len(factor_series), name="date"), factor_series.index],
        names=["date", "asset"],
    )
    return pd.Series(factor_series.values, index=multi_idx, name="factor")


def build_multi_period_factor_data(
    period_scores: dict[pd.Timestamp, pd.DataFrame],
    factor_name: str = "total_score",
) -> pd.Series:
    """Convert multiple periods of scorer output to alphalens factor data."""
    pieces = []
    for date in sorted(period_scores):
        scored = period_scores[date]
        if scored.empty:
            continue
        pieces.append(build_alphalens_factor_data(scored, date, factor_name))
    if not pieces:
        return pd.Series(
            [],
            index=pd.MultiIndex.from_arrays(
                [pd.Index([], name="date"), pd.Index([], name="asset")]
            ),
            name="factor",
            dtype="float64",
        )
    return pd.concat(pieces)


def build_alphalens_price_data(data_dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build alphalens-compatible price table from data_dfs."""
    close_series = {}
    for symbol, df in data_dfs.items():
        if df is None or df.empty or "Close" not in df.columns:
            continue
        close_series[symbol] = df["Close"]
    if not close_series:
        return pd.DataFrame()
    prices = pd.DataFrame(close_series)
    prices.index = pd.to_datetime(prices.index)
    prices.index.name = "date"
    return prices.sort_index()


def run_factor_analysis(
    data_dfs: dict[str, pd.DataFrame],
    start: pd.Timestamp,
    end: pd.Timestamp,
    factor_names: list[str] | None = None,
    weight_mom: float = 1.0,
    weight_vol: float = 1.0,
    weight_rev: float = 1.0,
    weight_val: float = 0.0,
    weight_qual: float = 0.0,
    book_values: BookValuesInput = None,
    roe_values: dict[str, float | None] | None = None,
    momentum_definition: str = "90d",
    artifact_dir: str | Path | None = None,
    reversal_filter_params=None,
    top_n: int = 10,
) -> dict:
    """Run factor analysis over a date range.

    Returns dict with:
        - "ic_summary": per-factor {mean_ic, std_ic, ir, rank_ic}
        - "factor_data": per-factor MultiIndex Series (for alphalens)
        - "price_data": DataFrame for alphalens
        - "period_scores": raw scored DataFrames per date
    """
    if factor_names is None:
        factor_names = ["total_score", "mom_raw", "vol_raw", "rev_raw"]
        if weight_val > 0.0 and book_values is not None:
            factor_names.append("val_raw")
        if weight_qual > 0.0 and roe_values is not None:
            factor_names.append("qual_raw")

    lookback = 252 if momentum_definition == "12_1" else max(
        DEFAULT_LOOKBACK_MOM, DEFAULT_LOOKBACK_VOL, DEFAULT_LOOKBACK_REV
    )

    rebalance_dates = pd.date_range(start, end, freq="BMS")

    period_scores: dict[pd.Timestamp, pd.DataFrame] = {}
    for date in rebalance_dates:
        window_dfs = {}
        for sym, df in data_dfs.items():
            if df is None or df.empty:
                continue
            sliced = df.loc[df.index < date]
            if len(sliced) >= lookback:
                window_dfs[sym] = sliced

        if not window_dfs:
            continue

        try:
            effective_book_values = _resolve_book_values(book_values, date)
            if momentum_definition != "90d":
                from src.research.research_scoring import score_research_universe
                scored = score_research_universe(
                    window_dfs, top_n=top_n,
                    weight_mom=weight_mom, weight_vol=weight_vol,
                    weight_rev=weight_rev, weight_val=weight_val,
                    weight_qual=weight_qual,
                    momentum_definition=momentum_definition,
                    book_values=effective_book_values,
                )
            else:
                scored = score_universe(
                    window_dfs, top_n=top_n,
                    weight_mom=weight_mom, weight_vol=weight_vol,
                    weight_rev=weight_rev, weight_val=weight_val,
                    weight_qual=weight_qual,
                    book_values=effective_book_values, roe_values=roe_values,
                )
        except ValueError:
            continue

        if scored.empty:
            continue

        if reversal_filter_params is not None:
            from src.research.reversal_filter import apply_reversal_filter
            result = apply_reversal_filter(scored, window_dfs, reversal_filter_params)
            scored = result["filtered_scores"]

        period_scores[date] = scored

    if not period_scores:
        raise ValueError(f"No valid scoring periods between {start} and {end}")

    # Build factor data for each factor
    factor_data = {}
    for fn in factor_names:
        factor_data[fn] = build_multi_period_factor_data(period_scores, fn)

    price_data = build_alphalens_price_data(data_dfs)

    # Compute IC summary per factor — manual Spearman rank IC for reliability
    ic_summary = {}
    for fn in factor_names:
        ic_values = []
        n_periods = 0
        for date in sorted(period_scores):
            scored_df = period_scores[date]
            if fn not in scored_df.columns:
                continue
            # Compute forward 1-day return for each symbol
            fwd_returns = {}
            for _, row in scored_df.iterrows():
                sym = row["symbol"]
                df = data_dfs.get(sym)
                if df is None or df.empty or sym not in price_data.columns:
                    continue
                # Find the price at the scoring date and the next day
                try:
                    px_col = price_data[sym]
                    mask = px_col.index >= date
                    if mask.sum() < 2:
                        continue
                    px_today = float(px_col.loc[mask].iloc[0])
                    px_next = float(px_col.loc[mask].iloc[1])
                    fwd_returns[sym] = (px_next / px_today - 1.0)
                except (IndexError, KeyError):
                    continue

            if len(fwd_returns) < 5:
                continue

            # Cross-sectional Spearman rank IC
            factor_vals = scored_df.set_index("symbol")[fn]
            fwd_series = pd.Series(fwd_returns)
            common = factor_vals.index.intersection(fwd_series.index)
            if len(common) < 5:
                continue

            rank_ic = factor_vals.loc[common].rank().corr(
                fwd_series.loc[common].rank(), method="spearman"
            )
            if not pd.isna(rank_ic):
                ic_values.append(rank_ic)
                n_periods += 1

        if ic_values:
            ic_series = pd.Series(ic_values)
            ic_summary[fn] = {
                "mean_ic": float(ic_series.mean()),
                "std_ic": float(ic_series.std()),
                "ir": float(ic_series.mean() / ic_series.std()) if ic_series.std() > 0 else 0.0,
                "n_periods": n_periods,
            }
        else:
            ic_summary[fn] = {"mean_ic": 0.0, "std_ic": 0.0, "ir": 0.0, "n_periods": 0}

    result: dict = {
        "ic_summary": ic_summary,
        "factor_data": factor_data,
        "price_data": price_data,
        "period_scores": period_scores,
    }

    if artifact_dir is not None:
        _write_tear_sheets(factor_data, price_data, ic_summary, Path(artifact_dir))

    return result


def _has_alphalens() -> bool:
    try:
        import alphalens  # noqa: F401
        return True
    except ImportError:
        return False


def _write_tear_sheets(factor_data, price_data, ic_summary, artifact_dir: Path):
    """Write alphalens tear sheets for each factor."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    try:
        import alphalens as al
    except ImportError:
        print("alphalens-reloaded not installed. Skipping tear sheets.")
        return

    for fn, factor_series in factor_data.items():
        if factor_series.empty:
            continue
        clean = factor_series.dropna()
        if clean.empty:
            continue

        try:
            factor_table = al.utils.get_clean_factor_and_forward_returns(
                factor=clean, prices=price_data, periods=[1, 5, 21],
            )
            ic = al.performance.mean_information_coefficient(factor_table)
            ic.to_csv(str(artifact_dir / f"ic_{fn}.csv"))

            # Quantile returns bar chart (returns tuple in some versions)
            mean_ret = al.performance.mean_return_by_quantile(factor_table)
            if isinstance(mean_ret, tuple):
                mean_ret = mean_ret[0]
            fig = al.plotting.plot_quantile_returns_bar(mean_ret)
            import matplotlib.pyplot as plt
            plt.savefig(str(artifact_dir / f"quantile_{fn}.png"), dpi=150, bbox_inches="tight")
            plt.close()
        except Exception as e:
            print(f"  [{fn}] tear sheet failed: {e}")

    # IC summary CSV
    summary_rows = []
    for fn, s in ic_summary.items():
        summary_rows.append({
            "factor": fn, "mean_ic": s["mean_ic"], "std_ic": s["std_ic"],
            "ir": s["ir"], "n_periods": s["n_periods"],
        })
    pd.DataFrame(summary_rows).to_csv(str(artifact_dir / "ic_summary.csv"), index=False)
    print(f"Alphalens artifacts written to {artifact_dir}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Factor analysis with alphalens")
    parser.add_argument("--universe-name", default="japan_large_30")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--momentum-definition", choices=["90d", "12_1"], default="90d")
    parser.add_argument("--weight-mom", type=float, default=1.0)
    parser.add_argument("--weight-vol", type=float, default=1.0)
    parser.add_argument("--weight-rev", type=float, default=1.0)
    parser.add_argument("--weight-val", type=float, default=0.0)
    parser.add_argument("--reversal-filter", action="store_true")
    parser.add_argument("--artifact-dir", type=Path, default=Path(".research_artifacts/factor_analysis"))
    parser.add_argument("--use-local-store", action="store_true")
    parser.add_argument("--local-store-root", type=Path, default=Path("."))
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)

    if args.use_local_store:
        from src.data import local_store
        from src.data.universe import get_universe
        symbols = get_universe(args.universe_name)
        try:
            raw = local_store.load_local_universe(symbols, str(start), str(end),
                warmup=300, strict_warmup=False, root=args.local_store_root)
            data_dfs = {}
            for sym, df in raw.items():
                if df is not None and not df.empty and "Date" in df.columns:
                    df = df.copy()
                    dates = pd.to_datetime(df["Date"]).values
                    df = df.drop(columns=["Date"])
                    df.index = pd.DatetimeIndex(dates)
                    data_dfs[sym] = df.sort_index()
        except Exception as e:
            print(f"Data load failed: {e}")
            return 1
    else:
        from src.data.bulk_loader import fetch_universe
        from src.data.universe import get_universe
        symbols = get_universe(args.universe_name)
        print(f"Fetching data for {len(symbols)} symbols...")
        data_dfs = fetch_universe(symbols, str(start), str(end))

    reversal_params = None
    if args.reversal_filter:
        from src.research.reversal_filter import ReversalFilterParams
        reversal_params = ReversalFilterParams()

    book_values = None
    if args.weight_val > 0.0:
        from src.data.fundamental_loader import get_book_values
        book_value_cache: dict[str, dict[str, float | None]] = {}

        def book_values(as_of_date: pd.Timestamp) -> dict[str, float | None]:
            key = pd.Timestamp(as_of_date).strftime("%Y-%m-%d")
            if key not in book_value_cache:
                book_value_cache[key] = get_book_values(symbols, as_of_date=pd.Timestamp(key))
            return book_value_cache[key]

    try:
        result = run_factor_analysis(
            data_dfs=data_dfs, start=start, end=end,
            weight_mom=args.weight_mom, weight_vol=args.weight_vol,
            weight_rev=args.weight_rev, weight_val=args.weight_val,
            book_values=book_values,
            momentum_definition=args.momentum_definition,
            reversal_filter_params=reversal_params,
            artifact_dir=args.artifact_dir,
        )
    except ValueError as e:
        print(f"Factor analysis failed: {e}")
        return 1

    print("\n=== FACTOR IC SUMMARY ===")
    print(f"{'Factor':<20} {'Mean IC':>8} {'Std IC':>8} {'IR':>8} {'N':>5}")
    print("-" * 52)
    for fn, s in result["ic_summary"].items():
        print(f"{fn:<20} {s['mean_ic']:>8.4f} {s['std_ic']:>8.4f} {s['ir']:>8.4f} {s['n_periods']:>5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
