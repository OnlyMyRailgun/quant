from __future__ import annotations

import pandas as pd

from src.research.artifacts import write_walk_forward_run


DEFAULT_CONTRIBUTOR_COUNT = 3


def _format_date(value: pd.Timestamp) -> str:
    return value.strftime("%Y-%m-%d")


def _coerce_symbol_returns(symbol_returns) -> pd.DataFrame:
    if symbol_returns is None:
        return pd.DataFrame(columns=["symbol", "return_pct"])
    if isinstance(symbol_returns, pd.DataFrame):
        if {"symbol", "return_pct"}.issubset(symbol_returns.columns):
            return symbol_returns.loc[:, ["symbol", "return_pct"]].copy()
        return pd.DataFrame(columns=["symbol", "return_pct"])

    frame = pd.DataFrame(symbol_returns)
    if frame.empty or not {"symbol", "return_pct"}.issubset(frame.columns):
        return pd.DataFrame(columns=["symbol", "return_pct"])
    return frame.loc[:, ["symbol", "return_pct"]].copy()


def _sort_contributors(frame: pd.DataFrame, ascending: bool, contributor_count: int) -> list[dict[str, object]]:
    if frame.empty:
        return []

    sorted_frame = frame.sort_values(
        by=["return_pct", "symbol"],
        ascending=[ascending, True],
        kind="mergesort",
    ).head(contributor_count)
    return [
        {
            "symbol": row["symbol"],
            "return_pct": round(float(row["return_pct"]), 4),
        }
        for row in sorted_frame.to_dict(orient="records")
    ]


def build_portfolio_diagnostics(
    symbol_returns,
    contributor_count: int = DEFAULT_CONTRIBUTOR_COUNT,
) -> dict[str, object]:
    frame = _coerce_symbol_returns(symbol_returns)
    if frame.empty:
        return {
            "hit_rate": None,
            "top_contributors": [],
            "bottom_contributors": [],
        }

    returns = pd.to_numeric(frame["return_pct"], errors="coerce")
    frame = frame.assign(return_pct=returns).dropna(subset=["return_pct"])
    if frame.empty:
        return {
            "hit_rate": None,
            "top_contributors": [],
            "bottom_contributors": [],
        }

    hit_rate = round(float((frame["return_pct"] > 0).mean()), 4)
    return {
        "hit_rate": hit_rate,
        "top_contributors": _sort_contributors(frame, ascending=False, contributor_count=contributor_count),
        "bottom_contributors": _sort_contributors(frame, ascending=True, contributor_count=contributor_count),
    }


def aggregate_portfolio_diagnostics(
    window_diagnostics: list[dict[str, object]],
    contributor_count: int = DEFAULT_CONTRIBUTOR_COUNT,
) -> dict[str, object]:
    hit_rates = [
        float(diagnostics["hit_rate"])
        for diagnostics in window_diagnostics
        if diagnostics.get("hit_rate") is not None
    ]

    aggregated_top_rows: list[dict[str, object]] = []
    aggregated_bottom_rows: list[dict[str, object]] = []
    for diagnostics in window_diagnostics:
        aggregated_top_rows.extend(diagnostics.get("top_contributors", []))
        aggregated_bottom_rows.extend(diagnostics.get("bottom_contributors", []))

    def aggregate_rows(rows: list[dict[str, object]], ascending: bool) -> list[dict[str, object]]:
        if not rows:
            return []
        frame = pd.DataFrame(rows)
        frame["return_pct"] = pd.to_numeric(frame["return_pct"], errors="coerce")
        frame = frame.dropna(subset=["return_pct"])
        if frame.empty:
            return []
        grouped = frame.groupby("symbol", as_index=False)["return_pct"].sum()
        return _sort_contributors(grouped, ascending=ascending, contributor_count=contributor_count)

    return {
        "avg_hit_rate": round(sum(hit_rates) / len(hit_rates), 4) if hit_rates else None,
        "top_contributors": aggregate_rows(aggregated_top_rows, ascending=False),
        "bottom_contributors": aggregate_rows(aggregated_bottom_rows, ascending=True),
    }


