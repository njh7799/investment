#!/usr/bin/env python3
"""Download adjusted OHLC history and build a synthetic pre-launch TQQQ series."""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd
import yfinance as yf


OHLC = ["Open", "High", "Low", "Close"]
SYMBOLS = {"IXIC": "^IXIC", "QQQ": "QQQ", "TQQQ": "TQQQ"}
NEW_YORK = ZoneInfo("America/New_York")
ROUNDING_TOLERANCE = 1e-10


class DataValidationError(RuntimeError):
    """Raised when downloaded or derived market data is unsafe to publish."""


def fix_ohlc_roundoff(frame: pd.DataFrame) -> pd.DataFrame:
    """Clamp only floating-point-sized OHLC boundary violations."""
    result = frame.copy()
    body_high = result[["Open", "Close"]].max(axis=1)
    body_low = result[["Open", "Close"]].min(axis=1)
    high_gap = body_high - result["High"]
    low_gap = result["Low"] - body_low
    scale = result.abs().max(axis=1).clip(lower=1.0)

    fix_high = (high_gap > 0) & (high_gap <= ROUNDING_TOLERANCE * scale)
    fix_low = (low_gap > 0) & (low_gap <= ROUNDING_TOLERANCE * scale)
    result.loc[fix_high, "High"] = body_high.loc[fix_high]
    result.loc[fix_low, "Low"] = body_low.loc[fix_low]
    return result


