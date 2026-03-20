from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd


@dataclass(frozen=True)
class ScreeningRules:
    min_history_days: int = 252
    max_missing_ratio: float = 0.1
    min_latest_close: float = 5.0
    recent_window_days: int = 20
    min_recent_trading_day_ratio: float = 0.8
    max_recent_inactive_day_ratio: float = 0.2


def _to_bound_timestamp(value, *, end: bool) -> pd.Timestamp | None:
    if value is None:
        return None

    timestamp = pd.Timestamp(value)
    if isinstance(value, str):
        has_time = any(marker in value for marker in ("T", ":"))
        if not has_time:
            timestamp = timestamp.normalize()
            if end:
                timestamp = timestamp + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    elif isinstance(value, date) and not isinstance(value, datetime):
        timestamp = timestamp.normalize()
        if end:
            timestamp = timestamp + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)

    return timestamp


def _truncate_to_as_of(frame: pd.DataFrame, screen_as_of) -> pd.DataFrame:
    as_of = _to_bound_timestamp(screen_as_of, end=True)
    truncated = frame.loc[frame.index <= as_of]
    return truncated.sort_index()


def history_days(frame: pd.DataFrame) -> int:
    return int(len(frame))


def _close_series(frame: pd.DataFrame) -> pd.Series:
    if "Close" not in frame.columns:
        return pd.Series(dtype="float64", index=frame.index)
    return pd.to_numeric(frame["Close"], errors="coerce")


def missing_ratio(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 1.0

    closes = _close_series(frame)
    valid_count = int(closes.notna().sum())
    return float(1.0 - (valid_count / len(frame)))


def latest_close(frame: pd.DataFrame) -> float | None:
    if frame.empty:
        return None

    closes = _close_series(frame)
    if closes.empty:
        return None

    latest_value = closes.iloc[-1]
    if pd.isna(latest_value):
        return None
    return float(latest_value)


def _requested_window_frame(
    frame: pd.DataFrame,
    start,
    end,
    screen_as_of,
) -> pd.DataFrame:
    if frame.empty:
        return frame

    lower_bound = _to_bound_timestamp(start, end=False)
    upper_candidates = [_to_bound_timestamp(end, end=True), _to_bound_timestamp(screen_as_of, end=True)]
    upper_bound = min(candidate for candidate in upper_candidates if candidate is not None)

    window = frame.loc[frame.index <= upper_bound]
    if lower_bound is not None:
        window = window.loc[window.index >= lower_bound]
    return window.sort_index()


def recent_trading_day_ratio(frame: pd.DataFrame, recent_window_days: int) -> float:
    if frame.empty:
        return 0.0

    window = frame.tail(max(1, int(recent_window_days)))
    closes = _close_series(window)
    return float(closes.notna().sum() / len(window))


def recent_inactive_day_ratio(frame: pd.DataFrame, recent_window_days: int) -> float:
    if frame.empty:
        return 1.0

    return float(1.0 - recent_trading_day_ratio(frame, recent_window_days))


def _screen_symbol_with_window(
    symbol: str,
    frame: pd.DataFrame,
    start,
    end,
    screen_as_of,
    screening_rules: ScreeningRules,
) -> dict:
    available_frame = _truncate_to_as_of(frame, screen_as_of)
    window_frame = _requested_window_frame(available_frame, start, end, screen_as_of)

    metrics = {
        "history_days": history_days(available_frame),
        "missing_ratio": missing_ratio(window_frame),
        "latest_close": latest_close(available_frame),
        "recent_trading_day_ratio": recent_trading_day_ratio(window_frame, screening_rules.recent_window_days),
        "recent_inactive_day_ratio": recent_inactive_day_ratio(window_frame, screening_rules.recent_window_days),
    }

    reasons: list[str] = []
    if metrics["history_days"] < screening_rules.min_history_days:
        reasons.append("insufficient_history")
    if metrics["missing_ratio"] > screening_rules.max_missing_ratio:
        reasons.append("high_missing_ratio")
    if metrics["latest_close"] is None or metrics["latest_close"] < screening_rules.min_latest_close:
        reasons.append("low_latest_close")
    if metrics["recent_trading_day_ratio"] < screening_rules.min_recent_trading_day_ratio:
        reasons.append("weak_recent_trading_activity")
    if metrics["recent_inactive_day_ratio"] > screening_rules.max_recent_inactive_day_ratio:
        reasons.append("high_recent_inactive_day_ratio")

    eligible = not reasons
    return {
        "symbol": symbol,
        "eligible": eligible,
        "reasons": reasons,
        "metrics": metrics,
    }


def _summarize(results_by_symbol: dict[str, dict]) -> dict:
    requested_symbol_count = len(results_by_symbol)
    eligible_symbol_count = sum(1 for result in results_by_symbol.values() if result["eligible"])
    screened_out_symbol_count = requested_symbol_count - eligible_symbol_count

    summary = {
        "requested_symbol_count": requested_symbol_count,
        "eligible_symbol_count": eligible_symbol_count,
        "screened_out_symbol_count": screened_out_symbol_count,
        "eligibility_ratio": float(eligible_symbol_count / requested_symbol_count) if requested_symbol_count else 0.0,
    }

    for result in results_by_symbol.values():
        if result["eligible"]:
            continue
        for reason in set(result["reasons"]):
            key = f"screened_out_{reason}_count"
            summary[key] = summary.get(key, 0) + 1

    return summary


def screen_universe(
    candidate_symbols,
    data_dfs,
    start,
    end,
    screen_as_of,
    screening_rules: ScreeningRules | None = None,
) -> dict:
    rules = screening_rules or ScreeningRules()

    by_symbol: dict[str, dict] = {}
    eligible_symbols: list[str] = []
    rejected_symbols: list[str] = []

    for symbol in candidate_symbols:
        frame = data_dfs.get(symbol)
        if frame is None:
            record = {
                "symbol": symbol,
                "eligible": False,
                "reasons": ["missing_data"],
                "metrics": {
                    "history_days": 0,
                    "missing_ratio": 1.0,
                    "latest_close": None,
                    "recent_trading_day_ratio": 0.0,
                    "recent_inactive_day_ratio": 1.0,
                },
            }
        else:
            record = _screen_symbol_with_window(symbol, frame, start, end, screen_as_of, rules)

        by_symbol[symbol] = record
        if record["eligible"]:
            eligible_symbols.append(symbol)
        else:
            rejected_symbols.append(symbol)

    return {
        "eligible_symbols": eligible_symbols,
        "rejected_symbols": rejected_symbols,
        "by_symbol": by_symbol,
        "summary": _summarize(by_symbol),
    }
