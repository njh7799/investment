from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .core import BacktestResult, OHLC, _affordable_shares, _read_prices


def load_assets(names: list[str] | tuple[str, ...], root: Path | str = ".") -> dict[str, pd.DataFrame]:
    assets = Path(root) / "assets"
    return {name: _read_prices(assets / f"{name}.csv") for name in names}


def common_index(assets: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    iterator = iter(assets.values())
    index = next(iterator).index
    for frame in iterator:
        index = index.intersection(frame.index)
    return index


def run_portfolio_strategy(
    assets: dict[str, pd.DataFrame],
    target_weights: pd.DataFrame,
    *,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    initial_cash: float = 100_000.0,
    fee_rate: float = 0.001,
    rebalance_monthly: bool = False,
) -> BacktestResult:
    """Execute close-derived multi-asset target weights at the next common open."""
    if initial_cash <= 0 or fee_rate < 0:
        raise ValueError("initial_cash must be positive and fee_rate non-negative")
    names = list(assets)
    index = common_index(assets).intersection(target_weights.index)
    if start is not None:
        index = index[index >= pd.Timestamp(start)]
    if end is not None:
        index = index[index <= pd.Timestamp(end)]
    if index.empty:
        raise ValueError("selected backtest period is empty")

    full_index = common_index(assets).intersection(target_weights.index)
    weights = target_weights.reindex(full_index).fillna(0.0).clip(lower=0.0)
    if (weights.sum(axis=1) > 1.0 + 1e-12).any():
        raise ValueError("target weights exceed 100%")
    cash = float(initial_cash)
    shares = {name: 0 for name in names}
    last_target: tuple[float, ...] | None = None
    trades: list[dict[str, object]] = []
    positions: list[dict[str, object]] = []
    equity: list[float] = []
    first = full_index.get_loc(index[0])

    for offset, date in enumerate(index):
        location = first + offset
        pending = weights.iloc[0] if location == 0 else weights.iloc[location - 1]
        target_key = tuple(float(pending.get(name, 0.0)) for name in names)
        opens = {name: float(assets[name].loc[date, "Open"]) for name in names}
        open_equity = cash + sum(shares[name] * opens[name] for name in names)
        first_session_of_month = offset == 0 or index[offset - 1].to_period("M") != date.to_period("M")
        if last_target is None or not np.allclose(target_key, last_target) or (rebalance_monthly and first_session_of_month):
            desired = {name: int(np.floor(open_equity * pending.get(name, 0.0) / opens[name])) for name in names}
            for name in names:
                delta = desired[name] - shares[name]
                if delta >= 0:
                    continue
                quantity = -delta
                gross = quantity * opens[name]
                fee = gross * fee_rate
                cash += gross - fee
                shares[name] -= quantity
                trades.append({"Date": date, "Asset": name, "Side": "SELL", "Quantity": quantity, "Price": opens[name], "Gross": gross, "Fee": fee, "TargetWeight": pending.get(name, 0.0)})
            for name in names:
                delta = desired[name] - shares[name]
                quantity = _affordable_shares(cash, opens[name], delta, fee_rate)
                if quantity <= 0:
                    continue
                gross = quantity * opens[name]
                fee = gross * fee_rate
                cash -= gross + fee
                shares[name] += quantity
                trades.append({"Date": date, "Asset": name, "Side": "BUY", "Quantity": quantity, "Price": opens[name], "Gross": gross, "Fee": fee, "TargetWeight": pending.get(name, 0.0)})
            last_target = target_key

        close_equity = cash + sum(shares[name] * float(assets[name].loc[date, "Close"]) for name in names)
        equity.append(close_equity)
        row = {"Date": date, "Cash": cash}
        row.update({f"{name}Shares": shares[name] for name in names})
        positions.append(row)

    trade_frame = pd.DataFrame(trades)
    if not trade_frame.empty:
        trade_frame = trade_frame.set_index("Date")
    return BacktestResult(
        equity=pd.Series(equity, index=index, name="Equity"),
        trades=trade_frame,
        positions=pd.DataFrame(positions).set_index("Date"),
        initial_cash=float(initial_cash),
    )
