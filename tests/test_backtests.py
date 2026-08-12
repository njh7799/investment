from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from backtests.core import MarketData, run_weight_strategy
from backtests.models import build_target_weights
from backtests.documented import causal_reference_high, run_three_percent_rule, run_vr_5
from backtests.portfolio import run_portfolio_strategy
from backtests.allocation_models import (
    DAA_CANARY,
    DAA_G12_RISKY,
    ERC8_ASSETS,
    FAA_ASSETS,
    PAA_DEFENSIVE,
    PAA_RISKY,
    VAA_CASH,
    VAA_G4_RISKY,
    build_allocation_weights,
    _ordinal_ranks,
    solve_equal_risk_contribution,
)
from backtests.vo_upside import apply_upside_override, directional_features, variant_specs
from backtests.ma_research import apply_vo_trend, moving_average_score
from backtests.ma_research import signal_specs as ma_signal_specs
from backtests.ma_research import variant_specs as ma_variant_specs
from backtests.vo_bull import (
    bullish_breadth,
    confirmed_recovery_weights,
    multi_horizon_consensus,
    risk_adjusted_trend,
    variant_specs as bull_variant_specs,
)


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


def test_paa2_uses_breadth_fraction_and_top_six():
    index = pd.date_range("2023-01-31", periods=13, freq="ME")
    closes = pd.DataFrame(100.0, index=index, columns=[*PAA_RISKY, *PAA_DEFENSIVE])
    closes.loc[index[-1], list(PAA_RISKY[:5])] = 80.0
    closes.loc[index[-1], list(PAA_RISKY[5:])] = 120.0
    closes.loc[index[-1], "IEF"] = 110.0
    weights = build_allocation_weights("paa2", closes).iloc[-1]
    assert weights["IEF"] == pytest.approx(5.0 / 6.0)
    assert np.allclose(weights[list(PAA_RISKY[5:11])], 1.0 / 36.0)
    assert weights.sum() == pytest.approx(1.0)


def test_vaa_g4_switches_fully_to_best_cash_when_one_risky_asset_is_bad():
    index = pd.date_range("2023-01-31", periods=13, freq="ME")
    columns = list(dict.fromkeys([*VAA_G4_RISKY, *VAA_CASH]))
    closes = pd.DataFrame(100.0, index=index, columns=columns)
    closes.loc[index[-1], list(VAA_G4_RISKY)] = [120.0, 120.0, 80.0, 120.0]
    closes.loc[index[-1], list(VAA_CASH)] = [101.0, 110.0, 105.0]

    weights = build_allocation_weights("vaa_g4", closes).iloc[-1]

    assert weights["IEF"] == pytest.approx(1.0)
    assert weights[list(VAA_G4_RISKY)].sum() == pytest.approx(0.0)


def test_daa_g12_halves_cash_and_risky_slots_when_one_canary_is_bad():
    index = pd.date_range("2023-01-31", periods=13, freq="ME")
    columns = list(dict.fromkeys([*DAA_G12_RISKY, *DAA_CANARY, *VAA_CASH]))
    closes = pd.DataFrame(100.0, index=index, columns=columns)
    closes.loc[index[-1], list(DAA_G12_RISKY)] = 110.0
    closes.loc[index[-1], ["QQQ", "GLD"]] = [140.0, 130.0]
    closes.loc[index[-1], list(DAA_CANARY)] = [80.0, 120.0]
    closes.loc[index[-1], list(VAA_CASH)] = [101.0, 115.0, 105.0]

    weights = build_allocation_weights("daa_g12", closes).iloc[-1]

    assert weights["IEF"] == pytest.approx(0.5)
    assert weights["QQQ"] == pytest.approx(0.5)
    assert weights["GLD"] == pytest.approx(0.0)
    assert weights.sum() == pytest.approx(1.0)


def test_faa_ordinal_ranks_use_requested_direction_and_alphabetical_ties():
    values = pd.Series({"B": 2.0, "A": 2.0, "C": 1.0})

    assert list(_ordinal_ranks(values, ascending=False).sort_index()) == [1.0, 2.0, 3.0]
    assert list(_ordinal_ranks(values, ascending=True).sort_index()) == [2.0, 3.0, 1.0]


def test_faa_waits_four_months_and_replaces_nonpositive_slots_with_shy():
    index = pd.date_range("2024-01-31", periods=5, freq="ME")
    closes = pd.DataFrame(index=index)
    for offset, name in enumerate(FAA_ASSETS):
        closes[name] = [100.0 - (offset + 1) * step - (step % 2) * 0.1 * offset for step in range(5)]

    weights = build_allocation_weights("faa_default", closes)

    assert (weights.iloc[:4].sum(axis=1) == 0.0).all()
    assert weights.iloc[-1]["SHY"] == pytest.approx(1.0)
    assert weights.iloc[-1].sum() == pytest.approx(1.0)


