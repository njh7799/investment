import pandas as pd
import pytest

from backtests.vo_consecutive import consecutive_up, cumulative_return, variant_specs


def series(values):
    return pd.Series(values, index=pd.bdate_range("2026-01-02", periods=len(values)), dtype=float)


def test_consecutive_grid_matches_preregistration():
    specs = variant_specs()
    assert len(specs) == 14
    assert len({spec.name for spec in specs}) == 14
    assert sum(spec.family == "consecutive_up_fill_stop" for spec in specs) == 6
    assert sum(spec.family == "consecutive_up_return_fill_stop" for spec in specs) == 8


def test_consecutive_up_requires_exact_positive_run_and_equal_breaks_it():
    close = series([100, 101, 102, 102, 103, 104])
    signal = consecutive_up(close, 2)
    assert list(signal) == [False, False, True, False, False, True]


def test_cumulative_return_uses_close_t_minus_n_and_includes_exact_boundary():
    close = series([100, 101, 102, 103])
    result = cumulative_return(close, 3)
    assert result.iloc[-1] == pytest.approx(0.03)
    assert bool(result.iloc[-1] >= 0.03)


def test_cross_asset_wiring_specs_are_distinct():
    specs = {spec.name: spec for spec in variant_specs()}
    assert (specs["combo_qt_3_6"].streak_asset, specs["combo_qt_3_6"].return_asset) == ("q", "t")
    assert (specs["combo_tq_3_2"].streak_asset, specs["combo_tq_3_2"].return_asset) == ("t", "q")


def test_missing_close_is_rejected_instead_of_forward_filled():
    close = series([100, 101, 102])
    close.iloc[1] = float("nan")
    with pytest.raises(ValueError, match="missing"):
        consecutive_up(close, 2)
    with pytest.raises(ValueError, match="missing"):
        cumulative_return(close, 2)


def test_future_price_change_does_not_change_past_streak():
    original = series([100, 101, 102, 103, 104])
    revised = original.copy()
    revised.iloc[-1] = 50
    pd.testing.assert_series_equal(
        consecutive_up(original, 3).iloc[:-1],
        consecutive_up(revised, 3).iloc[:-1],
    )
