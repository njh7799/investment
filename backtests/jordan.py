from __future__ import annotations

from collections import deque

import pandas as pd

from .core import BacktestResult, MarketData, run_weight_strategy
from .portfolio import common_index, run_portfolio_strategy


def jordan_open_regimes(ixic_close: pd.Series, index: pd.DatetimeIndex | None = None) -> pd.Series:
    """Return the Jordan regime in force at each open, using only prior closes."""
    selected = ixic_close.index if index is None else ixic_close.index.intersection(index)
    close = ixic_close.loc[selected].astype(float)
    regime = "normal"
    expiry: pd.Timestamp | None = None
    up_streak = 0
    crash_dates: deque[pd.Timestamp] = deque()
    values: list[str] = []

    for location, date in enumerate(selected):
        if regime != "normal" and expiry is not None and date >= expiry:
            regime, expiry, up_streak = "normal", None, 0
        values.append(regime)

        if location == 0:
            continue
        daily_return = close.iloc[location] / close.iloc[location - 1] - 1.0
        crash = daily_return <= -0.03
        if crash:
            crash_dates.append(date)
            cutoff = date - pd.DateOffset(months=1)
            while crash_dates and crash_dates[0] < cutoff:
                crash_dates.popleft()
            regime = "great_panic" if len(crash_dates) >= 4 or regime == "great_panic" else "panic"
            expiry = date + pd.DateOffset(months=2 if regime == "great_panic" else 1) + pd.DateOffset(days=1)
            up_streak = 0
        elif regime != "normal":
            up_streak = up_streak + 1 if close.iloc[location] > close.iloc[location - 1] else 0
            if up_streak >= 8:
                regime, expiry, up_streak = "normal", None, 0

    return pd.Series(values, index=selected, name="Regime")


def _signals_for_next_open(open_targets: pd.Series) -> pd.Series:
    signals = open_targets.shift(-1)
    signals.iloc[-1] = open_targets.iloc[-1]
    return signals


def run_jordan_tqqq(
    data: MarketData,
    *,
    panic_weight: float = 1.0 / 3.0,
    great_panic_weight: float = 0.0,
    start=None,
    end=None,
    initial_cash: float = 100_000.0,
    fee_rate: float = 0.001,
) -> BacktestResult:
    regimes = jordan_open_regimes(data.ixic["Close"], data.index)
    open_targets = regimes.map({"normal": 1.0, "panic": panic_weight, "great_panic": great_panic_weight})
    return run_weight_strategy(
        data.tqqq.loc[data.index],
        _signals_for_next_open(open_targets),
        start=start,
        end=end,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
    )


def run_jordan_public_proxy(
    data: MarketData,
    tlt: pd.DataFrame,
    *,
    start=None,
    end=None,
    initial_cash: float = 100_000.0,
    fee_rate: float = 0.001,
) -> BacktestResult:
    assets = {"QQQ": data.qqq, "TLT": tlt}
    index = common_index(assets).intersection(data.ixic.index)
    regimes = jordan_open_regimes(data.ixic["Close"], index)
    open_weights = pd.DataFrame(
        {"QQQ": (regimes == "normal").astype(float), "TLT": (regimes != "normal").astype(float)},
        index=index,
    )
    signals = open_weights.shift(-1)
    signals.iloc[-1] = open_weights.iloc[-1]
    return run_portfolio_strategy(
        assets,
        signals,
        start=start,
        end=end,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
    )
