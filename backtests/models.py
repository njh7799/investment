from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .core import MarketData


@dataclass(frozen=True)
class ModelSpec:
    name: str
    family: str
    source: str
    signal_asset: str
    parameters: str
    adaptation: str = ""


MODEL_SPECS: dict[str, ModelSpec] = {
    "tqqq_hold": ModelSpec("TQQQ buy and hold", "benchmark", "Repository benchmark", "TQQQ", "100%"),
    "qqq_hold": ModelSpec("QQQ buy and hold", "benchmark", "Repository benchmark", "QQQ", "100%"),
    "vo": ModelSpec("VO 30-day", "volatility", "docs/strategies/volatility-allocation", "TQQQ", "30d; 60%/90%; 100/50/0"),
    "three_percent": ModelSpec("IXIC 3% rule", "regime", "docs/strategies/ixic-three-percent-rule", "IXIC/QQQ/TQQQ", "documented default"),
    "vr5": ModelSpec("VR 5.0 lump-sum", "value_rebalancing", "docs/strategies/value-rebalancing", "TQQQ", "10 sessions; G=10; band=15%"),
    "faber_10m": ModelSpec("Faber 10-month SMA", "trend", "https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf", "QQQ", "month-end close > 10-month SMA"),
    "sma_200": ModelSpec("200-day SMA", "trend", "Faber (2007), daily approximation", "QQQ", "close > 200-day SMA", "10-month rule expressed daily"),
    "golden_cross": ModelSpec("Golden Cross", "trend", "Brock, Lakonishok & LeBaron (1992)", "QQQ", "50-day SMA > 200-day SMA"),
    "absolute_momentum_12m": ModelSpec("12-month absolute momentum", "momentum", "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2244633", "QQQ", "month-end 12-month return > 0", "cash return fixed at 0"),
    "tsmom_12m": ModelSpec("12-month time-series momentum", "momentum", "https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf", "QQQ", "sign of trailing 12-month return; monthly", "long/cash, without shorting or volatility scaling"),
    "turtle_55_20": ModelSpec("Turtle System 2 breakout", "breakout", "https://www.turtletrader.com/rules/", "QQQ", "55-day high entry; 20-day low exit", "long/cash and full allocation"),
    "halloween": ModelSpec("Halloween indicator", "seasonality", "https://www.aeaweb.org/articles?id=10.1257/000282802762024683", "calendar", "invest November-April"),
    "turn_of_month": ModelSpec("Turn of the month", "seasonality", "Lakonishok & Smidt (1988)", "calendar", "last session and first three sessions"),
    "macd": ModelSpec("MACD 12-26-9", "trend", "Gerald Appel canonical MACD", "QQQ", "EMA12-EMA26 > EMA9 signal"),
    "rsi2": ModelSpec("Connors RSI(2)", "mean_reversion", "Connors & Alvarez, Short Term Trading Strategies That Work", "QQQ", "RSI(2)<10 entry; close>5-day SMA exit", "long/cash and next-open execution"),
}


def _month_end_signal(close: pd.Series, state: pd.Series) -> pd.Series:
    month_end = close.groupby(close.index.to_period("M")).tail(1).index
    sparse = state.reindex(month_end)
    return sparse.reindex(close.index).ffill().fillna(0.0).astype(float)


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0).rolling(period).mean()
    losses = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gains / losses.replace(0.0, np.nan)
    result = 100.0 - 100.0 / (1.0 + rs)
    return result.where(losses.ne(0.0), 100.0)


def _stateful_entry_exit(entry: pd.Series, exit_: pd.Series) -> pd.Series:
    state = 0.0
    values: list[float] = []
    for enter, leave in zip(entry.fillna(False), exit_.fillna(False)):
        if state == 0.0 and enter:
            state = 1.0
        elif state == 1.0 and leave:
            state = 0.0
        values.append(state)
    return pd.Series(values, index=entry.index)


def build_target_weights(model: str, data: MarketData) -> tuple[pd.DataFrame, pd.Series]:
    index = data.index
    qqq = data.qqq.loc[index]
    tqqq = data.tqqq.loc[index]
    if model == "qqq_hold":
        return qqq, pd.Series(1.0, index=index)
    if model == "tqqq_hold":
        return tqqq, pd.Series(1.0, index=index)
    if model == "vo":
        vol = tqqq["Close"].pct_change().rolling(30).std(ddof=1) * np.sqrt(252)
        weights = pd.Series(np.select([vol <= 0.60, vol <= 0.90], [1.0, 0.5], default=0.0), index=index)
        return tqqq, weights.where(vol.notna(), 1.0)

    close = qqq["Close"]
    if model == "faber_10m":
        month_close = close.groupby(close.index.to_period("M")).last()
        state = month_close > month_close.rolling(10).mean()
        month_dates = close.groupby(close.index.to_period("M")).tail(1).index
        weights = pd.Series(state.to_numpy(dtype=float), index=month_dates).reindex(index).ffill().fillna(0.0)
    elif model == "sma_200":
        weights = (close > close.rolling(200).mean()).astype(float)
    elif model == "golden_cross":
        weights = (close.rolling(50).mean() > close.rolling(200).mean()).astype(float)
    elif model in {"absolute_momentum_12m", "tsmom_12m"}:
        month_close = close.groupby(close.index.to_period("M")).last()
        state = month_close.pct_change(12) > 0.0
        month_dates = close.groupby(close.index.to_period("M")).tail(1).index
        weights = pd.Series(state.to_numpy(dtype=float), index=month_dates).reindex(index).ffill().fillna(0.0)
    elif model == "turtle_55_20":
        entry = close > close.shift(1).rolling(55).max()
        exit_ = close < close.shift(1).rolling(20).min()
        weights = _stateful_entry_exit(entry, exit_)
    elif model == "halloween":
        desired = pd.Series(close.index.month.isin([11, 12, 1, 2, 3, 4]).astype(float), index=index)
        weights = desired.shift(-1).fillna(desired.iloc[-1])
    elif model == "turn_of_month":
        periods = close.index.to_period("M")
        sequence = pd.Series(np.arange(len(index)), index=index)
        first_three = sequence.groupby(periods).rank(method="first") <= 3
        last = sequence.groupby(periods).rank(method="first", ascending=False) == 1
        desired = (first_three | last).astype(float)
        weights = desired.shift(-1).fillna(desired.iloc[-1])
    elif model == "macd":
        macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        weights = (macd > macd.ewm(span=9, adjust=False).mean()).astype(float)
    elif model == "rsi2":
        weights = _stateful_entry_exit(_rsi(close, 2) < 10.0, close > close.rolling(5).mean())
    else:
        raise KeyError(f"unknown model: {model}")
    return tqqq, weights.astype(float)
