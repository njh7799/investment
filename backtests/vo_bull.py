from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .core import MarketData
from .models import build_target_weights
from .vo_upside import apply_upside_override


@dataclass(frozen=True)
class BullVariant:
    name: str
    family: str
    action: str
    parameters: str


def _realized_volatility(close: pd.Series, window: int) -> pd.Series:
    return close.pct_change().rolling(window).std(ddof=1) * np.sqrt(252)


def risk_adjusted_trend(close: pd.Series, horizon: int) -> pd.Series:
    period_volatility = _realized_volatility(close, horizon) * np.sqrt(horizon / 252)
    return close.pct_change(horizon) / period_volatility.replace(0.0, np.nan)


def volatility_cooling(close: pd.Series, short: int, long: int) -> pd.Series:
    return _realized_volatility(close, short) / _realized_volatility(close, long).replace(0.0, np.nan)


def bullish_breadth(
    closes: pd.DataFrame,
    *,
    kind: str,
    horizon: int,
    minimum: int,
) -> pd.Series:
    if kind == "return":
        bullish = closes.pct_change(horizon, fill_method=None) > 0.0
    elif kind == "price_sma":
        average = closes.rolling(horizon).mean()
        bullish = (closes >= average).where(average.notna(), False)
    else:
        raise ValueError(f"unknown breadth kind: {kind}")
    valid = closes.rolling(horizon + 1 if kind == "return" else horizon).count().min(axis=1)
    return (bullish.sum(axis=1) >= minimum).where(valid >= (horizon + 1 if kind == "return" else horizon), False)


def multi_horizon_consensus(close: pd.Series, horizons: tuple[int, ...], minimum: int) -> pd.Series:
    signals = pd.concat({horizon: close.pct_change(horizon) > 0.0 for horizon in horizons}, axis=1)
    valid = close.shift(max(horizons)).notna()
    return (signals.sum(axis=1) >= minimum).where(valid, False)


def confirmed_recovery_weights(
    base: pd.Series,
    tqqq_close: pd.Series,
    confirmation: pd.Series,
    recovery: float,
) -> pd.Series:
    base = base.astype(float)
    tqqq_close = tqqq_close.reindex(base.index)
    confirmation = confirmation.reindex(base.index).fillna(False).astype(bool)
    previous_base = float(base.iloc[0])
    cut_price: float | None = None
    pre_cut_weight: float | None = None
    cut_weight: float | None = None
    restored = False
    values: list[float] = []

    for base_weight, price, confirmed in zip(base, tqqq_close, confirmation):
        base_weight = float(base_weight)
        price = float(price)
        if base_weight < previous_base:
            cut_price = price
            pre_cut_weight = previous_base
            cut_weight = base_weight
            restored = False
        elif pre_cut_weight is not None and base_weight >= pre_cut_weight:
            cut_price = pre_cut_weight = cut_weight = None
            restored = False
        elif cut_weight is not None and base_weight < cut_weight:
            cut_price = price
            pre_cut_weight = previous_base
            cut_weight = base_weight
            restored = False

        if cut_price is not None and pre_cut_weight is not None:
            if restored and price <= cut_price:
                restored = False
            elif not restored and confirmed and (
                price > cut_price * (1.0 + recovery)
                or np.isclose(price, cut_price * (1.0 + recovery))
            ):
                restored = True
        values.append(float(pre_cut_weight) if restored and pre_cut_weight is not None else base_weight)
        previous_base = base_weight
    return pd.Series(values, index=base.index, dtype=float)