def aggregate_symbol_return_contributors(
    window_symbol_returns: list[object],
    contributor_count: int = DEFAULT_CONTRIBUTOR_COUNT,
) -> dict[str, object]:
    frames = [
        _coerce_symbol_returns(symbol_returns)
        for symbol_returns in window_symbol_returns
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return {
            "top_contributors": [],
            "bottom_contributors": [],
        }

    frame = pd.concat(frames, ignore_index=True)
    frame["return_pct"] = pd.to_numeric(frame["return_pct"], errors="coerce")
    frame = frame.dropna(subset=["return_pct"])
    if frame.empty:
        return {
            "top_contributors": [],
            "bottom_contributors": [],
        }

    grouped = frame.groupby("symbol", as_index=False)["return_pct"].sum()
    return {
        "top_contributors": _sort_contributors(grouped, ascending=False, contributor_count=contributor_count),
        "bottom_contributors": _sort_contributors(grouped, ascending=True, contributor_count=contributor_count),
    }


def build_walk_forward_windows(
    start: str,
    end: str,
    train_months: int,
    validation_months: int,
    step_months: int,
) -> list[dict[str, str]]:
    if min(train_months, validation_months, step_months) < 1:
        raise ValueError("train_months, validation_months, and step_months must be >= 1")

    overall_start = pd.Timestamp(start)
    overall_end = pd.Timestamp(end)
    if overall_end < overall_start:
        raise ValueError("end must be on or after start")

    windows: list[dict[str, str]] = []
    train_start = overall_start

    while True:
        train_end = train_start + pd.DateOffset(months=train_months) - pd.DateOffset(days=1)
        validation_start = train_end + pd.DateOffset(days=1)
        validation_end = validation_start + pd.DateOffset(months=validation_months) - pd.DateOffset(days=1)

        if validation_end > overall_end:
            break

        windows.append(
            {
                "train_start": _format_date(train_start),
                "train_end": _format_date(train_end),
                "validation_start": _format_date(validation_start),
                "validation_end": _format_date(validation_end),
            }
        )

        train_start = train_start + pd.DateOffset(months=step_months)

    return windows


def select_best_weights(
    weight_grid: list[tuple[float, float, float]],
    evaluate,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []

    for weight_mom, weight_vol, weight_rev in weight_grid:
        metrics = evaluate((weight_mom, weight_vol, weight_rev))
        rows.append(
            {
                "weights": {
                    "mom": weight_mom,
                    "vol": weight_vol,
                    "rev": weight_rev,
                },
                "return_pct": float(metrics["return_pct"]),
                "sharpe": float(metrics.get("sharpe", 0.0)),
            }
        )

    if not rows:
        raise ValueError("weight_grid must not be empty")

    rows.sort(
        key=lambda row: (
            row["return_pct"],
            row["sharpe"],
            row["weights"]["mom"],
            row["weights"]["vol"],
            row["weights"]["rev"],
        ),
        reverse=True,
    )
    return {"best": rows[0], "rows": rows}


def run_walk_forward_experiment(
    start: str,
    end: str,
    train_months: int,
    validation_months: int,
    step_months: int,
    weight_grid: list[tuple[float, float, float]],
    evaluate_training_window,
    evaluate_validation_window,
    evaluate_baseline_window,
    evaluate_one_shot_training_window=None,
    evaluate_one_shot_validation_window=None,
    evaluate_benchmark_windows=None,
    artifact_dir=None,
) -> dict[str, object]:
    windows = build_walk_forward_windows(
        start=start,
        end=end,
        train_months=train_months,
        validation_months=validation_months,
        step_months=step_months,
    )

    rows: list[dict[str, object]] = []
    baseline_total = 0.0
    one_shot_total = 0.0
    walk_forward_total = 0.0
    benchmark_totals: dict[str, float] = {}
    one_shot_best_weights: dict[str, float] | None = None
    benchmark_evaluators = evaluate_benchmark_windows or {}
    window_diagnostics: list[dict[str, object]] = []
    window_symbol_returns: list[object] = []

    if evaluate_one_shot_training_window is not None:
        one_shot_leaderboard = select_best_weights(
            weight_grid=weight_grid,
            evaluate=evaluate_one_shot_training_window,
        )
        one_shot_best_weights = one_shot_leaderboard["best"]["weights"]

    for window in windows:
        leaderboard = select_best_weights(
            weight_grid=weight_grid,
            evaluate=lambda weights: evaluate_training_window(window, weights),
        )
        best_weights = leaderboard["best"]["weights"]
        weight_tuple = (
            best_weights["mom"],
            best_weights["vol"],
            best_weights["rev"],
        )
        validation_metrics = evaluate_validation_window(window, weight_tuple)
        baseline_metrics = evaluate_baseline_window(window)
        one_shot_return_pct = None
        benchmark_returns: dict[str, float] = {}

        if one_shot_best_weights is not None:
            if evaluate_one_shot_validation_window is None:
                raise ValueError(
                    "evaluate_one_shot_validation_window is required when "
                    "evaluate_one_shot_training_window is provided"
                )

            one_shot_weight_tuple = (
                one_shot_best_weights["mom"],
                one_shot_best_weights["vol"],
                one_shot_best_weights["rev"],
            )
            one_shot_metrics = evaluate_one_shot_validation_window(
                window,
                one_shot_weight_tuple,
            )
            one_shot_return_pct = float(one_shot_metrics["return_pct"])
            one_shot_total += one_shot_return_pct

        for benchmark_name, evaluator in benchmark_evaluators.items():
            benchmark_metrics = evaluator(window)
            benchmark_return_pct = float(benchmark_metrics["return_pct"])
            benchmark_returns[benchmark_name] = benchmark_return_pct
            benchmark_totals[benchmark_name] = benchmark_totals.get(benchmark_name, 0.0) + benchmark_return_pct

        symbol_returns = validation_metrics.get("symbol_returns")
        diagnostics = build_portfolio_diagnostics(symbol_returns)
        window_diagnostics.append(diagnostics)
        window_symbol_returns.append(symbol_returns)

        baseline_total += float(baseline_metrics["return_pct"])
        walk_forward_total += float(validation_metrics["return_pct"])

        rows.append(
            {
                "rebalance_date": window["validation_start"],
                "train_start": window["train_start"],
                "train_end": window["train_end"],
                "validation_start": window["validation_start"],
                "validation_end": window["validation_end"],
                "weight_mom": best_weights["mom"],
                "weight_vol": best_weights["vol"],
                "weight_rev": best_weights["rev"],
                "train_return_pct": leaderboard["best"]["return_pct"],
                "validation_return_pct": float(validation_metrics["return_pct"]),
                "baseline_return_pct": float(baseline_metrics["return_pct"]),
                "one_shot_return_pct": one_shot_return_pct,
                "hit_rate": diagnostics["hit_rate"],
                "top_contributors": diagnostics["top_contributors"],
                "bottom_contributors": diagnostics["bottom_contributors"],
                **{
                    f"{benchmark_name}_return_pct": benchmark_return_pct
                    for benchmark_name, benchmark_return_pct in benchmark_returns.items()
                },
            }
        )

    weights = pd.DataFrame(rows)
    summary_diagnostics = aggregate_portfolio_diagnostics(window_diagnostics)
    summary_contributors = aggregate_symbol_return_contributors(window_symbol_returns)
    summary = {
        "window_count": len(rows),
        "baseline_return_pct": round(baseline_total, 10),
        "walk_forward_return_pct": round(walk_forward_total, 10),
        "active_return_pct": round(walk_forward_total - baseline_total, 10),
        "avg_hit_rate": summary_diagnostics["avg_hit_rate"],
        "top_contributors": summary_contributors["top_contributors"],
        "bottom_contributors": summary_contributors["bottom_contributors"],
    }
    if one_shot_best_weights is not None:
        summary["one_shot_return_pct"] = round(one_shot_total, 10)
        summary["one_shot_active_return_pct"] = round(one_shot_total - baseline_total, 10)
    for benchmark_name, benchmark_total in benchmark_totals.items():
        summary[f"{benchmark_name}_return_pct"] = round(benchmark_total, 10)
        summary[f"walk_forward_excess_vs_{benchmark_name}_pct"] = round(
            walk_forward_total - benchmark_total,
            10,
        )
    metadata = {
        "start": start,
        "end": end,
        "train_months": train_months,
        "validation_months": validation_months,
        "step_months": step_months,
    }
    if one_shot_best_weights is not None:
        metadata["one_shot_weights"] = one_shot_best_weights

    result: dict[str, object] = {
        "windows": windows,
        "weights": weights,
        "summary": summary,
        "metadata": metadata,
    }

    if artifact_dir is not None:
        result["artifacts"] = write_walk_forward_run(
            base_dir=artifact_dir,
            metadata=metadata,
            weights=weights,
            summary=summary,
        )

    return result
