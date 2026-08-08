from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .core import MarketData
from .models import build_target_weights


@dataclass(frozen=True)
class MaSignalSpec:
    name: str
    kind: str
    short: int | None = None
    middle: int | None = None
    long: int | None = None
    band: float = 0.0


@dataclass(frozen=True)
class MaVariantSpec:
    name: str
    family: str
    signal_asset: str
    signal: str
    action: str


STANDALONE_ACTIONS = ("full_cash", "half_floor")
VO_ACTIONS = (
    "trend_cap",
    "trend_floor",
    "blend",
    "bear_step_down",
    "bull_step_up",
    "cut_confirm",
    "raise_confirm",
    "both_confirm",
)


def signal_specs() -> tuple[MaSignalSpec, ...]:
    specs: list[MaSignalSpec] = []
    for lookback in (20, 50, 100, 150, 200, 250):
        specs.append(MaSignalSpec(f"price_sma_{lookback}", "price_sma", long=lookback))
    for short in (5, 10, 20, 50, 100):
        for long in (20, 50, 100, 150, 200, 250):
            if short < long:
                specs.append(MaSignalSpec(f"cross_{short}_{long}", "cross", short=short, long=long))
    for short, long in ((10, 50), (20, 100), (50, 200), (100, 200)):
        for band in (0.01, 0.02, 0.03):
            code = int(round(band * 100))
            specs.append(
                MaSignalSpec(
                    f"band_cross_{short}_{long}_{code}",
                    "band_cross",
                    short=short,
                    long=long,
                    band=band,
                )
            )
    for short, middle, long in (
        (5, 20, 100),
        (10, 50, 200),
        (20, 50, 200),
        (20, 100, 200),
        (50, 100, 200),
        (50, 150, 200),
    ):
        specs.append(
            MaSignalSpec(
                f"triple_{short}_{middle}_{long}",
                "triple",
                short=short,
                middle=middle,
                long=long,
            )
        )
    for lookback in (50, 100, 150, 200, 250):
        specs.append(MaSignalSpec(f"slope_{lookback}_20", "slope", long=lookback, short=20))
    return tuple(specs)


def _stateful_band(fast: pd.Series, slow: pd.Series, band: float) -> pd.Series:
    state = 1.0
    values: list[float] = []
    for fast_value, slow_value in zip(fast, slow):
        if pd.notna(fast_value) and pd.notna(slow_value):
            if fast_value > slow_value * (1.0 + band):
                state = 1.0
            elif fast_value < slow_value * (1.0 - band):
                state = 0.0
        values.append(state)
    return pd.Series(values, index=fast.index, dtype=float)


def moving_average_score(close: pd.Series, spec: MaSignalSpec) -> pd.Series:
    if spec.kind == "price_sma":
        slow = close.rolling(int(spec.long)).mean()
        score = (close >= slow).astype(float)
        return score.where(slow.notna(), 1.0)
    if spec.kind in {"cross", "band_cross"}:
        fast = close.rolling(int(spec.short)).mean()
        slow = close.rolling(int(spec.long)).mean()
        if spec.kind == "band_cross":
            return _stateful_band(fast, slow, spec.band)
        score = (fast >= slow).astype(float)
        return score.where(fast.notna() & slow.notna(), 1.0)
    if spec.kind == "triple":
        fast = close.rolling(int(spec.short)).mean()
        middle = close.rolling(int(spec.middle)).mean()
        slow = close.rolling(int(spec.long)).mean()
        valid = fast.notna() & middle.notna() & slow.notna()
        bullish = (fast >= middle) & (middle >= slow)
        bearish = (fast < middle) & (middle < slow)
        score = pd.Series(np.select([bullish, bearish], [1.0, 0.0], default=0.5), index=close.index)
        return score.where(valid, 1.0)
    if spec.kind == "slope":
        slow = close.rolling(int(spec.long)).mean()
        valid = slow.notna() & slow.shift(int(spec.short)).notna()
        score = ((close >= slow) & (slow >= slow.shift(int(spec.short)))).astype(float)
        return score.where(valid, 1.0)
    raise ValueError(f"unknown moving-average signal: {spec.kind}")


