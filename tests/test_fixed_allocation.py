from __future__ import annotations

import pandas as pd
import pytest

from backtests import load_market_data
from backtests.fixed_allocation import calendar_review_closes, run_fixed_allocation
from scripts.analyze_fixed_allocation_batch import weight_grid


def prices(index, opens, closes=None):
    closes = opens if closes is None else closes
    return pd.DataFrame(
        {"Open": opens, "High": closes, "Low": closes, "Close": closes},
        index=pd.DatetimeIndex(index),
        dtype=float,
    )


def test_target_validation():
    index = pd.bdate_range("2024-01-02", periods=2)
    frame = prices(index, [10, 10])
    with pytest.raises(ValueError, match="sum to one"):
        run_fixed_allocation(frame, frame, (0.5, 0.5, 0.5), frequency="never")
    with pytest.raises(ValueError, match="exactly one"):
        run_fixed_allocation(frame, frame, (0.5, 0.5, 0), frequency="daily", band=0.1)


def test_registered_simplex_grid_is_complete():
    primary = weight_grid(10)
    stability = weight_grid(5)
    assert len(primary) == 66
    assert len(stability) == 231
    assert all(min(target) >= 0 and sum(target) == pytest.approx(1.0) for target in stability)


def test_initial_allocation_and_daily_close_execute_at_next_open():
    index = pd.bdate_range("2024-01-02", periods=3)
    tqqq = prices(index, [10, 20, 30], [10, 30, 30])
    qqq = prices(index, [10, 10, 10])
    diagnostics = run_fixed_allocation(tqqq, qqq, (0.5, 0.5, 0), frequency="daily", initial_cash=100, fee_rate=0)

    first = diagnostics.result.trades.loc[index[0]]
    second = diagnostics.result.trades.loc[index[1]]
    assert set(first.Asset) == {"TQQQ", "QQQ"}
    assert set(second.Side) == {"SELL", "BUY"}
    assert set(second.Price) == {20.0, 10.0}


def test_last_close_review_remains_unfilled():
    index = pd.bdate_range("2024-01-02", periods=2)
    tqqq = prices(index, [10, 10], [10, 20])
    qqq = prices(index, [10, 10])
    diagnostics = run_fixed_allocation(tqqq, qqq, (0.5, 0.5, 0), frequency="daily", initial_cash=100, fee_rate=0)

    assert diagnostics.result.trades.index.unique().tolist() == [index[0]]
    assert diagnostics.scheduled_reviews == 1


def test_period_boundaries_use_last_available_session():
    index = pd.to_datetime(["2024-03-27", "2024-03-28", "2024-04-01", "2024-04-02"])
    weekly = calendar_review_closes(index, "weekly")
    monthly = calendar_review_closes(index, "monthly")
    quarterly = calendar_review_closes(index, "quarterly")

    assert weekly[weekly].index.tolist() == [pd.Timestamp("2024-03-28"), pd.Timestamp("2024-04-02")]
    assert monthly[monthly].index.tolist() == [pd.Timestamp("2024-03-28"), pd.Timestamp("2024-04-02")]
    assert quarterly[quarterly].index.tolist() == [pd.Timestamp("2024-03-28"), pd.Timestamp("2024-04-02")]


def test_band_equality_triggers_but_below_boundary_does_not():
    index = pd.bdate_range("2024-01-02", periods=3)
    qqq = prices(index, [10, 10, 10])
    equality = prices(index, [10, 10, 110 / 9], [10, 110 / 9, 110 / 9])
    below = prices(index, [10, 10, 10], [10, 12.21, 12.21])

    hit = run_fixed_allocation(equality, qqq, (0.5, 0.5, 0), band=0.05, initial_cash=100, fee_rate=0)
    miss = run_fixed_allocation(below, qqq, (0.5, 0.5, 0), band=0.05, initial_cash=100, fee_rate=0)

    assert hit.result.trades.index.unique().tolist() == [index[0], index[2]]
    assert miss.result.trades.index.unique().tolist() == [index[0]]


def test_sells_before_buys_charges_both_fees_and_preserves_cash():
    index = pd.bdate_range("2024-01-02", periods=3)
    tqqq = prices(index, [10, 10, 20], [10, 20, 20])
    qqq = prices(index, [10, 10, 10])
    diagnostics = run_fixed_allocation(tqqq, qqq, (0.5, 0.5, 0), frequency="daily", initial_cash=1_000, fee_rate=0.01)
    trades = diagnostics.result.trades.loc[index[2]]

    assert trades.iloc[0].Side == "SELL"
    assert trades.iloc[-1].Side == "BUY"
    assert (trades.Fee > 0).all()
    assert (diagnostics.result.positions.Cash >= -1e-9).all()


def test_synthetic_to_live_tqqq_boundary_is_present_and_aligned():
    data = load_market_data(".")
    boundary = pd.to_datetime(["2010-02-10", "2010-02-11"])
    assert data.tqqq.loc[boundary].notna().all().all()
    assert data.qqq.loc[boundary].notna().all().all()
    assert (data.tqqq.loc[boundary, ["Open", "High", "Low", "Close"]] > 0).all().all()