def variant_specs() -> tuple[BullVariant, ...]:
    specs: list[BullVariant] = []
    for horizon in (20, 60, 120):
        for threshold in (0.5, 1.0, 1.5):
            for action in ("step_up", "block_cut"):
                specs.append(BullVariant(
                    f"riskadj_h{horizon}_t{int(threshold * 10)}_{action}",
                    "risk_adjusted_trend", action, f"horizon={horizon};threshold={threshold}",
                ))
    for short in (5, 10):
        for long in (30, 60):
            for ratio in (0.65, 0.80, 0.95):
                for action in ("step_up", "block_cut"):
                    specs.append(BullVariant(
                        f"cool_s{short}_l{long}_r{int(ratio * 100)}_{action}",
                        "volatility_cooling", action, f"short={short};long={long};ratio={ratio}",
                    ))
    for kind in ("return", "price_sma"):
        for horizon in (20, 60):
            for minimum in (2, 3):
                for action in ("step_up", "block_cut"):
                    specs.append(BullVariant(
                        f"breadth_{kind}_h{horizon}_n{minimum}_{action}",
                        "cross_market_breadth", action, f"kind={kind};horizon={horizon};minimum={minimum}",
                    ))
    for horizons in ((10, 20, 60), (20, 60, 120)):
        code = "_".join(map(str, horizons))
        for minimum in (2, 3):
            for action in ("step_up", "block_cut"):
                specs.append(BullVariant(
                    f"consensus_{code}_n{minimum}_{action}",
                    "multi_horizon_consensus", action, f"horizons={code};minimum={minimum}",
                ))
    for recovery in (0.10, 0.15):
        specs.append(BullVariant(
            f"recovery_{int(recovery * 100)}_breadth2_cool95",
            "confirmed_recovery", "restore_pre_cut", f"recovery={recovery};breadth=2;cooling=0.95",
        ))
    return tuple(specs)


def _parse_parameters(text: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in text.split(";"))


def build_vo_bull_weights(
    data: MarketData,
    breadth_closes: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, pd.Series], tuple[BullVariant, ...]]:
    index = data.index
    tqqq = data.tqqq.loc[index]
    qqq_close = data.qqq.loc[index, "Close"]
    breadth_closes = breadth_closes.reindex(index)[["QQQ", "SPY", "IWM"]]
    _, full_base = build_target_weights("vo", data)
    base = full_base.loc[index]
    weights: dict[str, pd.Series] = {"vo": base}
    specs = variant_specs()

    risk_features = {h: risk_adjusted_trend(qqq_close, h) for h in (20, 60, 120)}
    cooling_features = {
        (short, long): volatility_cooling(qqq_close, short, long)
        for short in (5, 10) for long in (30, 60)
    }
    breadth_features = {
        (kind, horizon, minimum): bullish_breadth(
            breadth_closes, kind=kind, horizon=horizon, minimum=minimum
        )
        for kind in ("return", "price_sma")
        for horizon in (20, 60)
        for minimum in (2, 3)
    }
    consensus_features = {
        (horizons, minimum): multi_horizon_consensus(qqq_close, horizons, minimum)
        for horizons in ((10, 20, 60), (20, 60, 120))
        for minimum in (2, 3)
    }
    recovery_confirmation = breadth_features[("return", 20, 2)] & (cooling_features[(10, 30)] <= 0.95)

    for spec in specs:
        params = _parse_parameters(spec.parameters)
        if spec.family == "risk_adjusted_trend":
            condition = risk_features[int(params["horizon"])] >= float(params["threshold"])
        elif spec.family == "volatility_cooling":
            short = int(params["short"])
            condition = (
                cooling_features[(short, int(params["long"]))] <= float(params["ratio"])
            ) & (qqq_close.pct_change(short) > 0.0)
        elif spec.family == "cross_market_breadth":
            condition = breadth_features[(params["kind"], int(params["horizon"]), int(params["minimum"]))]
        elif spec.family == "multi_horizon_consensus":
            horizons = tuple(int(value) for value in params["horizons"].split("_"))
            condition = consensus_features[(horizons, int(params["minimum"]))]
        else:
            weights[spec.name] = confirmed_recovery_weights(
                base, tqqq["Close"], recovery_confirmation, float(params["recovery"])
            )
            continue
        weights[spec.name] = apply_upside_override(base, condition, spec.action)
    return tqqq, weights, specs
