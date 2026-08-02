from __future__ import annotations

import pandas as pd
import pytest

from backtests.core import MarketData, run_weight_strategy
from backtests.models import build_target_weights
from backtests.documented import causal_reference_high, run_three_percent_rule, run_vr_5
from backtests.portfolio import run_portfolio_strategy
from backtests.allocation_models import build_allocation_weights


def prices(values, opens=None, start="2024-01-02"):
    index = pd.bdate_range(start, periods=len(values))
    opens = values if opens is None else opens
    return pd.DataFrame(
        {"Open": opens, "High": values, "Low": values, "Close": values}, index=index, dtype=float
    )


def market(close):
    frame = prices(close)
    return MarketData(ixic=frame, qqq=frame, tqqq=frame)


def test_initial_integer_purchase_and_fee():
    frame = prices([10, 11])
    weights = pd.Series([1.0, 1.0], index=frame.index)
    result = run_weight_strategy(frame, weights, initial_cash=100, fee_rate=0.01)
    assert result.positions.iloc[0]["Shares"] == 9
    assert result.positions.iloc[0]["Cash"] == pytest.approx(9.1)
    assert result.trades.iloc[0]["Fee"] == pytest.approx(0.9)


def test_close_signal_executes_at_next_open():
    frame = prices([10, 10, 10], opens=[10, 20, 30])
    weights = pd.Series([0.0, 1.0, 1.0], index=frame.index)
    result = run_weight_strategy(frame, weights, initial_cash=100, fee_rate=0)
    assert len(result.trades) == 1
    assert result.trades.index[0] == frame.index[2]
    assert result.trades.iloc[0]["Price"] == 30


def test_last_day_signal_remains_unfilled():
    frame = prices([10, 10])
    weights = pd.Series([0.0, 1.0], index=frame.index)
    result = run_weight_strategy(frame, weights, initial_cash=100, fee_rate=0)
    assert result.trades.empty


def test_state_change_only_rebalances_once():
    frame = prices([10, 11, 12, 13])
    weights = pd.Series([0.0, 1.0, 1.0, 1.0], index=frame.index)
    result = run_weight_strategy(frame, weights, initial_cash=100, fee_rate=0)
    assert len(result.trades) == 1


def test_multi_asset_sells_before_buying_and_uses_integer_shares():
    index = pd.bdate_range("2024-01-02", periods=3)
    a = prices([10, 10, 10], start="2024-01-02")
    b = prices([20, 20, 20], start="2024-01-02")
    weights = pd.DataFrame({"A": [1.0, 0.0, 0.0], "B": [0.0, 1.0, 1.0]}, index=index)
    result = run_portfolio_strategy({"A": a, "B": b}, weights, initial_cash=105, fee_rate=0)
    assert list(result.trades.Side) == ["BUY", "SELL", "BUY"]
    assert result.positions.iloc[-1].BShares == 5


def test_summary_counts_one_rebalance_date_for_multiple_orders():
    from backtests.metrics import summarize

    index = pd.bdate_range("2024-01-02", periods=3)
    a = prices([10, 10, 10], start="2024-01-02")
    b = prices([20, 20, 20], start="2024-01-02")
    weights = pd.DataFrame({"A": [0.5, 0.0, 0.0], "B": [0.5, 1.0, 1.0]}, index=index)
    result = run_portfolio_strategy({"A": a, "B": b}, weights, initial_cash=100, fee_rate=0)
    assert len(result.trades) == 4
    assert summarize(result)["trade_count"] == 2


def test_monthly_rebalance_trades_even_when_target_is_unchanged():
    index = pd.bdate_range("2024-01-29", "2024-02-02")
    a = pd.DataFrame({column: [10, 20, 20, 20, 20] for column in ["Open", "High", "Low", "Close"]}, index=index)
    b = pd.DataFrame({column: [10, 10, 10, 10, 10] for column in ["Open", "High", "Low", "Close"]}, index=index)
    weights = pd.DataFrame({"A": 0.5, "B": 0.5}, index=index)
    result = run_portfolio_strategy({"A": a, "B": b}, weights, initial_cash=100, fee_rate=0, rebalance_monthly=True)
    assert result.trades.index.nunique() == 2


def test_gtaa_waits_for_ten_months_and_allocates_fixed_slots():
    index = pd.date_range("2023-01-31", periods=11, freq="ME")
    closes = pd.DataFrame({name: range(100, 111) for name in ["SPY", "EFA", "IEF", "VNQ", "DBC"]}, index=index)
    weights = build_allocation_weights("gtaa5", closes)
    assert weights.iloc[8].sum() == 0.0
    assert weights.iloc[9].sum() == pytest.approx(1.0)


