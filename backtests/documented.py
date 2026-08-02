from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .core import BacktestResult, MarketData, _affordable_shares


def _trade_to_weight(cash, shares, price, weight, fee_rate):
    equity = cash + shares * price
    desired = int(np.floor(equity * weight / price))
    delta = desired - shares
    if delta < 0:
        quantity = -delta
        gross = quantity * price
        fee = gross * fee_rate
        return cash + gross - fee, shares - quantity, "SELL", quantity, gross, fee
    if delta > 0:
        quantity = _affordable_shares(cash, price, delta, fee_rate)
        gross = quantity * price
        fee = gross * fee_rate
        return cash - gross - fee, shares + quantity, "BUY", quantity, gross, fee
    return cash, shares, "NONE", 0, 0.0, 0.0


def _true_range(frame: pd.DataFrame) -> pd.Series:
    previous = frame["Close"].shift()
    values = pd.concat(
        [frame["High"] - frame["Low"], (frame["High"] - previous).abs(), (frame["Low"] - previous).abs()],
        axis=1,
    )
    result = values.max(axis=1)
    result.iloc[0] = frame["High"].iloc[0] - frame["Low"].iloc[0]
    return result


def causal_reference_high(frame: pd.DataFrame) -> pd.Series:
    """Latest confirmed close-based ZigZag peak, available only on confirmation close."""
    close = frame["Close"]
    atr = _true_range(frame).rolling(14).mean()
    mode = "unknown"
    high_value = low_value = float(close.iloc[0])
    high_date = low_date = close.index[0]
    last_peak_date = None
    reference = float(close.iloc[0])
    values = []
    for date, price in close.items():
        if price >= high_value:
            high_value, high_date = float(price), date
        if price <= low_value:
            low_value, low_date = float(price), date
        ready = pd.notna(atr.loc[date])
        fall = high_value - price
        rise = price - low_value
        peak_confirm = ready and fall >= 4 * atr.loc[date] and fall / high_value >= 0.10
        trough_confirm = ready and rise >= 4 * atr.loc[date] and rise / low_value >= 0.10
        if mode in {"unknown", "up"} and peak_confirm:
            mode = "down"
            last_peak_date = high_date
            reference = high_value
            low_value, low_date = float(price), date
        elif mode in {"unknown", "down"} and trough_confirm:
            mode = "up"
            high_value, high_date = float(price), date
        if last_peak_date is None:
            reference = max(reference, float(price))
        elif date >= last_peak_date:
            reference = max(reference, float(price))
        values.append(reference)
    return pd.Series(values, index=close.index, name="ReferenceHigh")


def _band(price: float, reference: float) -> int:
    if reference <= 0:
        return 0
    return min(9, max(0, int(np.floor(max(0.0, 1.0 - price / reference) / 0.10 + 1e-12))))


def run_three_percent_rule(
    data: MarketData,
    *,
    start=None,
    end=None,
    initial_cash=100_000.0,
    fee_rate=0.001,
) -> BacktestResult:
    index = data.index
    tqqq = data.tqqq.loc[index]
    qqq = data.qqq.loc[index]
    ixic = data.ixic.loc[index]
    reference = causal_reference_high(tqqq)
    selected = index
    if start is not None:
        selected = selected[selected >= pd.Timestamp(start)]
    if end is not None:
        selected = selected[selected <= pd.Timestamp(end)]
    if selected.empty:
        raise ValueError("selected backtest period is empty")

    cash = float(initial_cash)
    shares = 0
    applied_band = 0
    panic_band = None
    regime = "normal"
    expiry = None
    up_streak = 0
    crash_dates: deque[pd.Timestamp] = deque()
    pending_target = 1.0
    trades = []
    positions = []
    equities = []

    for date in selected:
        price = float(tqqq.loc[date, "Open"])
        if regime != "normal" and expiry is not None and date >= expiry:
            previous = index.get_loc(date) - 1
            close_band = _band(float(tqqq["Close"].iloc[previous]), float(reference.iloc[previous]))
            regime, expiry, up_streak = "normal", None, 0
            applied_band = close_band
            pending_target = 1.0 - close_band / 10.0

        target = pending_target
        pending_target = None

        if target is not None:
            cash, shares, side, quantity, gross, fee = _trade_to_weight(cash, shares, price, target, fee_rate)
            if quantity:
                trades.append({"Date": date, "Side": side, "Quantity": quantity, "Price": price, "Gross": gross, "Fee": fee, "TargetWeight": target})

        close_price = float(tqqq.loc[date, "Close"])
        equities.append(cash + shares * close_price)
        positions.append({"Date": date, "Cash": cash, "Shares": shares, "TargetWeight": target})

        crash = False
        loc = index.get_loc(date)
        if loc > 0:
            crash = float(ixic["Close"].iloc[loc] / ixic["Close"].iloc[loc - 1] - 1.0) <= -0.03
        if crash:
            crash_dates.append(date)
            cutoff = date - pd.DateOffset(months=1)
            while crash_dates and crash_dates[0] < cutoff:
                crash_dates.popleft()
            new_regime = "great_panic" if len(crash_dates) >= 4 or regime == "great_panic" else "panic"
            regime = new_regime
            expiry = date + pd.DateOffset(months=2 if regime == "great_panic" else 1) + pd.DateOffset(days=1)
            up_streak = 0
            close_band = _band(close_price, float(reference.loc[date]))
            if regime == "great_panic":
                pending_target = 0.0
            else:
                panic_band = close_band
                pending_target = close_band / 10.0
        elif regime != "normal":
            if loc > 0 and qqq["Close"].iloc[loc] > qqq["Close"].iloc[loc - 1]:
                up_streak += 1
            else:
                up_streak = 0
            if up_streak >= 8:
                close_band = _band(close_price, float(reference.loc[date]))
                regime, expiry, up_streak = "normal", None, 0
                applied_band = close_band
                pending_target = 1.0 - close_band / 10.0
        else:
            close_band = _band(close_price, float(reference.loc[date]))
            if close_band != applied_band:
                applied_band = close_band
                pending_target = 1.0 - close_band / 10.0
        if regime == "panic" and panic_band is not None:
            close_band = _band(close_price, float(reference.loc[date]))
            if close_band > panic_band:
                panic_band = close_band
                pending_target = close_band / 10.0

    equity = pd.Series(equities, index=selected, name="Equity")
    trade_frame = pd.DataFrame(trades)
    if not trade_frame.empty:
        trade_frame = trade_frame.set_index("Date")
    return BacktestResult(equity, trade_frame, pd.DataFrame(positions).set_index("Date"), float(initial_cash))