def test_faa_signal_does_not_change_when_future_prices_change():
    index = pd.date_range("2024-01-31", periods=6, freq="ME")
    closes = pd.DataFrame(
        {name: [100.0 + (offset + 1) * step + (step % 2) * offset for step in range(6)] for offset, name in enumerate(FAA_ASSETS)},
        index=index,
    )
    revised = closes.copy()
    revised.loc[index[-1], "SPY"] *= 10.0

    original_weights = build_allocation_weights("faa_default", closes)
    revised_weights = build_allocation_weights("faa_default", revised)

    pd.testing.assert_frame_equal(original_weights.iloc[:-1], revised_weights.iloc[:-1])


def test_erc_equal_covariance_produces_equal_weights():
    solved = solve_equal_risk_contribution(np.eye(4))

    assert np.allclose(solved, 0.25, atol=1e-8)


def test_erc_solver_equalizes_fractional_risk_contributions():
    covariance = np.array(
        [
            [0.04, 0.006, 0.004],
            [0.006, 0.09, 0.012],
            [0.004, 0.012, 0.16],
        ]
    )
    solved = solve_equal_risk_contribution(covariance)
    fractional = solved * (covariance @ solved) / (solved @ covariance @ solved)

    assert np.allclose(fractional, 1.0 / 3.0, atol=1e-6)


def test_erc_waits_for_exactly_252_returns():
    index = pd.bdate_range("2023-01-02", periods=253)
    closes = pd.DataFrame(
        {name: 100.0 + (offset + 1) * np.arange(len(index)) + 0.01 * np.square(np.arange(len(index)) % (offset + 2)) for offset, name in enumerate(ERC8_ASSETS)},
        index=index,
    )

    weights = build_allocation_weights("erc8", closes)

    assert (weights.loc[: index[-2]].sum(axis=1) == 0.0).all()
    assert weights.loc[index[-1]].sum() == pytest.approx(1.0)


def test_erc_future_price_does_not_change_past_weights():
    index = pd.bdate_range("2022-01-03", periods=520)
    closes = pd.DataFrame(
        {name: 100.0 + (offset + 1) * np.arange(len(index)) + np.sin(np.arange(len(index)) / (offset + 2)) for offset, name in enumerate(ERC8_ASSETS)},
        index=index,
    )
    future_date = pd.bdate_range(index[-1] + pd.Timedelta(days=1), periods=1)[0]
    revised = pd.concat([closes, (closes.iloc[[-1]] * 1.001).set_axis([future_date])])

    original_weights = build_allocation_weights("erc8", closes)
    revised_weights = build_allocation_weights("erc8", revised)

    pd.testing.assert_frame_equal(original_weights, revised_weights.loc[index], check_freq=False)


def test_vo_boundaries_and_warmup():
    data = market([100.0] * 31)
    _, weights = build_target_weights("vo", data)
    assert (weights == 1.0).all()


def test_directional_features_use_exactly_trailing_thirty_returns_without_lookahead():
    index = pd.bdate_range("2024-01-02", periods=32)
    close = pd.Series([100.0] * 31 + [200.0], index=index)
    original = directional_features(close)
    revised = directional_features(close.where(close.index < index[-1], 50.0))

    assert original.loc[index[30], "total_return"] == pytest.approx(0.0)
    assert original.loc[index[-1], "total_return"] == pytest.approx(1.0)
    pd.testing.assert_frame_equal(original.iloc[:-1], revised.iloc[:-1])


def test_upside_override_actions_only_change_weights_when_condition_is_true():
    index = pd.bdate_range("2024-01-02", periods=4)
    base = pd.Series([1.0, 0.5, 0.0, 0.0], index=index)
    condition = pd.Series([False, True, True, False], index=index)

    assert list(apply_upside_override(base, condition, "floor50")) == [1.0, 0.5, 0.5, 0.0]
    assert list(apply_upside_override(base, condition, "floor100")) == [1.0, 1.0, 1.0, 0.0]
    assert list(apply_upside_override(base, condition, "step_up")) == [1.0, 1.0, 0.5, 0.0]
    assert list(apply_upside_override(base, condition, "block_cut")) == [1.0, 1.0, 1.0, 0.0]


def test_vo_upside_grid_is_fixed_and_unique():
    specs = variant_specs()
    assert len(specs) == 366
    assert len({spec.name for spec in specs}) == len(specs)


