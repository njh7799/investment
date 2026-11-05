from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .core import MarketData
from .models import build_target_weights


@dataclass(frozen=True)
class ReboundVariant:
    name: str
    family: str
    parameters: str


def variant_specs() -> tuple[ReboundVariant, ...]:
    specs: list[ReboundVariant] = []
    for threshold in (0.10, 0.15, 0.20):
        code = int(round(threshold * 100))
        specs.append(ReboundVariant(f"online_low_rebound_{code}", "online_low_rebound_fill_stop", f"rebound={threshold}"))
    for threshold in (0.10, 0.15, 0.20):
        code = int(round(threshold * 100))
        specs.append(ReboundVariant(f"surge_5d_{code}", "five_day_surge_fill_stop", f"horizon=5;return={threshold}"))
    specs.append(ReboundVariant("sma_upcross_5_20", "sma_upcross_fill_stop", "short=5;long=20"))
    for horizon, threshold in ((5, 0.15), (10, 0.20)):
        specs.append(ReboundVariant(f"strict_high_{horizon}d_{int(threshold * 100)}", "return_with_strict_recent_high_fill_stop", f"horizon={horizon};return={threshold}"))
    for horizon, threshold in ((5, 0.15), (10, 0.20)):
        specs.append(ReboundVariant(f"near_high_{horizon}d_{int(threshold * 100)}", "return_with_near_recent_high_fill_stop", f"horizon={horizon};return={threshold};proximity=0.98"))
    return tuple(specs)


def _parse_parameters(text: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in text.split(";"))


def fill_stopped_addon_weights(
    base: pd.Series,
    prices: pd.DataFrame,
    signal: pd.Series,
    *,
    rearm_level: pd.Series | None = None,
) -> tuple[pd.Series, pd.Series]:
    """Causal +50pp addon whose stop anchor is its next-open activation price.

    An activation that produces no target increase is treated as no net purchase and is blocked
    until the raw condition rearms. Entry-price values are retained for audit while active.
    """
    index = base.index.intersection(prices.index)
    base = base.loc[index].astype(float)
    prices = prices.loc[index]
    signal = signal.reindex(index).fillna(False).astype(bool)
    level = signal if rearm_level is None else rearm_level.reindex(index).fillna(False).astype(bool)

    active = False
    pending_entry = False
    blocked = False
    entry_price: float | None = None
    previous_target: float | None = None
    targets: list[float] = []
    anchors: list[float] = []

    for position, (date, base_weight) in enumerate(base.items()):
        base_weight = float(base_weight)
        if pending_entry:
            active = True
            entry_price = float(prices.at[date, "Open"])
            pending_entry = False

        if base_weight >= 1.0:
            active = False
            pending_entry = False
            blocked = False
            entry_price = None
            target = base_weight
        else:
            if active and entry_price is not None and float(prices.at[date, "Close"]) < entry_price:
                active = False
                blocked = True
                entry_price = None
            elif not active and blocked and not bool(level.at[date]):
                blocked = False
            elif not active and not blocked and bool(signal.at[date]):
                intended = min(1.0, base_weight + 0.5)
                prior = base_weight if previous_target is None else previous_target
                if intended > prior + 1e-12:
                    pending_entry = True
                else:
                    blocked = True
            target = min(1.0, base_weight + 0.5) if active or pending_entry else base_weight

        targets.append(target)
        anchors.append(np.nan if entry_price is None else entry_price)
        previous_target = target

    return (
        pd.Series(targets, index=index, dtype=float),
        pd.Series(anchors, index=index, dtype=float, name="EntryPrice"),
    )


def online_low_fill_stopped_weights(
    base: pd.Series,
    prices: pd.DataFrame,
    rebound: float,
) -> tuple[pd.Series, pd.Series]:
    """Online-low entry with actual next-open anchor and a fresh low search after a stop."""
    index = base.index.intersection(prices.index)
    base = base.loc[index].astype(float)
    prices = prices.loc[index]
    active = False
    pending_entry = False
    entry_price: float | None = None
    running_low: float | None = None
    previous_target: float | None = None
    targets: list[float] = []
    anchors: list[float] = []

    for date, base_weight in base.items():
        base_weight = float(base_weight)
        close = float(prices.at[date, "Close"])
        if pending_entry:
            active = True
            entry_price = float(prices.at[date, "Open"])
            pending_entry = False

        if base_weight >= 1.0:
            active = False
            pending_entry = False
            entry_price = None
            running_low = None
            target = base_weight
        else:
            if active and entry_price is not None and close < entry_price:
                active = False
                entry_price = None
                running_low = close
            elif not active and not pending_entry:
                running_low = close if running_low is None else min(running_low, close)
                boundary = running_low * (1.0 + rebound)
                if close > boundary or np.isclose(close, boundary):
                    intended = min(1.0, base_weight + 0.5)
                    prior = base_weight if previous_target is None else previous_target
                    if intended > prior + 1e-12:
                        pending_entry = True
                    else:
                        running_low = close
            target = min(1.0, base_weight + 0.5) if active or pending_entry else base_weight

        targets.append(target)
        anchors.append(np.nan if entry_price is None else entry_price)
        previous_target = target

    return pd.Series(targets, index=index, dtype=float), pd.Series(anchors, index=index, dtype=float, name="EntryPrice")


def build_vo_rebound_weights(data: MarketData) -> tuple[pd.DataFrame, dict[str, pd.Series], tuple[ReboundVariant, ...]]:
    index = data.index
    tqqq = data.tqqq.loc[index]
    close = tqqq["Close"]
    _, full_base = build_target_weights("vo", data)
    base = full_base.loc[index]
    specs = variant_specs()
    weights: dict[str, pd.Series] = {"vo": base}
    returns = {h: close.pct_change(h, fill_method=None) for h in (5, 10)}
    prior_highs = {h: close.shift(1).rolling(h).max() for h in (5, 10)}
    inclusive_highs = {h: close.rolling(h + 1).max() for h in (5, 10)}

    for spec in specs:
        params = _parse_parameters(spec.parameters)
        if spec.family == "online_low_rebound_fill_stop":
            weights[spec.name], _ = online_low_fill_stopped_weights(base, tqqq, float(params["rebound"]))
            continue
        if spec.family == "sma_upcross_fill_stop":
            fast = close.rolling(int(params["short"])).mean()
            slow = close.rolling(int(params["long"])).mean()
            bull = fast > slow
            signal = bull & ~bull.shift(1, fill_value=False)
            weights[spec.name], _ = fill_stopped_addon_weights(base, tqqq, signal, rearm_level=bull)
            continue
        horizon = int(params["horizon"])
        threshold = float(params["return"])
        condition = returns[horizon] >= threshold
        if spec.family == "return_with_strict_recent_high_fill_stop":
            condition &= close > prior_highs[horizon]
        elif spec.family == "return_with_near_recent_high_fill_stop":
            condition &= close >= float(params["proximity"]) * inclusive_highs[horizon]
        weights[spec.name], _ = fill_stopped_addon_weights(base, tqqq, condition)
    return tqqq, weights, specs
