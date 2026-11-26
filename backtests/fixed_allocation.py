from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .core import BacktestResult


CalendarFrequency = Literal["daily", "weekly", "monthly", "quarterly", "annual", "never"]


@dataclass(frozen=True)
class FixedAllocationDiagnostics:
    result: BacktestResult
    scheduled_reviews: int
    turnover: float


def calendar_review_closes(index: pd.DatetimeIndex, frequency: CalendarFrequency) -> pd.Series:
    """Return closes whose fixed-weight review is executed at the following open."""
    if frequency not in {"daily", "weekly", "monthly", "quarterly", "annual", "never"}:
        raise ValueError(f"unsupported frequency: {frequency}")
    review = np.zeros(len(index), dtype=bool)
    if frequency == "never" or not len(index):
        return pd.Series(review, index=index)
    if frequency == "daily":
        review[:] = True
    else:
        codes = {
            "weekly": index.to_period("W-FRI"),
            "monthly": index.to_period("M"),
            "quarterly": index.to_period("Q"),
            "annual": index.to_period("Y"),
        }[frequency]
        if len(index) > 1:
            review[:-1] = np.asarray(codes[:-1] != codes[1:])
        review[-1] = True
    return pd.Series(review, index=index)


def run_fixed_allocation(
    tqqq: pd.DataFrame,
    qqq: pd.DataFrame,
    target: tuple[float, float, float],
    *,
    frequency: CalendarFrequency | None = None,
    band: float | None = None,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    initial_cash: float = 100_000.0,
    fee_rate: float = 0.001,
    record_positions: bool = True,
    record_trade_details: bool = True,
) -> FixedAllocationDiagnostics:
    """Run a long-only TQQQ/QQQ/cash constant-mix policy with whole shares."""
    if (frequency is None) == (band is None):
        raise ValueError("provide exactly one of frequency or band")
    if band is not None and not 0 < band <= 1:
        raise ValueError("band must be in (0, 1]")
    if initial_cash <= 0 or fee_rate < 0:
        raise ValueError("initial_cash must be positive and fee_rate non-negative")
    weights = np.asarray(target, dtype=float)
    if np.any(weights < 0) or not np.isclose(weights.sum(), 1.0):
        raise ValueError("target weights must be nonnegative and sum to one")

    index = tqqq.index.intersection(qqq.index)
    if start is not None:
        index = index[index >= pd.Timestamp(start)]
    if end is not None:
        index = index[index <= pd.Timestamp(end)]
    if index.empty:
        raise ValueError("selected backtest period is empty")

    opens = np.column_stack(
        [tqqq.loc[index, "Open"].to_numpy(float), qqq.loc[index, "Open"].to_numpy(float)]
    )
    closes = np.column_stack(
        [tqqq.loc[index, "Close"].to_numpy(float), qqq.loc[index, "Close"].to_numpy(float)]
    )
    reviews = None if frequency is None else calendar_review_closes(index, frequency).to_numpy(bool)
    shares = np.zeros(2, dtype=np.int64)
    cash = float(initial_cash)
    due = True
    scheduled_reviews = 0
    turnover = 0.0
    trade_rows: list[dict[str, object]] = []
    position_rows: list[dict[str, object]] = []
    equity_values: list[float] = []

    for location, date in enumerate(index):
        if due:
            open_equity = cash + float(np.dot(shares, opens[location]))
            desired = np.floor(open_equity * weights[:2] / opens[location]).astype(np.int64)
            deltas = desired - shares
            for asset_location, asset in enumerate(("TQQQ", "QQQ")):
                if deltas[asset_location] >= 0:
                    continue
                quantity = int(-deltas[asset_location])
                gross = quantity * opens[location, asset_location]
                fee = gross * fee_rate
                cash += gross - fee
                shares[asset_location] -= quantity
                turnover += gross
                detail = {"Date": date, "Gross": gross, "Fee": fee}
                if record_trade_details:
                    detail.update({"Asset": asset, "Side": "SELL", "Quantity": quantity,
                                   "Price": opens[location, asset_location],
                                   "TargetWeight": weights[asset_location]})
                trade_rows.append(detail)
            for asset_location, asset in enumerate(("TQQQ", "QQQ")):
                wanted = int(desired[asset_location] - shares[asset_location])
                if wanted <= 0:
                    continue
                price = opens[location, asset_location]
                quantity = min(wanted, int(np.floor(cash / (price * (1.0 + fee_rate)))))
                if quantity <= 0:
                    continue
                gross = quantity * price
                fee = gross * fee_rate
                cash -= gross + fee
                shares[asset_location] += quantity
                turnover += gross
                detail = {"Date": date, "Gross": gross, "Fee": fee}
                if record_trade_details:
                    detail.update({"Asset": asset, "Side": "BUY", "Quantity": quantity,
                                   "Price": price, "TargetWeight": weights[asset_location]})
                trade_rows.append(detail)
            due = False

        close_equity = cash + float(np.dot(shares, closes[location]))
        equity_values.append(close_equity)
        if record_positions:
            position_rows.append(
                {"Date": date, "Cash": cash, "TQQQShares": int(shares[0]),
                 "QQQShares": int(shares[1])}
            )
        if location == len(index) - 1:
            continue
        if reviews is not None:
            due = bool(reviews[location])
            scheduled_reviews += int(due)
        else:
            actual = np.array(
                [shares[0] * closes[location, 0], shares[1] * closes[location, 1], cash]
            ) / close_equity
            due = bool(np.any(np.abs(actual[:2] - weights[:2]) >= float(band) - 1e-12))
            scheduled_reviews += int(due)

    trades = pd.DataFrame(trade_rows)
    if not trades.empty:
        trades = trades.set_index("Date")
    result = BacktestResult(
        equity=pd.Series(equity_values, index=index, name="Equity"),
        trades=trades,
        positions=(pd.DataFrame(position_rows).set_index("Date") if position_rows
                   else pd.DataFrame(columns=["Cash", "TQQQShares", "QQQShares"])),
        initial_cash=float(initial_cash),
    )
    return FixedAllocationDiagnostics(result=result, scheduled_reviews=scheduled_reviews, turnover=turnover)
