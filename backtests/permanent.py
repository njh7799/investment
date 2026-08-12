from __future__ import annotations

import numpy as np
import pandas as pd

from .core import BacktestResult, _affordable_shares
from .portfolio import common_index


PERMANENT_ASSETS = ("SPY", "TLT", "GLD", "SHY")


def permanent_band_trigger(weights: pd.Series, lower: float = 0.15, upper: float = 0.35) -> bool:
    selected = weights.loc[list(PERMANENT_ASSETS)]
    return bool((selected < lower).any() or (selected > upper).any())


def run_permanent_portfolio(
    assets: dict[str, pd.DataFrame],
    *,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    initial_cash: float = 100_000.0,
    fee_rate: float = 0.001,
    annual_equal: bool = False,
) -> BacktestResult:
    if tuple(assets) != PERMANENT_ASSETS:
        raise ValueError(f"assets must be ordered as {PERMANENT_ASSETS}")
    if initial_cash <= 0 or fee_rate < 0:
        raise ValueError("initial_cash must be positive and fee_rate non-negative")

    full_index = common_index(assets)
    selected = full_index
    if start is not None:
        selected = selected[selected >= pd.Timestamp(start)]
    if end is not None:
        selected = selected[selected <= pd.Timestamp(end)]
    if selected.empty:
        raise ValueError("selected backtest period is empty")

    annual_reviews = set(
        date
        for position, date in enumerate(full_index)
        if position == len(full_index) - 1 or full_index[position + 1].year != date.year
    )
    cash = float(initial_cash)
    shares = {name: 0 for name in PERMANENT_ASSETS}
    pending_rebalance = True
    trades: list[dict[str, object]] = []
    positions: list[dict[str, object]] = []
    equity_values: list[float] = []

    for date in selected:
        opens = {name: float(assets[name].loc[date, "Open"]) for name in PERMANENT_ASSETS}
        if pending_rebalance:
            open_equity = cash + sum(shares[name] * opens[name] for name in PERMANENT_ASSETS)
            desired = {name: int(np.floor(open_equity * 0.25 / opens[name])) for name in PERMANENT_ASSETS}
            for name in PERMANENT_ASSETS:
                delta = desired[name] - shares[name]
                if delta >= 0:
                    continue
                quantity = -delta
                gross = quantity * opens[name]
                fee = gross * fee_rate
                cash += gross - fee
                shares[name] -= quantity
                trades.append({"Date": date, "Asset": name, "Side": "SELL", "Quantity": quantity, "Price": opens[name], "Gross": gross, "Fee": fee, "TargetWeight": 0.25})
            for name in PERMANENT_ASSETS:
                delta = desired[name] - shares[name]
                quantity = _affordable_shares(cash, opens[name], delta, fee_rate)
                if quantity <= 0:
                    continue
                gross = quantity * opens[name]
                fee = gross * fee_rate
                cash -= gross + fee
                shares[name] += quantity
                trades.append({"Date": date, "Asset": name, "Side": "BUY", "Quantity": quantity, "Price": opens[name], "Gross": gross, "Fee": fee, "TargetWeight": 0.25})
            pending_rebalance = False

        closes = {name: float(assets[name].loc[date, "Close"]) for name in PERMANENT_ASSETS}
        close_equity = cash + sum(shares[name] * closes[name] for name in PERMANENT_ASSETS)
        equity_values.append(close_equity)
        row = {"Date": date, "Cash": cash}
        row.update({f"{name}Shares": shares[name] for name in PERMANENT_ASSETS})
        positions.append(row)

        if date in annual_reviews:
            weights = pd.Series({name: shares[name] * closes[name] / close_equity for name in PERMANENT_ASSETS})
            pending_rebalance = annual_equal or permanent_band_trigger(weights)

    trade_frame = pd.DataFrame(trades)
    if not trade_frame.empty:
        trade_frame = trade_frame.set_index("Date")
    return BacktestResult(
        equity=pd.Series(equity_values, index=selected, name="Equity"),
        trades=trade_frame,
        positions=pd.DataFrame(positions).set_index("Date"),
        initial_cash=float(initial_cash),
    )