def normalize_history(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Return a date-indexed adjusted OHLC frame with a stable schema."""
    if frame.empty:
        raise DataValidationError(f"{symbol}: Yahoo returned no history")
    missing = set(OHLC).difference(frame.columns)
    if missing:
        raise DataValidationError(f"{symbol}: missing columns: {sorted(missing)}")

    result = frame.loc[:, OHLC].copy()
    index = pd.DatetimeIndex(result.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    result.index = index.normalize()
    result.index.name = "Date"
    result = result[~result.index.duplicated(keep="last")].sort_index()
    return fix_ohlc_roundoff(result.astype(float))


def download_symbol(symbol: str, through: pd.Timestamp | None = None) -> pd.DataFrame:
    """Download all available adjusted daily data for one Yahoo symbol."""
    if hasattr(yf, "config"):
        yf.config.debug.hide_exceptions = False
    end = None
    if through is not None:
        end = (pd.Timestamp(through) + pd.Timedelta("1D")).strftime("%Y-%m-%d")
    history = yf.Ticker(symbol).history(
        period="max",
        end=end,
        interval="1d",
        auto_adjust=True,
        actions=False,
        repair=True,
    )
    return normalize_history(history, symbol)


def ensure_tqqq_actual_coverage(qqq: pd.DataFrame, tqqq: pd.DataFrame) -> None:
    """Reject missing TQQQ sessions after its first real observation."""
    first_actual = tqqq.index.min()
    last_actual = tqqq.index.max()
    expected = qqq.loc[first_actual:last_actual].index
    missing = expected.difference(tqqq.index)
    if not missing.empty:
        sample = ", ".join(day.strftime("%Y-%m-%d") for day in missing[:5])
        raise DataValidationError(
            f"TQQQ: {len(missing)} missing real sessions after launch: {sample}"
        )


def build_synthetic_tqqq(qqq: pd.DataFrame, actual: pd.DataFrame) -> pd.DataFrame:
    """Prepend a QQQ-derived 3x daily-return history to actual TQQQ data."""
    ensure_tqqq_actual_coverage(qqq, actual)
    first_actual = actual.index.min()
    if first_actual not in qqq.index:
        raise DataValidationError("TQQQ: first actual session is absent from QQQ")

    qqq_through_anchor = qqq.loc[:first_actual]
    if len(qqq_through_anchor) < 2:
        raise DataValidationError("TQQQ: not enough QQQ history for synthesis")

    close_factors = 1.0 + 3.0 * qqq_through_anchor["Close"].pct_change()
    if (close_factors.iloc[1:] <= 0).any():
        bad_date = close_factors.index[close_factors <= 0][0]
        raise DataValidationError(
            f"TQQQ: non-positive leveraged close factor on {bad_date.date()}"
        )

    relative_closes = close_factors.iloc[1:].cumprod()
    relative_closes = pd.concat(
        [pd.Series([1.0], index=qqq_through_anchor.index[:1]), relative_closes]
    )
    scale = actual.loc[first_actual, "Close"] / relative_closes.loc[first_actual]
    synthetic_closes = relative_closes * scale

    pre_dates = qqq.index[qqq.index < first_actual]
    synthetic = pd.DataFrame(index=pre_dates, columns=OHLC, dtype=float)
    synthetic["Close"] = synthetic_closes.loc[pre_dates]

    first_date = pre_dates[0]
    first_scale = synthetic.loc[first_date, "Close"] / qqq.loc[first_date, "Close"]
    synthetic.loc[first_date, ["Open", "High", "Low"]] = (
        qqq.loc[first_date, ["Open", "High", "Low"]] * first_scale
    )

    later_dates = pre_dates[1:]
    previous_qqq_close = qqq["Close"].shift(1).loc[later_dates]
    previous_synthetic_close = synthetic_closes.shift(1).loc[later_dates]
    for column in ["Open", "High", "Low"]:
        leveraged_return = 3.0 * (
            qqq.loc[later_dates, column] / previous_qqq_close - 1.0
        )
        synthetic.loc[later_dates, column] = previous_synthetic_close * (
            1.0 + leveraged_return
        )

    synthetic.index.name = "Date"
    combined = pd.concat([synthetic, actual.loc[first_actual:, OHLC]]).sort_index()
    combined.index.name = "Date"
    return fix_ohlc_roundoff(combined)


def validate_ohlc(frame: pd.DataFrame, name: str) -> None:
    """Validate the public CSV schema and core market-data invariants."""
    if list(frame.columns) != OHLC:
        raise DataValidationError(f"{name}: columns must be exactly {OHLC}")
    if frame.empty:
        raise DataValidationError(f"{name}: data is empty")
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise DataValidationError(f"{name}: dates must be sorted and unique")
    if frame.isna().any().any():
        raise DataValidationError(f"{name}: data contains missing values")

    for value in frame.to_numpy().ravel():
        if not math.isfinite(float(value)) or value <= 0:
            raise DataValidationError(f"{name}: prices must be finite and positive")

    low_ok = frame["Low"] <= frame[["Open", "Close"]].min(axis=1)
    high_ok = frame["High"] >= frame[["Open", "Close"]].max(axis=1)
    range_ok = frame["Low"] <= frame["High"]
    invalid = ~(low_ok & high_ok & range_ok)
    if invalid.any():
        first = invalid.index[invalid][0]
        raise DataValidationError(f"{name}: invalid OHLC range on {first.date()}")


def is_nasdaq_session(day: pd.Timestamp) -> bool:
    calendar = xcals.get_calendar("XNAS")
    return calendar.is_session(pd.Timestamp(day).normalize())


def latest_settled_session(now: pd.Timestamp | None = None) -> pd.Timestamp:
    """Return the latest XNAS session whose close is at least two hours old."""
    calendar = xcals.get_calendar("XNAS")
    current = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    else:
        current = current.tz_convert("UTC")

    new_york_day = pd.Timestamp(current.tz_convert(NEW_YORK).date())
    if calendar.is_session(new_york_day):
        close = calendar.session_close(new_york_day)
        if current >= close + pd.Timedelta("2h"):
            return new_york_day
        return pd.Timestamp(calendar.previous_session(new_york_day)).tz_localize(None)

    previous = calendar.date_to_session(new_york_day, direction="previous")
    return pd.Timestamp(previous).tz_localize(None)


def fetch_all(through: pd.Timestamp | None = None) -> Dict[str, pd.DataFrame]:
    downloaded = {
        name: download_symbol(symbol, through) for name, symbol in SYMBOLS.items()
    }
    downloaded["TQQQ"] = build_synthetic_tqqq(
        downloaded["QQQ"], downloaded["TQQQ"]
    )
    for name, frame in downloaded.items():
        validate_ohlc(frame, name)
    return downloaded


def verify_target_session(data: Dict[str, pd.DataFrame], target: pd.Timestamp) -> None:
    missing = [name for name, frame in data.items() if target not in frame.index]
    if missing:
        raise DataValidationError(
            f"latest session {target.date()} is missing from: {', '.join(missing)}"
        )


def fetch_with_retries(
    target: pd.Timestamp | None,
    attempts: int,
    retry_delay: int,
    fetcher: Callable[[], Dict[str, pd.DataFrame]] = fetch_all,
) -> Dict[str, pd.DataFrame]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            data = fetcher()
            if target is not None:
                verify_target_session(data, target)
            return data
        except Exception as error:  # retries network errors and unsafe partial data
            last_error = error
            if attempt == attempts:
                break
            print(
                f"Attempt {attempt}/{attempts} failed: {error}; "
                f"retrying in {retry_delay}s",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(retry_delay)
    raise RuntimeError(f"market data update failed after {attempts} attempts") from last_error


def write_csvs(data: Dict[str, pd.DataFrame], output_dir: Path) -> None:
    """Validate every frame, then atomically replace each destination file."""
    for name in SYMBOLS:
        validate_ohlc(data[name], name)

    output_dir.mkdir(parents=True, exist_ok=True)
    temporary: Dict[str, Path] = {}
    try:
        for name in SYMBOLS:
            temp_path = output_dir / f".{name}.csv.tmp"
            data[name].to_csv(
                temp_path,
                columns=OHLC,
                index=True,
                index_label="Date",
                date_format="%Y.%m.%d",
                float_format="%.10f",
                lineterminator="\n",
            )
            temporary[name] = temp_path
        for name, temp_path in temporary.items():
            os.replace(temp_path, output_dir / f"{name}.csv")
    finally:
        for temp_path in temporary.values():
            temp_path.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["full", "daily"], default="full")
    parser.add_argument("--output-dir", type=Path, default=Path("assets"))
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--retry-delay", type=int, default=60)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.attempts < 1 or args.retry_delay < 0:
        raise ValueError("attempts must be positive and retry-delay cannot be negative")

    target: pd.Timestamp | None = None
    settled_session = latest_settled_session()
    if args.mode == "daily":
        target = pd.Timestamp(datetime.now(NEW_YORK).date())
        if not is_nasdaq_session(target):
            print(f"{target.date()} is not a Nasdaq session; nothing to update")
            return 0
        if target > settled_session:
            raise DataValidationError(
                f"{target.date()} has not been closed for two hours yet"
            )

    data = fetch_with_retries(
        target,
        args.attempts,
        args.retry_delay,
        fetcher=lambda: fetch_all(settled_session),
    )
    data = {name: frame.loc[:settled_session].copy() for name, frame in data.items()}
    for name, frame in data.items():
        validate_ohlc(frame, name)
    write_csvs(data, args.output_dir)
    print(
        "Updated "
        + ", ".join(
            f"{name} ({len(data[name])} rows through {data[name].index.max().date()})"
            for name in SYMBOLS
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
