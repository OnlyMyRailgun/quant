from __future__ import annotations

import argparse
from pathlib import Path

from src.research.approved_params import (
    DEFAULT_APPROVED_PARAMS_FILE,
    approve_walk_forward_params,
    load_walk_forward_run_candidates,
)


def _find_run_by_id(runs: list[dict], run_id: str) -> dict:
    for run in runs:
        if run.get("run_id") == run_id:
            return run
    raise ValueError(f"No walk-forward run found for run_id={run_id}")


def _print_runs(runs: list[dict]) -> None:
    if not runs:
        print("No walk-forward runs found.")
        return

    print(
        "run_id\twindow_count\tbaseline_return_pct\twalk_forward_return_pct\tactive_return_pct\tlatest_rebalance_date\tweights_path"
    )
    for run in runs:
        summary = run["summary"]
        print(
            f"{run['run_id']}\t"
            f"{summary.get('window_count', '')}\t"
            f"{summary.get('baseline_return_pct', '')}\t"
            f"{summary.get('walk_forward_return_pct', '')}\t"
            f"{summary.get('active_return_pct', '')}\t"
            f"{run.get('latest_rebalance_date', '')}\t"
            f"{run.get('weights_path', '')}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Approve walk-forward parameters for paper trading")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List candidate walk-forward runs")
    list_parser.add_argument("--artifact-dir", type=Path, default=Path(".research_artifacts"))

    approve_parser = subparsers.add_parser("approve", help="Approve a specific walk-forward run")
    approve_parser.add_argument("--artifact-dir", type=Path, default=Path(".research_artifacts"))
    approve_parser.add_argument("--run-id", required=True)
    approve_parser.add_argument("--rebalance-date", required=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _build_parser()
        args = parser.parse_args(argv)
        runs = load_walk_forward_run_candidates(args.artifact_dir)
        if args.command == "list":
            _print_runs(runs)
            return 0

        run = _find_run_by_id(runs, args.run_id)
        rebalance_date = args.rebalance_date or run["latest_rebalance_date"]
        approve_walk_forward_params(
            artifact_dir=args.artifact_dir,
            run_record=run,
            rebalance_date=rebalance_date,
        )
        approved_path = args.artifact_dir / DEFAULT_APPROVED_PARAMS_FILE
        print(f"Approved run {args.run_id} at rebalance_date {rebalance_date}")
        print(f"Wrote approved params to {approved_path}")
        return 0
    except SystemExit as exc:
        print("Approval workflow failed: invalid command arguments")
        return int(exc.code)
    except Exception as exc:
        print(f"Approval workflow failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
