import pandas as pd
import pytest

from backtests import MarketData, build_active_vo_allocation
from scripts.analyze_vo_sgov import build_execution_targets, run_sgov_strategy


def prices(index, value=100.0):
    return pd.DataFrame({"Open": value, "High": value, "Low": value, "Close": value}, index=index)


def distributions(ex_date="2024-01-04", pay_date="2024-01-08", amount=1.0):
    return pd.DataFrame({"RecordDate": [pd.Timestamp(ex_date)], "ExDate": [pd.Timestamp(ex_date)],
                         "PayableDate": [pd.Timestamp(pay_date)], "Distribution": [amount]})


def test_distribution_entitlement_survives_sale_on_ex_date():
    index = pd.bdate_range("2024-01-02", periods=6)
    assets = {"TQQQ": prices(index), "SGOV": prices(index)}
    targets = pd.DataFrame({"TQQQ": [0, 0, 1, 1, 1, 1], "SGOV": [1, 1, 0, 0, 0, 0]}, index=index)

    result, stats = run_sgov_strategy(assets, targets, distributions(), tqqq_fee=0, sgov_fee=0)

    assert result.positions.loc["2024-01-04", "SGOVShares"] == 0
    assert result.positions.loc["2024-01-04", "Receivable"] == pytest.approx(1000)
    assert result.positions.loc["2024-01-08", "Receivable"] == 0
    assert stats["gross_distributions"] == pytest.approx(1000)


def test_ex_date_buyer_does_not_receive_distribution():
    index = pd.bdate_range("2024-01-02", periods=6)
    assets = {"TQQQ": prices(index), "SGOV": prices(index)}
    targets = pd.DataFrame({"TQQQ": [1, 1, 0, 0, 0, 0], "SGOV": [0, 0, 1, 1, 1, 1]}, index=index)

    _, stats = run_sgov_strategy(assets, targets, distributions(), tqqq_fee=0, sgov_fee=0)

    assert stats["gross_distributions"] == 0


def test_delayed_entry_waits_fifteen_same_state_signals_and_does_not_rebalance_tqqq():
    signal_index = pd.bdate_range("2024-01-02", periods=20)
    signal = pd.Series([1.0] + [0.5] * 19, index=signal_index)
    execution = signal_index[1:]
    targets = build_execution_targets(signal, execution, "delayed_15_sessions")
    assets = {"TQQQ": prices(execution), "SGOV": prices(execution)}

    result, _ = run_sgov_strategy(assets, targets, distributions("2025-01-02", "2025-01-03"),
                                  tqqq_fee=0, sgov_fee=0)

    assert targets.SGOV.iloc[14] == 0
    assert targets.SGOV.iloc[15] == pytest.approx(0.5)
    assert len(result.trades.query("Asset == 'TQQQ'")) == 2


def test_high_band_half_enters_only_at_zero_and_persists_through_middle_band():
    signal_index = pd.bdate_range("2024-01-02", periods=6)
    signal = pd.Series([1.0, 0.5, 0.0, 0.5, 1.0, 1.0], index=signal_index)
    targets = build_execution_targets(signal, signal_index[1:], "high_band_half_then_hold")

    assert list(targets.SGOV) == [0.0, 0.0, 0.5, 0.5, 0.0]


def test_layered_lower_clock_survives_transition_to_high_band():
    signal_index = pd.bdate_range("2024-01-02", periods=32)
    signal = pd.Series([1.0] + [0.5] * 14 + [0.0] * 17, index=signal_index)
    targets = build_execution_targets(signal, signal_index[1:], "layered_15_sessions")

    # The 15th lower-layer session is the first >90% session, so only that layer matures.
    first_high_execution = signal_index[16]
    assert targets.loc[first_high_execution, "SGOV"] == pytest.approx(0.5)
    # The upper layer matures after its own 15 signal sessions.
    assert targets.loc[signal_index[30], "SGOV"] == pytest.approx(1.0)


def test_layered_layers_deactivate_at_their_own_boundaries():
    signal_index = pd.bdate_range("2024-01-02", periods=34)
    signal = pd.Series([0.0] * 16 + [0.5] * 2 + [1.0] * 16, index=signal_index)
    targets = build_execution_targets(signal, signal_index[1:], "layered_15_sessions")

    assert targets.loc[signal_index[17], "SGOV"] == pytest.approx(0.5)
    assert targets.loc[signal_index[19], "SGOV"] == 0.0


def test_active_addon_caps_matured_sgov_to_available_cash():
    signal_index = pd.bdate_range("2024-01-02", periods=20)
    core = pd.Series(0.0, index=signal_index)
    active = pd.Series(0.5, index=signal_index)
    active.iloc[-2:] = 1.0

    targets = build_execution_targets(
        core, signal_index[1:], "layered_15_sessions", tqqq_signal=active
    )

    assert targets.loc[signal_index[16], "SGOV"] == pytest.approx(0.5)
    assert targets.loc[signal_index[19], "SGOV"] == 0.0


def test_default_active_allocation_combines_tqqq_addon_and_layered_sgov(monkeypatch):
    index = pd.bdate_range("2024-01-02", periods=20)
    frame = prices(index)
    core = pd.Series(0.0, index=index)
    active = pd.Series(0.5, index=index)
    monkeypatch.setattr(
        "backtests.vo_sgov.build_active_vo_weights",
        lambda data: (frame, active, core),
    )

    _, allocation, _, state = build_active_vo_allocation(
        MarketData(ixic=frame, qqq=frame, tqqq=frame)
    )

    assert allocation.iloc[13].to_dict() == {"TQQQ": 0.5, "SGOV": 0.0, "Cash": 0.5}
    assert allocation.iloc[14].to_dict() == {"TQQQ": 0.5, "SGOV": 0.5, "Cash": 0.0}
    assert state.iloc[14]["SGOVCapacity"] == 1.0