def run_vr_5(
    prices: pd.DataFrame,
    *,
    start=None,
    end=None,
    initial_cash=100_000.0,
    fee_rate=0.001,
) -> BacktestResult:
    selected = prices
    if start is not None:
        selected = selected.loc[pd.Timestamp(start):]
    if end is not None:
        selected = selected.loc[:pd.Timestamp(end)]
    if selected.empty:
        raise ValueError("selected backtest period is empty")
    cash = float(initial_cash)
    shares = 0
    v = None
    buy_budget = 0.0
    pending_side = None
    trades = []
    positions = []
    equities = []
    for offset, (date, row) in enumerate(selected.iterrows()):
        if offset == 0:
            cash, shares, side, quantity, gross, fee = _trade_to_weight(cash, shares, float(row.Open), 0.90, fee_rate)
            if quantity:
                trades.append({"Date": date, "Side": side, "Quantity": quantity, "Price": float(row.Open), "Gross": gross, "Fee": fee, "TargetWeight": 0.90})
            v = shares * float(row.Open)
        elif pending_side is not None:
            price = float(row.Open)
            target_shares = int(np.floor(v / price))
            if pending_side == "SELL" and target_shares < shares:
                quantity = shares - target_shares
                gross = quantity * price
                fee = gross * fee_rate
                cash += gross - fee
                shares = target_shares
                trades.append({"Date": date, "Side": "SELL", "Quantity": quantity, "Price": price, "Gross": gross, "Fee": fee, "TargetWeight": np.nan})
            elif pending_side == "BUY" and target_shares > shares:
                desired = target_shares - shares
                budget_shares = int(np.floor(min(cash, buy_budget) / (price * (1 + fee_rate))))
                quantity = min(desired, budget_shares)
                if quantity:
                    gross = quantity * price
                    fee = gross * fee_rate
                    cash -= gross + fee
                    buy_budget -= gross + fee
                    shares += quantity
                    trades.append({"Date": date, "Side": "BUY", "Quantity": quantity, "Price": price, "Gross": gross, "Fee": fee, "TargetWeight": np.nan})
            pending_side = None
        if offset % 10 == 0:
            if offset:
                v = v + cash / 10.0
            buy_budget = cash * 0.50
        stock_value = shares * float(row.Close)
        if stock_value > v * 1.15:
            pending_side = "SELL"
        elif stock_value < v * 0.85:
            pending_side = "BUY"
        equities.append(cash + shares * float(row.Close))
        positions.append({"Date": date, "Cash": cash, "Shares": shares, "TargetWeight": np.nan})
    trade_frame = pd.DataFrame(trades)
    if not trade_frame.empty:
        trade_frame = trade_frame.set_index("Date")
    return BacktestResult(pd.Series(equities, index=selected.index, name="Equity"), trade_frame, pd.DataFrame(positions).set_index("Date"), float(initial_cash))
