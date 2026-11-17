import pandas as pd
import pytest

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
