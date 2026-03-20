from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PriceFrameValidationResult:
    is_valid: bool
    issues: list[str]
    row_count: int
    start: str | None
    end: str | None


def _format_timestamp(value) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def validate_price_frame(df: pd.DataFrame) -> PriceFrameValidationResult:
    issues: list[str] = []
    row_count = len(df)

    if row_count == 0:
        issues.append("empty slice")
        return PriceFrameValidationResult(
            is_valid=False,
            issues=issues,
            row_count=row_count,
            start=None,
            end=None,
        )

    start = _format_timestamp(df.index[0])
    end = _format_timestamp(df.index[-1])

    if "Close" not in df.columns:
        issues.append("missing Close")

    if df.index.has_duplicates:
        issues.append("duplicate timestamps")

    if not df.index.is_monotonic_increasing:
        issues.append("unsorted timestamps")

    if "Close" in df.columns:
        close = pd.to_numeric(df["Close"], errors="coerce")
        finite_mask = np.isfinite(close.to_numpy(dtype="float64", copy=False))
        if not finite_mask.all():
            issues.append("non-finite close values")
        if (close[finite_mask] <= 0).any():
            issues.append("non-positive close values")

    return PriceFrameValidationResult(
        is_valid=not issues,
        issues=issues,
        row_count=row_count,
        start=start,
        end=end,
    )
