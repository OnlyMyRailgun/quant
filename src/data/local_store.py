from __future__ import annotations

from collections.abc import Callable
import json
import warnings
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from src.data.yfinance_loader import fetch_daily_data


RAW_SUBDIR = ".data_store/raw"
CATALOG_SUBDIR = ".data_store/catalog"
MANIFEST_FILENAME = "manifest.jsonl"
Fetcher = Callable[[str, str, str], pd.DataFrame]


def _resolve_root(root: Path | str | None) -> Path:
    return Path(root or ".")


def _ensure_dirs(root: Path) -> None:
    (root / RAW_SUBDIR).mkdir(parents=True, exist_ok=True)
    (root / CATALOG_SUBDIR).mkdir(parents=True, exist_ok=True)


def _sanitize_symbol(symbol: str) -> str:
    if not symbol or "/" in symbol or "\\" in symbol:
        raise ValueError("symbol contains invalid path characters")
    if Path(symbol).name != symbol:
        raise ValueError("symbol contains invalid path segments")
    return symbol


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_iso_datetime(value: str) -> datetime:
    normalized = value
    if isinstance(normalized, str) and normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized)


def _ensure_series_utc(series: pd.Series) -> pd.Series:
    tz = series.dt.tz
    if tz is None:
        return series.dt.tz_localize(timezone.utc)
    return series.dt.tz_convert(timezone.utc)


