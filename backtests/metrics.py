from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .core import BacktestResult


def drawdown_episodes(equity: pd.Series) -> pd.DataFrame:
    """Return non-overlapping high-water-mark drawdown episodes."""
    equity = equity.dropna().astype(float)
    if equity.empty or not equity.index.is_monotonic_increasing or equity.index.has_duplicates:
        raise ValueError("equity dates must be complete, sorted, and unique")
    if (equity <= 0).any():
        raise ValueError("equity must stay positive")

    rows: list[dict[str, object]] = []
    peak_date = equity.index[0]
    peak_value = float(equity.iloc[0])
    trough_date = peak_date
    trough_value = peak_value
    active = False

    for date, raw_value in equity.iloc[1:].items():
        value = float(raw_value)
        if not active:
            if value >= peak_value:
                peak_date = date
                peak_value = value
                trough_date = date
                trough_value = value
            else:
                active = True
                trough_date = date
                trough_value = value
            continue

        if value < trough_value:
            trough_date = date
            trough_value = value
        if value >= peak_value:
            rows.append(
                {
                    "peak_date": peak_date,
                    "trough_date": trough_date,
                    "recovery_date": date,
                    "mdd": trough_value / peak_value - 1.0,
                    "underwater_days": int((date - peak_date).days),
                }
            )
            active = False
            peak_date = date
            peak_value = value
            trough_date = date
            trough_value = value

    if active:
        rows.append(
            {
                "peak_date": peak_date,
                "trough_date": trough_date,
                "recovery_date": pd.NaT,
                "mdd": trough_value / peak_value - 1.0,
                "underwater_days": int((equity.index[-1] - peak_date).days),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "peak_date",
            "trough_date",
            "recovery_date",
            "mdd",
            "underwater_days",
        ],
    )


def _drawdown_stats(equity: pd.Series) -> dict[str, object]:
    running = equity.cummax()
    drawdown = equity / running - 1.0
    trough = drawdown.idxmin()
    peak_value = running.loc[trough]
    peak = equity.loc[:trough][equity.loc[:trough] == peak_value].index[-1]
    recovered = equity.loc[trough:][equity.loc[trough:] >= peak_value]
    recovery = None if recovered.empty else recovered.index[0]

    longest_days = 0
    underwater_start = None
    current_start = None
    for date, value in drawdown.items():
        if value < -1e-12 and current_start is None:
            prior = drawdown.loc[:date]
            zeroes = prior[prior >= -1e-12]
            current_start = zeroes.index[-1] if not zeroes.empty else equity.index[0]
        elif value >= -1e-12 and current_start is not None:
            days = (date - current_start).days
            if days > longest_days:
                longest_days, underwater_start = days, current_start
            current_start = None
    if current_start is not None:
        days = (equity.index[-1] - current_start).days
        if days > longest_days:
            longest_days, underwater_start = days, current_start

    return {
        "mdd": float(drawdown.min()),
        "mdd_peak": peak.date().isoformat(),
        "mdd_trough": trough.date().isoformat(),
        "drawdown_duration_days": int((trough - peak).days),
        "recovery_date": None if recovery is None else recovery.date().isoformat(),
        "recovery_period_days": None if recovery is None else int((recovery - trough).days),
        "mdd_time_underwater_days": None if recovery is None else int((recovery - peak).days),
        "longest_time_underwater_days": int(longest_days),
        "longest_underwater_start": None if underwater_start is None else underwater_start.date().isoformat(),
    }


def summarize(result: BacktestResult) -> dict[str, object]:
    equity = result.equity.dropna()
    elapsed_years = (equity.index[-1] - equity.index[0]).days / 365.2425
    total_return = equity.iloc[-1] / result.initial_cash - 1.0
    cagr = math.pow(equity.iloc[-1] / result.initial_cash, 1.0 / elapsed_years) - 1.0 if elapsed_years > 0 else np.nan
    trade_dates = int(result.trades.index.nunique()) if not result.trades.empty else 0
    metrics: dict[str, object] = {
        "start": equity.index[0].date().isoformat(),
        "end": equity.index[-1].date().isoformat(),
        "start_equity": float(result.initial_cash),
        "end_equity": float(equity.iloc[-1]),
        "total_return": float(total_return),
        "cagr": float(cagr),
        "trade_count": trade_dates,
        "annual_trades": float(trade_dates / elapsed_years) if elapsed_years > 0 else 0.0,
        "fees": float(result.trades["Fee"].sum()) if not result.trades.empty else 0.0,
    }
    metrics.update(_drawdown_stats(equity))
    return metrics
