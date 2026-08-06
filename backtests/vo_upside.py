from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .core import MarketData
from .models import build_target_weights


LOOKBACK = 30
ACTIONS = ("floor50", "floor100", "step_up", "block_cut")


@dataclass(frozen=True)
class UpsideVariant:
    name: str
    signal_asset: str
    condition: str
    threshold: float
    action: str
    return_threshold: float | None = None
    regime_filter: str | None = None


def directional_features(close: pd.Series) -> pd.DataFrame:
    returns = close.pct_change()
    positive = returns.clip(lower=0.0)
    negative = -returns.clip(upper=0.0)
    positive_squares = positive.pow(2).rolling(LOOKBACK).sum()
    negative_squares = negative.pow(2).rolling(LOOKBACK).sum()
    total_squares = positive_squares + negative_squares
    negative_magnitude = negative.rolling(LOOKBACK).sum()
    magnitude_ratio = positive.rolling(LOOKBACK).sum() / negative_magnitude.replace(0.0, np.nan)
    magnitude_ratio = magnitude_ratio.where(negative_magnitude.ne(0.0), np.inf)
    return pd.DataFrame(
        {
            "total_return": close.pct_change(LOOKBACK),
            "up_variance_share": positive_squares / total_squares.replace(0.0, np.nan),
            "up_down_magnitude_ratio": magnitude_ratio,
        },
        index=close.index,
    )


def apply_upside_override(base: pd.Series, condition: pd.Series, action: str) -> pd.Series:
    condition = condition.reindex(base.index).fillna(False).astype(bool)
    if action == "floor50":
        return base.where(~condition, base.clip(lower=0.5))
    if action == "floor100":
        return base.where(~condition, 1.0)
    if action == "step_up":
        return base.where(~condition, (base + 0.5).clip(upper=1.0))
    if action != "block_cut":
        raise ValueError(f"unknown upside override action: {action}")

    state = float(base.iloc[0])
    values: list[float] = []
    for base_weight, block in zip(base.astype(float), condition):
        if not block or base_weight >= state:
            state = float(base_weight)
        values.append(state)
    return pd.Series(values, index=base.index, dtype=float)


def variant_specs() -> tuple[UpsideVariant, ...]:
    variants: list[UpsideVariant] = []
    return_thresholds = {
        "tqqq": (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40),
        "qqq": (0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15),
    }
    combo_return_thresholds = {
        "tqqq": (0.10, 0.15, 0.20, 0.30),
        "qqq": (0.03, 0.05, 0.075, 0.10),
    }
    for asset in ("tqqq", "qqq"):
        for threshold in return_thresholds[asset]:
            for action in ACTIONS:
                code = int(round(threshold * 1000))
                variants.append(
                    UpsideVariant(f"ret_{asset}_{code}_{action}", asset, "total_return", threshold, action)
                )
        for threshold in (0.55, 0.60, 0.65, 0.70, 0.75, 0.80):
            for action in ACTIONS:
                code = int(round(threshold * 100))
                variants.append(
                    UpsideVariant(
                        f"varshare_{asset}_{code}_{action}", asset, "up_variance_share", threshold, action
                    )
                )
        for threshold in (1.25, 1.50, 2.00, 3.00, 4.00):
            for action in ACTIONS:
                code = int(round(threshold * 100))
                variants.append(
                    UpsideVariant(
                        f"magratio_{asset}_{code}_{action}",
                        asset,
                        "up_down_magnitude_ratio",
                        threshold,
                        action,
                    )
                )
        for return_threshold in combo_return_thresholds[asset]:
            for threshold in (0.55, 0.65, 0.75):
                for action in ACTIONS:
                    return_code = int(round(return_threshold * 1000))
                    share_code = int(round(threshold * 100))
                    variants.append(
                        UpsideVariant(
                            f"combo_{asset}_{return_code}_{share_code}_{action}",
                            asset,
                            "return_and_variance_share",
                            threshold,
                            action,
                            return_threshold=return_threshold,
                        )
                    )
    filtered_conditions = [
        *(
            UpsideVariant("", "qqq", "total_return", threshold, "block_cut")
            for threshold in (0.04, 0.06, 0.08, 0.10, 0.12, 0.15)
        ),
        *(
            UpsideVariant("", "tqqq", "total_return", threshold, "block_cut")
            for threshold in (0.10, 0.15, 0.20, 0.25, 0.30)
        ),
        *(
            UpsideVariant("", asset, "up_variance_share", threshold, "block_cut")
            for asset in ("qqq", "tqqq")
            for threshold in (0.60, 0.65, 0.70)
        ),
        *(
            UpsideVariant("", asset, "up_down_magnitude_ratio", threshold, "block_cut")
            for asset in ("qqq", "tqqq")
            for threshold in (2.0, 3.0)
        ),
    ]
    regime_filters = ("sma100", "sma150", "sma200", "return60", "return120", "return200")
    for seed in filtered_conditions:
        threshold_code = int(round(seed.threshold * (1000 if seed.condition == "total_return" else 100)))
        condition_code = {
            "total_return": "ret",
            "up_variance_share": "varshare",
            "up_down_magnitude_ratio": "magratio",
        }[seed.condition]
        for regime_filter in regime_filters:
            variants.append(
                UpsideVariant(
                    f"filtered_{condition_code}_{seed.signal_asset}_{threshold_code}_{regime_filter}_block_cut",
                    seed.signal_asset,
                    seed.condition,
                    seed.threshold,
                    "block_cut",
                    regime_filter=regime_filter,
                )
            )
    return tuple(variants)


def build_vo_upside_weights(data: MarketData) -> tuple[pd.DataFrame, dict[str, pd.Series], tuple[UpsideVariant, ...]]:
    index = data.index
    tqqq = data.tqqq.loc[index]
    _, base = build_target_weights("vo", data)
    features = {
        "tqqq": directional_features(tqqq["Close"]),
        "qqq": directional_features(data.qqq.loc[index, "Close"]),
    }
    qqq_close = data.qqq.loc[index, "Close"]
    regime_filters = {
        "sma100": qqq_close >= qqq_close.rolling(100).mean(),
        "sma150": qqq_close >= qqq_close.rolling(150).mean(),
        "sma200": qqq_close >= qqq_close.rolling(200).mean(),
        "return60": qqq_close.pct_change(60) >= 0.0,
        "return120": qqq_close.pct_change(120) >= 0.0,
        "return200": qqq_close.pct_change(200) >= 0.0,
    }
    weights = {"vo": base}
    specs = variant_specs()
    for spec in specs:
        feature = features[spec.signal_asset]
        if spec.condition == "return_and_variance_share":
            condition = (feature["total_return"] >= float(spec.return_threshold)) & (
                feature["up_variance_share"] >= spec.threshold
            )
        else:
            condition = feature[spec.condition] >= spec.threshold
        if spec.regime_filter is not None:
            condition &= regime_filters[spec.regime_filter].fillna(False)
        weights[spec.name] = apply_upside_override(base, condition, spec.action)
    return tqqq, weights, specs