def test_moving_average_score_has_full_investment_warmup_and_no_lookahead():
    index = pd.bdate_range("2024-01-02", periods=52)
    close = pd.Series([100.0] * 51 + [200.0], index=index)
    spec = next(item for item in ma_signal_specs() if item.name == "price_sma_50")
    original = moving_average_score(close, spec)
    revised = moving_average_score(close.where(close.index < index[-1], 50.0), spec)

    assert (original.iloc[:49] == 1.0).all()
    pd.testing.assert_series_equal(original.iloc[:-1], revised.iloc[:-1])


def test_moving_average_band_retains_state_inside_band():
    index = pd.bdate_range("2024-01-02", periods=5)
    fast = pd.Series([100.0, 102.0, 100.5, 98.0, 100.0], index=index)
    slow = pd.Series(100.0, index=index)
    from backtests.ma_research import _stateful_band

    assert list(_stateful_band(fast, slow, 0.01)) == [1.0, 1.0, 1.0, 0.0, 0.0]


def test_vo_moving_average_confirmation_gates_changes_by_direction():
    index = pd.bdate_range("2024-01-02", periods=5)
    base = pd.Series([1.0, 0.5, 0.0, 0.5, 1.0], index=index)
    score = pd.Series([1.0, 1.0, 0.0, 0.0, 1.0], index=index)

    assert list(apply_vo_trend(base, score, "cut_confirm")) == [1.0, 1.0, 0.0, 0.5, 1.0]
    assert list(apply_vo_trend(base, score, "raise_confirm")) == [1.0, 0.5, 0.0, 0.0, 1.0]
    assert list(apply_vo_trend(base, score, "both_confirm")) == [1.0, 1.0, 0.0, 0.0, 1.0]


def test_moving_average_research_grid_is_fixed_and_unique():
    signals = ma_signal_specs()
    variants = ma_variant_specs()
    assert len(signals) == 53
    assert len(variants) == 458
    assert len({item.name for item in variants}) == len(variants)


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


def test_vo_bull_research_grid_is_preregistered_and_unique():
    variants = bull_variant_specs()
    assert len(variants) == 68
    assert len({variant.name for variant in variants}) == 68


def test_risk_adjusted_trend_uses_only_trailing_values():
    index = pd.bdate_range("2024-01-02", periods=23)
    close = pd.Series([100.0 + value for value in range(23)], index=index)
    original = risk_adjusted_trend(close, 20)
    revised = close.copy()
    revised.iloc[-1] = 1000.0
    updated = risk_adjusted_trend(revised, 20)
    pd.testing.assert_series_equal(original.iloc[:-1], updated.iloc[:-1])
    assert original.iloc[:20].isna().all()


def test_breadth_exact_minimum_is_inclusive_and_requires_warmup():
    index = pd.bdate_range("2024-01-02", periods=4)
    closes = pd.DataFrame({
        "QQQ": [10.0, 10.0, 11.0, 11.0],
        "SPY": [10.0, 10.0, 11.0, 11.0],
        "IWM": [10.0, 10.0, 9.0, 9.0],
    }, index=index)
    signal = bullish_breadth(closes, kind="return", horizon=2, minimum=2)
    assert not signal.iloc[1]
    assert signal.iloc[2]


def test_multi_horizon_consensus_counts_exact_boundary():
    close = pd.Series([10.0, 9.0, 10.0, 11.0], index=pd.bdate_range("2024-01-02", periods=4))
    signal = multi_horizon_consensus(close, (1, 2, 3), 2)
    assert not signal.iloc[2]
    assert signal.iloc[3]


def test_confirmed_recovery_cuts_first_then_restores_and_stops():
    index = pd.bdate_range("2024-01-02", periods=6)
    base = pd.Series([1.0, 0.5, 0.5, 0.5, 0.5, 1.0], index=index)
    close = pd.Series([100.0, 100.0, 109.0, 110.0, 99.0, 101.0], index=index)
    confirmation = pd.Series([True] * 6, index=index)
    weights = confirmed_recovery_weights(base, close, confirmation, 0.10)
    assert list(weights) == [1.0, 0.5, 0.5, 1.0, 0.5, 1.0]


def test_confirmed_recovery_resets_on_second_cut():
    index = pd.bdate_range("2024-01-02", periods=5)
    base = pd.Series([1.0, 0.5, 0.5, 0.0, 0.0], index=index)
    close = pd.Series([100.0, 100.0, 111.0, 110.0, 122.0], index=index)
    confirmation = pd.Series([True] * 5, index=index)
    weights = confirmed_recovery_weights(base, close, confirmation, 0.10)
    assert list(weights) == [1.0, 0.5, 1.0, 0.0, 0.5]
