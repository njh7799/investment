import numpy as np
import pandas as pd

from backtests.vo_buffers import (
    minimum_holding_weights,
    recovery_confirmation_weights,
    recovery_hysteresis_weights,
    smoothed_recovery_weights,
    variant_specs,
)


def series(values):
    return pd.Series(values, index=pd.bdate_range("2026-01-02", periods=len(values)))


def test_vo_buffer_grid_matches_preregistration():
    specs = variant_specs()
    assert len(specs) == 15
    assert len({spec.name for spec in specs}) == len(specs)


def test_hysteresis_cuts_immediately_and_recovers_at_exact_lower_boundaries():
    volatility = series([0.50, 0.6001, 0.58, 0.9001, 0.88, 0.58])
    assert list(recovery_hysteresis_weights(volatility, 0.02)) == [1.0, 0.5, 1.0, 0.0, 0.5, 1.0]


def test_confirmation_requires_consecutive_same_target_and_resets_on_cut():
    base = series([1.0, 0.5, 1.0, 1.0, 0.5, 0.0, 0.5, 0.5])
    assert list(recovery_confirmation_weights(base, 2)) == [1.0, 0.5, 0.5, 1.0, 0.5, 0.0, 0.0, 0.5]


def test_minimum_holding_counts_subsequent_signal_sessions_and_restarts_on_cut():
    base = series([1.0, 0.5, 1.0, 1.0, 0.0, 1.0, 1.0])
    assert list(minimum_holding_weights(base, 2)) == [1.0, 0.5, 0.5, 1.0, 0.0, 0.0, 1.0]


def test_smoothed_recovery_uses_default_during_warmup_and_never_delays_a_cut():
    base = series([1.0, 0.5, 1.0, 0.0, 0.5])
    volatility = series([0.50, 0.70, 0.50, 0.95, 0.80])
    result = smoothed_recovery_weights(base, volatility, 3)
    assert list(result) == [1.0, 0.5, 1.0, 0.0, 0.5]


def test_buffer_outputs_do_not_change_when_only_a_future_value_changes():
    original = series([0.50, 0.61, 0.59, 0.58, 0.57])
    revised = original.copy()
    revised.iloc[-1] = 1.20
    pd.testing.assert_series_equal(
        recovery_hysteresis_weights(original, 0.02).iloc[:-1],
        recovery_hysteresis_weights(revised, 0.02).iloc[:-1],
    )
