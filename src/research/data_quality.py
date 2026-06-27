from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.data import local_store
from src.data.universe import get_universe
from src.research.artifacts import DEFAULT_ARTIFACT_DIR, write_data_quality_run
from src.research.data_validation import validate_price_frame


@dataclass(frozen=True)
class DataQualityThresholds:
    max_critical_errors: int = 0
    allowed_manifest_statuses: tuple[str, ...] = ("ok", "warning")


def _date_string(value) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _load_raw_frame(symbol: str, root: Path) -> pd.DataFrame | None:
    raw_path = local_store.get_raw_path(symbol, root=root)
    if not raw_path.exists():
        return None

    frame = pd.read_parquet(raw_path)
    if "Date" in frame.columns:
        frame = frame.copy()
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
        frame = frame.dropna(subset=["Date"]).sort_values("Date", kind="mergesort")
        frame = frame.set_index("Date")
    return frame


def _coverage_row(
    symbol: str,
    status: str,
    manifest,
    frame: pd.DataFrame | None,
    start: str,
    end: str,
    row_count: int,
) -> dict:
    raw_start = _date_string(frame.index.min()) if frame is not None and len(frame) else None
    raw_end = _date_string(frame.index.max()) if frame is not None and len(frame) else None
    return {
        "symbol": symbol,
        "status": status,
        "manifest_status": manifest.validation_status if manifest else None,
        "manifest_validated_start": manifest.validated_start.isoformat()
        if manifest and manifest.validated_start
        else None,
        "manifest_validated_end": manifest.validated_end.isoformat()
        if manifest and manifest.validated_end
        else None,
        "raw_start": raw_start,
        "raw_end": raw_end,
        "requested_start": start,
        "requested_end": end,
        "row_count": row_count,
    }


def _error(symbol: str, severity: str, issue_code: str, detail: str) -> dict[str, str]:
    return {"symbol": symbol, "severity": severity, "issue_code": issue_code, "detail": detail}


def run_data_quality_report(
    symbols: Iterable[str],
    start: str,
    end: str,
    root: Path | str = ".",
    artifact_dir: Path | str = DEFAULT_ARTIFACT_DIR,
    thresholds: DataQualityThresholds | None = None,
    run_id: str | None = None,
    timestamp: str | None = None,
    created_at: str | None = None,
) -> dict[str, Path]:
    thresholds = thresholds or DataQualityThresholds()
    root_path = Path(root)
    artifact_path = Path(artifact_dir)
    requested_symbols = list(symbols)
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    coverage_rows: list[dict] = []
    error_rows: list[dict[str, str]] = []

    for symbol in requested_symbols:
        manifest = local_store.read_latest_manifest_record(symbol, root=root_path)
        frame = _load_raw_frame(symbol, root_path)
        row_count = 0

        if manifest is None:
            error_rows.append(_error(symbol, "critical", "missing_manifest", "no manifest record found"))
        else:
            if manifest.validation_status not in thresholds.allowed_manifest_statuses:
                error_rows.append(
                    _error(symbol, "critical", "manifest_status", f"status={manifest.validation_status}")
                )
            if manifest.validated_start is None or manifest.validated_end is None:
                error_rows.append(_error(symbol, "critical", "manifest_coverage", "validated range is missing"))
            elif start_ts.date() < manifest.validated_start or end_ts.date() > manifest.validated_end:
                error_rows.append(
                    _error(
                        symbol,
                        "critical",
                        "manifest_coverage",
                        f"validated={manifest.validated_start.isoformat()}..{manifest.validated_end.isoformat()}",
                    )
                )
            for issue in manifest.validation_issues:
                error_rows.append(_error(symbol, "warning", "manifest_validation_issue", issue))

        if frame is None:
            error_rows.append(_error(symbol, "critical", "missing_raw", "raw parquet file not found"))
        else:
            sliced = frame.loc[(frame.index >= start_ts) & (frame.index <= end_ts)]
            row_count = len(sliced)
            validation = validate_price_frame(sliced)
            for issue in validation.issues:
                error_rows.append(_error(symbol, "critical", issue.replace(" ", "_"), issue))

        symbol_errors = [
            row for row in error_rows if row["symbol"] == symbol and row["severity"] == "critical"
        ]
        coverage_rows.append(
            _coverage_row(
                symbol=symbol,
                status="fail" if symbol_errors else "pass",
                manifest=manifest,
                frame=frame,
                start=start,
                end=end,
                row_count=row_count,
            )
        )

    coverage = pd.DataFrame(coverage_rows)
    validation_errors = pd.DataFrame(error_rows, columns=["symbol", "severity", "issue_code", "detail"])
    critical_error_count = (
        int((validation_errors["severity"] == "critical").sum()) if not validation_errors.empty else 0
    )
    warning_count = int((validation_errors["severity"] == "warning").sum()) if not validation_errors.empty else 0
    failed_symbol_count = int((coverage["status"] == "fail").sum()) if not coverage.empty else 0
    summary = {
        "requested_symbol_count": len(requested_symbols),
        "passed_symbol_count": len(requested_symbols) - failed_symbol_count,
        "failed_symbol_count": failed_symbol_count,
        "critical_error_count": critical_error_count,
        "warning_count": warning_count,
        "status": "pass" if critical_error_count <= thresholds.max_critical_errors else "fail",
    }

    metadata = {
        "root": str(root_path),
        "start": start,
        "end": end,
        "symbols": requested_symbols,
        "thresholds": {
            "max_critical_errors": thresholds.max_critical_errors,
            "allowed_manifest_statuses": list(thresholds.allowed_manifest_statuses),
        },
    }
    return write_data_quality_run(
        base_dir=artifact_path,
        metadata=metadata,
        coverage=coverage,
        validation_errors=validation_errors,
        summary=summary,
        run_id=run_id,
        timestamp=timestamp,
        created_at=created_at,
    )


def _parse_symbols(value: str | None) -> list[str]:
    if not value:
        return []
    return [symbol.strip() for symbol in value.split(",") if symbol.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local research data-quality checks.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--symbols", help="Comma-separated symbols to validate")
    source.add_argument("--universe-name", help="Named universe from src.data.universe")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--max-critical-errors", type=int, default=0)
    args = parser.parse_args(argv)

    symbols = _parse_symbols(args.symbols) if args.symbols else get_universe(args.universe_name)
    paths = run_data_quality_report(
        symbols=symbols,
        start=args.start,
        end=args.end,
        root=args.root,
        artifact_dir=args.artifact_dir,
        thresholds=DataQualityThresholds(max_critical_errors=args.max_critical_errors),
    )

    summary = json.loads(Path(paths["summary"]).read_text(encoding="utf-8"))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