def _gate_vo(base: pd.Series, score: pd.Series, action: str) -> pd.Series:
    state = float(base.iloc[0])
    values: list[float] = []
    for base_weight, trend_score in zip(base.astype(float), score.astype(float)):
        if base_weight < state:
            allowed = action in {"cut_confirm", "both_confirm"} and trend_score < 0.5
            if action == "raise_confirm" or allowed:
                state = float(base_weight)
        elif base_weight > state:
            allowed = action in {"raise_confirm", "both_confirm"} and trend_score > 0.5
            if action == "cut_confirm" or allowed:
                state = float(base_weight)
        values.append(state)
    return pd.Series(values, index=base.index, dtype=float)


def apply_vo_trend(base: pd.Series, score: pd.Series, action: str) -> pd.Series:
    score = score.reindex(base.index).fillna(1.0).clip(0.0, 1.0)
    if action == "trend_cap":
        return pd.Series(np.minimum(base, score), index=base.index, dtype=float)
    if action == "trend_floor":
        return pd.Series(np.maximum(base, score), index=base.index, dtype=float)
    if action == "blend":
        return (base + score) / 2.0
    if action == "bear_step_down":
        return (base - 0.5 * (1.0 - score)).clip(lower=0.0)
    if action == "bull_step_up":
        return (base + 0.5 * score).clip(upper=1.0)
    if action in {"cut_confirm", "raise_confirm", "both_confirm"}:
        return _gate_vo(base, score, action)
    raise ValueError(f"unknown VO trend action: {action}")


def variant_specs() -> tuple[MaVariantSpec, ...]:
    signals = signal_specs()
    variants: list[MaVariantSpec] = []
    for signal in signals:
        for action in STANDALONE_ACTIONS:
            variants.append(
                MaVariantSpec(
                    f"standalone_qqq_{signal.name}_{action}",
                    "standalone",
                    "qqq",
                    signal.name,
                    action,
                )
            )

    vo_signal_names = {
        *(f"price_sma_{lookback}" for lookback in (20, 50, 100, 150, 200, 250)),
        *(f"cross_{short}_{long}" for short, long in (
            (5, 20),
            (10, 50),
            (20, 50),
            (20, 100),
            (20, 200),
            (50, 100),
            (50, 150),
            (50, 200),
            (100, 200),
            (100, 250),
        )),
        *(f"triple_{short}_{middle}_{long}" for short, middle, long in (
            (5, 20, 100),
            (10, 50, 200),
            (20, 50, 200),
            (20, 100, 200),
            (50, 100, 200),
            (50, 150, 200),
        )),
    }
    for asset in ("qqq", "tqqq"):
        for signal in signals:
            if signal.name not in vo_signal_names:
                continue
            for action in VO_ACTIONS:
                variants.append(
                    MaVariantSpec(
                        f"vo_{asset}_{signal.name}_{action}",
                        "vo_linked",
                        asset,
                        signal.name,
                        action,
                    )
                )
    return tuple(variants)


def build_ma_weights(
    data: MarketData,
) -> tuple[pd.DataFrame, dict[str, pd.Series], tuple[MaVariantSpec, ...]]:
    index = data.index
    tqqq = data.tqqq.loc[index]
    _, base = build_target_weights("vo", data)
    specs_by_name = {spec.name: spec for spec in signal_specs()}
    scores = {
        asset: {
            name: moving_average_score(data_frame.loc[index, "Close"], spec)
            for name, spec in specs_by_name.items()
        }
        for asset, data_frame in (("qqq", data.qqq), ("tqqq", data.tqqq))
    }

    variants = variant_specs()
    weights: dict[str, pd.Series] = {"vo": base}
    for variant in variants:
        score = scores[variant.signal_asset][variant.signal]
        if variant.family == "standalone":
            weights[variant.name] = score if variant.action == "full_cash" else 0.5 + 0.5 * score
        else:
            weights[variant.name] = apply_vo_trend(base, score, variant.action)
    return tqqq, weights, variants
