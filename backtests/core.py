from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


OHLC = ["Open", "High", "Low", "Close"]


@dataclass(frozen=True)
class MarketData:
    ixic: pd.DataFrame
    qqq: pd.DataFrame
    tqqq: pd.DataFrame

    @property
    def index(self) -> pd.DatetimeIndex:
        return self.qqq.index.intersection(self.tqqq.index).intersection(self.ixic.index)


@dataclass(frozen=True)
class BacktestResult:
    equity: pd.Series
    trades: pd.DataFrame
    positions: pd.DataFrame
    initial_cash: float


def _read_prices(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["Date"] = pd.to_datetime(frame["Date"], format="%Y.%m.%d")
    frame = frame.set_index("Date")[OHLC].astype(float).sort_index()
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError(f"invalid market-data index: {path}")
    return frame


def load_market_data(root: Path | str = ".") -> MarketData:
    assets = Path(root) / "assets"
    return MarketData(
        ixic=_read_prices(assets / "IXIC.csv"),
        qqq=_read_prices(assets / "QQQ.csv"),
        tqqq=_read_prices(assets / "TQQQ.csv"),
    )


def _affordable_shares(cash: float, price: float, desired: int, fee_rate: float) -> int:
    if desired <= 0:
        return 0
    return min(desired, int(np.floor(cash / (price * (1.0 + fee_rate)))))


def run_weight_strategy(
    prices: pd.DataFrame,
    target_weights: pd.Series,
    *,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    initial_cash: float = 100_000.0,
    fee_rate: float = 0.001,
) -> BacktestResult:
    """Execute close-derived target weights at the next session's open."""
    if initial_cash <= 0 or fee_rate < 0:
        raise ValueError("initial_cash must be positive and fee_rate non-negative")

    common = prices.index.intersection(target_weights.index)
    prices = prices.loc[common]
    weights = target_weights.loc[common].astype(float).clip(0.0, 1.0)
    if start is not None:
        prices = prices.loc[pd.Timestamp(start) :]
    if end is not None:
        prices = prices.loc[: pd.Timestamp(end)]
    if prices.empty:
        raise ValueError("selected backtest period is empty")

    cash = float(initial_cash)
    shares = 0
    last_target: float | None = None
    trade_rows: list[dict[str, object]] = []
    position_rows: list[dict[str, object]] = []
    equity_values: list[float] = []

    first_location = common.get_loc(prices.index[0])
    for offset, (date, row) in enumerate(prices.iterrows()):
        location = first_location + offset
        pending = float(weights.iloc[0]) if location == 0 else float(weights.iloc[location - 1])
        if pending is not None and (last_target is None or not np.isclose(pending, last_target)):
            open_price = float(row["Open"])
            open_equity = cash + shares * open_price
            desired = int(np.floor(open_equity * pending / open_price))
            delta = desired - shares
            if delta < 0:
                quantity = -delta
                gross = quantity * open_price
                fee = gross * fee_rate
                cash += gross - fee
                shares -= quantity
            elif delta > 0:
                quantity = _affordable_shares(cash, open_price, delta, fee_rate)
                gross = quantity * open_price
                fee = gross * fee_rate
                cash -= gross + fee
                shares += quantity
            else:
                quantity = 0
                gross = 0.0
                fee = 0.0
            if quantity:
                trade_rows.append(
                    {
                        "Date": date,
                        "Side": "BUY" if delta > 0 else "SELL",
                        "Quantity": quantity,
                        "Price": open_price,
                        "Gross": gross,
                        "Fee": fee,
                        "TargetWeight": pending,
                    }
                )
            last_target = pending

        close_equity = cash + shares * float(row["Close"])
        equity_values.append(close_equity)
        position_rows.append(
            {"Date": date, "Cash": cash, "Shares": shares, "TargetWeight": last_target}
        )

    equity = pd.Series(equity_values, index=prices.index, name="Equity")
    trades = pd.DataFrame(trade_rows)
    if not trades.empty:
        trades = trades.set_index("Date")
    positions = pd.DataFrame(position_rows).set_index("Date")
    return BacktestResult(equity=equity, trades=trades, positions=positions, initial_cash=float(initial_cash))
