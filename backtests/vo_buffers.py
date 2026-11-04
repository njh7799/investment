from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .core import MarketData
from .models import build_target_weights


@dataclass(frozen=True)
class BufferVariant:
    name: str
    family: str
    parameters: str


def default_vo_weight(volatility: float) -> float:
    if pd.isna(volatility) or volatility <= 0.60:
        return 1.0
    if volatility <= 0.90:
        return 0.5
    return 0.0


def recovery_hysteresis_weights(volatility: pd.Series, gap: float) -> pd.Series:
    state = 1.0
    values: list[float] = []
    for raw in volatility:
        desired = default_vo_weight(raw)
        if desired < state:
            state = desired
        elif desired > state:
            recovery = (
                1.0 if raw <= 0.60 - gap else 0.5 if raw <= 0.90 - gap else 0.0
            )
            if recovery > state:
                state = recovery
        values.append(state)
    return pd.Series(values, index=volatility.index, dtype=float)


def recovery_confirmation_weights(base: pd.Series, sessions: int) -> pd.Series:
    if sessions < 1:
        raise ValueError("sessions must be positive")
    state = 1.0
    pending: float | None = None
    count = 0
    values: list[float] = []
    for raw in base:
        desired = float(raw)
        if desired < state:
            state, pending, count = desired, None, 0
        elif desired > state:
            if pending == desired:
                count += 1
            else:
                pending, count = desired, 1
            if count >= sessions:
                state, pending, count = desired, None, 0
        else:
            pending, count = None, 0
        values.append(state)
    return pd.Series(values, index=base.index, dtype=float)


def minimum_holding_weights(base: pd.Series, sessions: int) -> pd.Series:
    if sessions < 1:
        raise ValueError("sessions must be positive")
    state = 1.0
    cut_at: int | None = None
    values: list[float] = []
    for location, raw in enumerate(base):
        desired = float(raw)
        if desired < state:
            state, cut_at = desired, location
        elif desired > state and (cut_at is None or location - cut_at >= sessions):
            state = desired
        values.append(state)
    return pd.Series(values, index=base.index, dtype=float)


def smoothed_recovery_weights(
    base: pd.Series, volatility: pd.Series, sessions: int
) -> pd.Series:
    if sessions < 1:
        raise ValueError("sessions must be positive")
    smoothed = volatility.rolling(sessions).mean()
    state = 1.0
    values: list[float] = []
    for desired_raw, average in zip(base, smoothed):
        desired = float(desired_raw)
        if pd.isna(average) or desired < state:
            state = desired
        elif desired > state:
            candidate = min(desired, default_vo_weight(float(average)))
            if candidate > state:
                state = candidate
        values.append(state)
    return pd.Series(values, index=base.index, dtype=float)


def variant_specs() -> tuple[BufferVariant, ...]:
    specs = [
        *(BufferVariant(f"hyst_{gap * 100:.1f}pp", "recovery_hysteresis", f"gap={gap}") for gap in (0.025, 0.05, 0.10)),
        *(BufferVariant(f"confirm_{sessions}d", "recovery_confirmation", f"sessions={sessions}") for sessions in (2, 3, 5)),
        *(BufferVariant(f"hold_{sessions}d", "minimum_reduced_holding", f"sessions={sessions}") for sessions in (2, 5, 10)),
        *(BufferVariant(f"smooth_{sessions}d", "smoothed_recovery", f"sessions={sessions}") for sessions in (3, 5, 10)),
        BufferVariant("hybrid_h2.5_c2_m0", "combined_buffer", "gap=0.025;confirmation=2;holding=0"),
        BufferVariant("hybrid_h5.0_c2_m0", "combined_buffer", "gap=0.05;confirmation=2;holding=0"),
        BufferVariant("hybrid_h5.0_c1_m5", "combined_buffer", "gap=0.05;confirmation=1;holding=5"),
    ]
    return tuple(specs)


def _parameters(text: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in text.split(";"))


def build_vo_buffer_weights(
    data: MarketData,
) -> tuple[pd.DataFrame, dict[str, pd.Series], tuple[BufferVariant, ...]]:
    prices, full_base = build_target_weights("vo", data)
    index = full_base.index
    base = full_base.loc[index]
    volatility = prices.loc[index, "Close"].pct_change().rolling(30).std(ddof=1) * np.sqrt(252)
    weights: dict[str, pd.Series] = {"vo": base}
    specs = variant_specs()
    for spec in specs:
        parameters = _parameters(spec.parameters)
        if spec.family == "recovery_hysteresis":
            weights[spec.name] = recovery_hysteresis_weights(volatility, float(parameters["gap"]))
        elif spec.family == "recovery_confirmation":
            weights[spec.name] = recovery_confirmation_weights(base, int(parameters["sessions"]))
        elif spec.family == "minimum_reduced_holding":
            weights[spec.name] = minimum_holding_weights(base, int(parameters["sessions"]))
        elif spec.family == "smoothed_recovery":
            weights[spec.name] = smoothed_recovery_weights(base, volatility, int(parameters["sessions"]))
        else:
            target = recovery_hysteresis_weights(volatility, float(parameters["gap"]))
            confirmation = int(parameters["confirmation"])
            holding = int(parameters["holding"])
            weights[spec.name] = (
                recovery_confirmation_weights(target, confirmation)
                if confirmation > 1
                else minimum_holding_weights(target, holding)
            )
    return prices, weights, specs
