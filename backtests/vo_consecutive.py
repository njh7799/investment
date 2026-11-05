from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .core import MarketData
from .models import build_target_weights
from .vo_rebound import fill_stopped_addon_weights


@dataclass(frozen=True)
class ConsecutiveVariant:
    name: str
    family: str
    streak_asset: str
    return_asset: str | None
    sessions: int
    return_threshold: float | None


def variant_specs() -> tuple[ConsecutiveVariant, ...]:
    specs: list[ConsecutiveVariant] = []
    for asset in ("q", "t"):
        for sessions in (2, 3, 5):
            specs.append(ConsecutiveVariant(
                f"streak_{asset}_{sessions}", "consecutive_up_fill_stop",
                asset, None, sessions, None,
            ))
    combos = (
        ("combo_qq_3_2", "q", "q", 3, 0.02),
        ("combo_qq_5_3", "q", "q", 5, 0.03),
        ("combo_qt_3_6", "q", "t", 3, 0.06),
        ("combo_qt_5_9", "q", "t", 5, 0.09),
        ("combo_tq_3_2", "t", "q", 3, 0.02),
        ("combo_tq_5_3", "t", "q", 5, 0.03),
        ("combo_tt_3_6", "t", "t", 3, 0.06),
        ("combo_tt_5_9", "t", "t", 5, 0.09),
    )
    specs.extend(
        ConsecutiveVariant(name, "consecutive_up_return_fill_stop", streak, ret, sessions, threshold)
        for name, streak, ret, sessions, threshold in combos
    )
    return tuple(specs)


def consecutive_up(close: pd.Series, sessions: int) -> pd.Series:
    if close.isna().any():
        raise ValueError("consecutive-up signals do not permit missing closes")
    positive = close.diff() > 0.0
    valid = close.shift(sessions).notna()
    return positive.rolling(sessions).sum().eq(sessions).where(valid, False)


def cumulative_return(close: pd.Series, sessions: int) -> pd.Series:
    if close.isna().any():
        raise ValueError("return signals do not permit missing closes")
    return close.pct_change(sessions, fill_method=None)


def build_vo_consecutive_weights(
    data: MarketData,
) -> tuple[pd.DataFrame, dict[str, pd.Series], tuple[ConsecutiveVariant, ...]]:
    index = data.index
    tqqq = data.tqqq.loc[index]
    closes = {
        "q": data.qqq.loc[index, "Close"],
        "t": tqqq["Close"],
    }
    _, full_base = build_target_weights("vo", data)
    base = full_base.loc[index]
    specs = variant_specs()
    streaks = {
        (asset, sessions): consecutive_up(close, sessions)
        for asset, close in closes.items() for sessions in (2, 3, 5)
    }
    returns = {
        (asset, sessions): cumulative_return(close, sessions)
        for asset, close in closes.items() for sessions in (3, 5)
    }
    weights: dict[str, pd.Series] = {"vo": base}
    for spec in specs:
        signal = streaks[(spec.streak_asset, spec.sessions)]
        if spec.return_asset is not None and spec.return_threshold is not None:
            signal &= returns[(spec.return_asset, spec.sessions)] >= spec.return_threshold
        weights[spec.name], _ = fill_stopped_addon_weights(base, tqqq, signal)
    return tqqq, weights, specs
