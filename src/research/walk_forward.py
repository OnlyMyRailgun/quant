from __future__ import annotations

import pandas as pd

from src.research.artifacts import write_walk_forward_run


def _format_date(value: pd.Timestamp) -> str:
    return value.strftime("%Y-%m-%d")


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
                **{
                    f"{benchmark_name}_return_pct": benchmark_return_pct
                    for benchmark_name, benchmark_return_pct in benchmark_returns.items()
                },
            }
        )

    weights = pd.DataFrame(rows)
    summary = {
        "window_count": len(rows),
        "baseline_return_pct": round(baseline_total, 10),
        "walk_forward_return_pct": round(walk_forward_total, 10),
        "active_return_pct": round(walk_forward_total - baseline_total, 10),
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