@dataclass(frozen=True)
class ManifestRecord:
    symbol: str
    downloaded_start: date
    downloaded_end: date
    validated_start: date | None
    validated_end: date | None
    trading_days_expected: int
    trading_days_actual: int
    missing_count: int
    missing_date_samples: list[str]
    last_synced: datetime
    validation_status: str
    validation_issues: list[str]

    def __post_init__(self) -> None:  # pylint: disable=assigning-non-slot
        normalized = _normalize_datetime(self.last_synced)
        object.__setattr__(self, "last_synced", normalized)

    def to_dict(self) -> dict[str, Any]:
        validated_start = (
            self.validated_start.isoformat() if self.validated_start else None
        )
        validated_end = self.validated_end.isoformat() if self.validated_end else None
        return {
            "symbol": self.symbol,
            "downloaded_start": self.downloaded_start.isoformat(),
            "downloaded_end": self.downloaded_end.isoformat(),
            "validated_start": validated_start,
            "validated_end": validated_end,
            "trading_days_expected": self.trading_days_expected,
            "trading_days_actual": self.trading_days_actual,
            "missing_count": self.missing_count,
            "missing_date_samples": self.missing_date_samples,
            "last_synced": self.last_synced.isoformat().replace("+00:00", "Z"),
            "validation_status": self.validation_status,
            "validation_issues": self.validation_issues,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ManifestRecord":
        last_synced = _normalize_datetime(
            _parse_iso_datetime(data["last_synced"])
        )
        return cls(
            symbol=data["symbol"],
            downloaded_start=date.fromisoformat(data["downloaded_start"]),
            downloaded_end=date.fromisoformat(data["downloaded_end"]),
            validated_start=date.fromisoformat(data["validated_start"])
            if data.get("validated_start")
            else None,
            validated_end=date.fromisoformat(data["validated_end"])
            if data.get("validated_end")
            else None,
            trading_days_expected=int(data["trading_days_expected"]),
            trading_days_actual=int(data["trading_days_actual"]),
            missing_count=int(data["missing_count"]),
            missing_date_samples=list(data.get("missing_date_samples", [])),
            last_synced=last_synced,
            validation_status=data["validation_status"],
            validation_issues=list(data.get("validation_issues", [])),
        )


def get_raw_path(symbol: str, root: Path | str | None = None) -> Path:
    sanitized = _sanitize_symbol(symbol)
    return _resolve_root(root) / RAW_SUBDIR / f"{sanitized}.parquet"


def get_manifest_log_path(root: Path | str | None = None) -> Path:
    return _resolve_root(root) / CATALOG_SUBDIR / MANIFEST_FILENAME


def write_raw_parquet(symbol: str, frame: pd.DataFrame, root: Path | str | None = None) -> Path:
    sanitized = _sanitize_symbol(symbol)
    root_path = _resolve_root(root)
    _ensure_dirs(root_path)

    if "Date" not in frame.columns:
        raise ValueError("raw data must include a Date column")

    normalized = frame.copy()
    normalized["Date"] = pd.to_datetime(normalized["Date"], errors="coerce")
    normalized = normalized.sort_values("Date", kind="mergesort")
    normalized = normalized.drop_duplicates(subset="Date", keep="last")

    path = root_path / RAW_SUBDIR / f"{sanitized}.parquet"
    normalized.to_parquet(path, index=False)
    return path


def append_manifest_record(record: ManifestRecord, root: Path | str | None = None) -> Path:
    root_path = _resolve_root(root)
    _ensure_dirs(root_path)
    manifest_path = get_manifest_log_path(root=root_path)
    with manifest_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    return manifest_path


def read_manifest_records(symbol: str, root: Path | str | None = None) -> list[ManifestRecord]:
    manifest_path = get_manifest_log_path(root=root)
    if not manifest_path.exists():
        return []

    records: list[ManifestRecord] = []
    with manifest_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                record = ManifestRecord.from_dict(payload)
            except (KeyError, ValueError, TypeError):
                continue
            if record.symbol == symbol:
                records.append(record)
    return records


def read_latest_manifest_record(symbol: str, root: Path | str | None = None) -> ManifestRecord | None:
    records = read_manifest_records(symbol, root=root)
    if not records:
        return None
    return max(records, key=lambda rec: rec.last_synced.timestamp())


def merge_symbol_frames(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        return new.copy()
    if new.empty:
        return existing.copy()

    concatenated = pd.concat([existing, new], ignore_index=True)
    if "Date" in concatenated.columns:
        concatenated["Date"] = pd.to_datetime(concatenated["Date"], errors="raise")
        concatenated = concatenated.sort_values("Date", kind="mergesort")
        concatenated = concatenated.drop_duplicates(subset="Date", keep="last")
        return concatenated.reset_index(drop=True)

    return concatenated.drop_duplicates(keep="last").reset_index(drop=True)


def _prepare_fetched_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Ensure fetched frames expose a Date column derived from the index."""
    normalized = frame.copy()
    if normalized.empty:
        normalized["Date"] = pd.Series(dtype="datetime64[ns]")
        return normalized

    normalized["Date"] = pd.to_datetime(normalized.index, errors="coerce")
    return normalized.reset_index(drop=True)


def build_validation_summary(frame: pd.DataFrame) -> dict[str, Any]:
    issues: list[str] = []
    if "Date" not in frame.columns or frame.empty:
        return {
            "missing_count": 0,
            "missing_date_samples": [],
            "validation_status": "invalid",
            "validation_issues": ["empty_data"],
            "trading_days_expected": 0,
            "trading_days_actual": 0,
            "validated_start": None,
            "validated_end": None,
        }

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        timestamped = pd.to_datetime(frame["Date"], errors="coerce")

    timestamped = _ensure_series_utc(timestamped)

    if timestamped.isna().any():
        issues.append("invalid_date_values")

    valid_ts = timestamped.dropna()
    if valid_ts.empty:
        issues.append("invalid_date_values")
        return {
            "missing_count": 0,
            "missing_date_samples": [],
            "validation_status": "invalid",
            "validation_issues": sorted(set(issues)),
            "trading_days_expected": 0,
            "trading_days_actual": 0,
            "validated_start": None,
            "validated_end": None,
        }

    if not valid_ts.is_monotonic_increasing:
        issues.append("non_monotonic_timestamps")

    if valid_ts.duplicated().any():
        issues.append("duplicate_timestamps")

    numeric = frame.select_dtypes(include="number")
    if not numeric.empty and not np.all(np.isfinite(numeric.to_numpy())):
        issues.append("non_finite_values")

    if "Close" in frame.columns:
        close_series = pd.to_numeric(frame["Close"], errors="coerce")
        if close_series.isna().any() or (close_series <= 0).any():
            issues.append("non_positive_close")

    validated_start = valid_ts.min().date()
    validated_end = valid_ts.max().date()
    expected_range = pd.date_range(validated_start, validated_end, freq="B")
    observed = valid_ts.dt.normalize()
    if observed.dt.tz is not None:
        observed = observed.dt.tz_convert(timezone.utc).dt.tz_localize(None)
    observed = observed.drop_duplicates()
    observed_set = set(observed)
    missing = [
        dt.strftime("%Y-%m-%d")
        for dt in expected_range
        if dt.normalize() not in observed_set
    ]

    missing_count = len(missing)
    missing_samples = missing[:5]
    trading_days_expected = len(expected_range)
    trading_days_actual = len(observed)
    missing_ratio = (
        missing_count / trading_days_expected if trading_days_expected else 0.0
    )

    if missing_count > 0:
        issues.append("missing_data")

    structural_markers = {
        "invalid_date_values",
        "duplicate_timestamps",
        "non_monotonic_timestamps",
        "non_finite_values",
        "non_positive_close",
    }
    structural = any(issue in structural_markers for issue in issues)

    if structural:
        status = "invalid"
    elif missing_count == 0:
        status = "ok"
    elif missing_count <= 5 and missing_ratio < 0.01:
        status = "warning"
    else:
        status = "invalid"

    return {
        "missing_count": missing_count,
        "missing_date_samples": missing_samples,
        "validation_status": status,
        "validation_issues": sorted(set(issues)),
        "trading_days_expected": trading_days_expected,
        "trading_days_actual": trading_days_actual,
        "validated_start": validated_start,
        "validated_end": validated_end,
    }


def _coerce_date_range(value: str | date) -> tuple[str, date]:
    timestamp = pd.Timestamp(value)
    return timestamp.strftime("%Y-%m-%d"), timestamp.date()


def sync_symbol_history(
    symbol: str,
    start_date: str | date,
    end_date: str | date,
    root: Path | str | None = None,
    fetcher: Fetcher | None = None,
) -> ManifestRecord:
    """Fetch the requested range, validate the merged history, and log a manifest entry."""
    fetch_fn = fetcher or fetch_daily_data
    root_path = _resolve_root(root)
    _ensure_dirs(root_path)

    raw_path = get_raw_path(symbol, root=root_path)
    existing: pd.DataFrame = pd.DataFrame()
    if raw_path.exists():
        existing = pd.read_parquet(raw_path)

    start_str, downloaded_start = _coerce_date_range(start_date)
    end_str, downloaded_end = _coerce_date_range(end_date)

    fetched_raw = fetch_fn(symbol, start_str, end_str)
    prepared = _prepare_fetched_frame(fetched_raw)
    merged = merge_symbol_frames(existing, prepared)
    summary = build_validation_summary(merged)
    is_valid = summary["validation_status"] != "invalid"

    write_raw_parquet(symbol, merged, root=root_path)

    record = ManifestRecord(
        symbol=symbol,
        downloaded_start=downloaded_start,
        downloaded_end=downloaded_end,
        validated_start=summary["validated_start"] if is_valid else None,
        validated_end=summary["validated_end"] if is_valid else None,
        trading_days_expected=summary["trading_days_expected"],
        trading_days_actual=summary["trading_days_actual"],
        missing_count=summary["missing_count"],
        missing_date_samples=summary["missing_date_samples"],
        last_synced=datetime.now(timezone.utc),
        validation_status=summary["validation_status"],
        validation_issues=summary["validation_issues"],
    )

    append_manifest_record(record, root=root_path)
    return record


def sync_universe_history(
    symbols: list[str],
    start_date: str | date,
    end_date: str | date,
    root: Path | str | None = None,
    fetcher: Fetcher | None = None,
) -> dict[str, ManifestRecord]:
    """Sync multiple symbols by delegating to sync_symbol_history."""
    records: dict[str, ManifestRecord] = {}
    for symbol in symbols:
        records[symbol] = sync_symbol_history(
            symbol,
            start_date,
            end_date,
            root=root,
            fetcher=fetcher,
        )
    return records
