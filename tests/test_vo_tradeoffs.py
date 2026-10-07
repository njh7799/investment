from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtests import BacktestResult, run_weight_strategy
from scripts.analyze_vo_tradeoffs import (
    annual_returns, falling_low_volatility_runs, full_weight_drawdowns,
    reduced_episodes, runs,
)


def fixture(close, weights, opens=None, fee=0):
    index = pd.bdate_range("2024-01-02", periods=len(close))
    prices = pd.DataFrame({"Open": close if opens is None else opens, "Close": close}, index=index)
    result = run_weight_strategy(prices, pd.Series(weights, index=index), initial_cash=10_000, fee_rate=fee)
    features = pd.DataFrame({"volatility": .5, "return30": .1}, index=index)
    return prices, result, features


def test_annual_returns_carry_previous_year_close_and_initial_fee():
    equity = pd.Series([99, 120, 132, 150], index=pd.to_datetime([
        "2023-01-03", "2023-12-29", "2024-01-02", "2024-12-31"]))
    result = BacktestResult(equity, pd.DataFrame(), pd.DataFrame(), 100)
    annual = annual_returns(result)
    assert annual.return_rate.tolist() == pytest.approx([.20, .25])
    assert np.prod(1 + annual.return_rate) == pytest.approx(1.5)


def test_reduced_episode_keeps_open_gap_and_excludes_reentry_fee():
    prices, result, features = fixture([100, 110, 120, 130, 160], [1, .5, 0, 1, 1],
                                       opens=[100, 100, 110, 120, 150], fee=.001)
    rows = reduced_episodes(prices, result, features)
    row = rows.iloc[0]
    assert len(rows) == 1  # Half and zero exposure are one uninterrupted episode.
    assert row.start == prices.index[2]
    assert row.end == prices.index[4]
    assert row.trading_days == 2
    before, final = result.positions.iloc[1], result.positions.iloc[3]
    base = before.Cash + before.Shares * 110
    assert row.keep_shares_return == pytest.approx((before.Cash + before.Shares * 150) / base - 1)
    assert row.vo_return == pytest.approx((final.Cash + final.Shares * 150) / base - 1)
    assert row.signal_date == prices.index[1]


def test_last_signal_does_not_create_executed_cut_and_unfinished_run_uses_close():
    prices, result, features = fixture([100, 120, 140], [1, 1, 0])
    assert reduced_episodes(prices, result, features).empty
    prices, result, features = fixture([100, 120, 140], [1, 0, 1])
    row = reduced_episodes(prices, result, features).iloc[0]
    assert row.end_mark == "close_data_end"
    assert row.start == prices.index[-1]
    assert row.tqqq_return == 0  # Same day's equal open and close, no invented next open.


def test_full_weight_drawdowns_count_recoveries_once_and_include_exit_gap():
    prices, result, features = fixture([100, 90, 95, 100, 95, 70], [1, 1, 1, 1, .5, .5],
                                       opens=[100, 100, 90, 95, 100, 80])
    rows = full_weight_drawdowns(prices, result, features)
    assert len(rows) == 2
    assert rows.vo_drawdown.tolist() == pytest.approx([-.10, -.20])
    assert rows.iloc[0].recovery_within_full_weight == prices.index[3]
    assert rows.iloc[1].trough_mark == "open_before_rebalance"
    # The 70 close happens after the cut and cannot enter the full-exposure drawdown.
    assert rows.iloc[1].trough == prices.index[5]


def test_low_vol_falling_states_use_only_prior_close_and_include_boundary():
    prices, result, features = fixture([100, 95, 90, 85, 80], [1]*5)
    features["return30"] = [np.nan, -.05, -.10, .01, -.20]
    features["volatility"] = [np.nan, .60, .60001, .50, .50]
    rows = falling_low_volatility_runs(prices, result, features)
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row.start == prices.index[2]  # Exactly 60% qualifies on the following day.
    assert row.end == prices.index[3]
    assert row.vo_return == pytest.approx(85/90-1)
    assert runs(pd.Series([False, True, True, False, True])) == [(1, 2), (4, 4)]


def test_initial_reduced_state_is_not_called_a_sale_of_prior_holdings():
    prices, result, features = fixture([100, 120, 130], [.5, .5, .5])
    assert reduced_episodes(prices, result, features).empty


def test_individual_cuts_include_half_to_zero_and_stop_at_prior_target():
    prices, result, features = fixture([100, 110, 120, 130, 140, 150], [1, .5, 0, .5, 1, 1])
    rows = reduced_episodes(prices, result, features, every_cut=True)
    assert len(rows) == 2
    assert rows.previous_weight.tolist() == [1, .5]
    assert rows.iloc[0].end == prices.index[5]
    assert rows.iloc[1].start == prices.index[3]
    assert rows.iloc[1].end == prices.index[4]