def test_vo_boundaries_and_warmup():
    data = market([100.0] * 31)
    _, weights = build_target_weights("vo", data)
    assert (weights == 1.0).all()


def test_absolute_momentum_and_tsmom_are_identical():
    index = pd.bdate_range("2020-01-02", periods=800)
    frame = pd.DataFrame(index=index)
    frame["Close"] = range(100, 900)
    for column in ["Open", "High", "Low"]:
        frame[column] = frame["Close"]
    data = MarketData(ixic=frame, qqq=frame, tqqq=frame)
    _, absolute = build_target_weights("absolute_momentum_12m", data)
    _, tsmom = build_target_weights("tsmom_12m", data)
    pd.testing.assert_series_equal(absolute, tsmom)


def test_turtle_uses_prior_window_without_lookahead():
    close = [10.0] * 56 + [11.0, 9.0]
    data = market(close)
    _, weights = build_target_weights("turtle_55_20", data)
    assert weights.iloc[56] == 1.0
    assert weights.iloc[57] == 0.0


def test_bll_vma_one_percent_band_retains_state_at_boundaries():
    close = [100.0] * 150 + [102.0, 100.5, 98.0]
    data = market(close)
    _, weights = build_target_weights("bll_vma_1_150_b1", data)
    assert weights.iloc[150] == 1.0
    assert weights.iloc[151] == 1.0
    assert weights.iloc[152] == 0.0


def test_bll_trading_range_uses_only_prior_closes():
    close = [100.0] * 50 + [101.0, 100.0, 99.0]
    data = market(close)
    _, weights = build_target_weights("bll_trb_50", data)
    assert weights.iloc[50] == 1.0
    assert weights.iloc[51] == 1.0
    assert weights.iloc[52] == 0.0


def test_calendar_signal_is_advanced_for_next_open_execution():
    index = pd.bdate_range("2024-10-29", "2024-11-04")
    frame = pd.DataFrame({column: 10.0 for column in ["Open", "High", "Low", "Close"]}, index=index)
    data = MarketData(ixic=frame, qqq=frame, tqqq=frame)
    _, weights = build_target_weights("halloween", data)
    assert weights.loc["2024-10-31"] == 1.0


def test_summary_uses_initial_cash_not_first_close_value():
    from backtests.metrics import summarize

    frame = prices([20, 20], opens=[10, 20])
    weights = pd.Series([1.0, 1.0], index=frame.index)
    result = run_weight_strategy(frame, weights, initial_cash=100, fee_rate=0)
    assert summarize(result)["total_return"] == pytest.approx(1.0)


def test_causal_reference_high_does_not_revise_past_values():
    frame = prices([100.0] * 14 + [120.0, 118.0, 115.0, 100.0])
    frame["High"] = frame["Close"] + 1.0
    frame["Low"] = frame["Close"] - 1.0
    reference = causal_reference_high(frame)
    assert reference.iloc[14] == 120.0
    assert reference.iloc[-1] == 120.0


def test_vr_starts_with_approximately_ninety_percent_stock():
    frame = prices([10.0] * 12)
    result = run_vr_5(frame, initial_cash=1000, fee_rate=0)
    assert result.positions.iloc[0].Shares == 90
    assert result.positions.iloc[0].Cash == 100


def test_vr_uses_close_signal_and_next_open_execution():
    frame = prices(
        [10.0, 20.0, 20.0, 20.0],
        opens=[10.0, 10.0, 30.0, 20.0],
    )
    frame["High"] = 100.0
    frame["Low"] = 1.0

    result = run_vr_5(frame, initial_cash=1000, fee_rate=0)

    trade = result.trades.loc[frame.index[2]]
    assert trade.Side == "SELL"
    assert trade.Price == 30.0


def test_three_percent_rule_starts_fully_invested():
    frame = prices([10.0] * 20)
    data = MarketData(ixic=frame, qqq=frame, tqqq=frame)
    result = run_three_percent_rule(data, initial_cash=1000, fee_rate=0)
    assert result.positions.iloc[0].Shares == 100


def test_three_percent_rule_does_not_recheck_signal_at_next_open():
    tqqq = prices([100.0] * 20 + [80.0, 100.0], opens=[100.0] * 22)
    flat = prices([100.0] * 22)
    data = MarketData(ixic=flat, qqq=flat, tqqq=tqqq)

    result = run_three_percent_rule(data, initial_cash=1000, fee_rate=0)

    assert result.trades.iloc[-1].TargetWeight == pytest.approx(0.8)
    assert result.positions.iloc[-1].Shares == 8
