from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .core import MarketData
from .models import build_target_weights
from .vo_consecutive import consecutive_up


@dataclass(frozen=True)
class VRecoveryVariant:
    name: str
    policy: str
    signal: str
    parameter: float | int | None


SIGNALS = ("qqq_streak_2", "tqqq_surge_5d_15", "tqqq_sma_upcross_5_20")


def variant_specs() -> tuple[VRecoveryVariant, ...]:
    specs = [VRecoveryVariant(f"one_{s}", "one_attempt", s, None) for s in SIGNALS]
    for cooldown in (20, 60):
        specs.extend(VRecoveryVariant(f"cool{cooldown}_{s}", "cooldown", s, cooldown) for s in SIGNALS)
    for hold in (10, 20):
        specs.extend(VRecoveryVariant(f"hold{hold}_{s}", "timebox", s, hold) for s in SIGNALS)
    for trail in (0.10, 0.15):
        code = int(trail * 100)
        specs.extend(VRecoveryVariant(f"trail{code}_{s}", "ratchet", s, trail) for s in SIGNALS)
    specs.extend(VRecoveryVariant(f"staged_{s}", "staged", s, 0.05) for s in SIGNALS)
    return tuple(specs)


def controlled_addon_weights(
    base: pd.Series,
    prices: pd.DataFrame,
    signal: pd.Series,
    *,
    rearm_level: pd.Series,
    policy: str,
    parameter: float | int | None,
) -> pd.Series:
    index = base.index.intersection(prices.index)
    base = base.loc[index].astype(float)
    prices = prices.loc[index]
    signal = signal.reindex(index).fillna(False).astype(bool)
    level = rearm_level.reindex(index).fillna(False).astype(bool)
    active = pending = blocked = attempted = False
    entry_price: float | None = None
    peak: float | None = None
    active_sessions = cooldown_left = 0
    addon = 0.0
    previous_target: float | None = None
    targets: list[float] = []

    for date, raw_base in base.items():
        base_weight = float(raw_base)
        close = float(prices.at[date, "Close"])
        if cooldown_left > 0:
            cooldown_left -= 1
        if pending:
            active = attempted = True
            pending = False
            entry_price = float(prices.at[date, "Open"])
            peak = entry_price
            active_sessions = 0
            addon = 0.25 if policy == "staged" else 0.50

        if base_weight >= 1.0:
            active = pending = blocked = attempted = False
            entry_price = peak = None
            active_sessions = cooldown_left = 0
            addon = 0.0
        elif active:
            active_sessions += 1
            peak = max(float(peak), close)
            anchor = float(entry_price)
            if policy == "ratchet":
                anchor = max(anchor, float(peak) * (1.0 - float(parameter)))
            should_exit = close < anchor
            if policy == "timebox" and active_sessions >= int(parameter):
                should_exit = True
            if should_exit:
                active = False
                addon = 0.0
                entry_price = peak = None
                blocked = policy != "one_attempt"
                if policy == "cooldown":
                    cooldown_left = int(parameter)
            elif policy == "staged" and close >= float(entry_price) * (1.0 + float(parameter)):
                addon = 0.50
        elif blocked:
            if cooldown_left == 0 and not bool(level.at[date]):
                blocked = False
        elif not (policy == "one_attempt" and attempted) and bool(signal.at[date]):
            intended_addon = 0.25 if policy == "staged" else 0.50
            intended = min(1.0, base_weight + intended_addon)
            prior = base_weight if previous_target is None else previous_target
            if intended > prior + 1e-12:
                pending = True

        target = min(1.0, base_weight + (addon if active else (0.25 if pending and policy == "staged" else 0.50 if pending else 0.0)))
        targets.append(target)
        previous_target = target
    return pd.Series(targets, index=index, dtype=float)


def build_vo_v_recovery_weights(data: MarketData) -> tuple[pd.DataFrame, dict[str, pd.Series], tuple[VRecoveryVariant, ...]]:
    index = data.index
    prices = data.tqqq.loc[index]
    qqq = data.qqq.loc[index, "Close"]
    tqqq = prices["Close"]
    _, full_base = build_target_weights("vo", data)
    base = full_base.loc[index]
    fast = tqqq.rolling(5).mean()
    slow = tqqq.rolling(20).mean()
    bull = fast > slow
    levels = {
        "qqq_streak_2": consecutive_up(qqq, 2),
        "tqqq_surge_5d_15": tqqq.pct_change(5, fill_method=None) >= 0.15,
        "tqqq_sma_upcross_5_20": bull,
    }
    signals = {
        "qqq_streak_2": levels["qqq_streak_2"],
        "tqqq_surge_5d_15": levels["tqqq_surge_5d_15"],
        "tqqq_sma_upcross_5_20": bull & ~bull.shift(1, fill_value=False),
    }
    specs = variant_specs()
    weights: dict[str, pd.Series] = {"vo": base}
    for spec in specs:
        weights[spec.name] = controlled_addon_weights(
            base, prices, signals[spec.signal], rearm_level=levels[spec.signal],
            policy=spec.policy, parameter=spec.parameter,
        )
    return prices, weights, specs
