import numpy as np
import pandas as pd

from backtests.core import run_weight_strategy
from backtests.vo_rebound import (
    fill_stopped_addon_weights,
    online_low_fill_stopped_weights,
    variant_specs,
)


def series(values):
    return pd.Series(values, index=pd.bdate_range("2026-01-02", periods=len(values)), dtype=float)


def prices(opens, closes=None):
    opens = series(opens)
    closes = opens if closes is None else series(closes)
    return pd.DataFrame({"Open": opens, "High": np.maximum(opens, closes), "Low": np.minimum(opens, closes), "Close": closes})


def test_vo_rebound_grid_matches_corrected_preregistration():
    specs = variant_specs()
    assert len(specs) == 11
    assert len({spec.name for spec in specs}) == 11
    assert "sma_upcross_5_20" in {spec.name for spec in specs}


def test_next_open_is_entry_anchor_and_entry_day_close_can_stop():
    base = series([0.5, 0.5, 0.5, 0.5, 0.5])
    frame = prices([100, 101, 110, 90, 95], [100, 101, 105, 89, 95])
    signal = pd.Series([False, True, False, False, False], index=base.index)
    weights, anchor = fill_stopped_addon_weights(base, frame, signal)
    assert weights.tolist() == [0.5, 1.0, 0.5, 0.5, 0.5]
    assert anchor.isna().all()  # E=110 was breached by that session's close and then cleared.
    result = run_weight_strategy(frame, weights)
    assert result.trades.iloc[1].Price == 110
    assert result.trades.iloc[2].Price == 90


def test_equal_entry_close_holds_but_strictly_lower_close_exits_next_open():
    base = series([0.5] * 5)
    frame = prices([100, 110, 111, 90, 95], [100, 110, 109, 90, 95])
    signal = pd.Series([True, False, False, False, False], index=base.index)
    weights, anchor = fill_stopped_addon_weights(base, frame, signal)
    assert weights.tolist() == [1.0, 1.0, 0.5, 0.5, 0.5]
    assert anchor.iloc[1] == 110


def test_stop_requires_false_then_fresh_true_signal():
    base = series([0.5] * 7)
    frame = prices([100, 110, 111, 90, 91, 92, 93], [100, 109, 108, 90, 91, 92, 93])
    signal = pd.Series([True, True, True, True, False, True, False], index=base.index)
    weights, _ = fill_stopped_addon_weights(base, frame, signal)
    assert weights.tolist() == [1.0, 0.5, 0.5, 0.5, 0.5, 1.0, 1.0]


def test_full_vo_resets_entry_anchor_and_pending_state():
    base = series([0.5, 0.5, 1.0, 0.5])
    frame = prices([100, 110, 120, 130])
    signal = pd.Series([True, False, True, False], index=base.index)
    weights, anchor = fill_stopped_addon_weights(base, frame, signal)
    assert weights.tolist() == [1.0, 1.0, 1.0, 0.5]
    assert pd.isna(anchor.iloc[2])


def test_online_low_restarts_causal_search_after_fill_stop():
    base = series([0.5] * 8)
    frame = prices([100, 90, 100, 95, 80, 88, 87, 96], [100, 90, 99, 79, 80, 88, 87, 96])
    weights, _ = online_low_fill_stopped_weights(base, frame, 0.10)
    assert weights.tolist() == [0.5, 0.5, 1.0, 0.5, 0.5, 1.0, 1.0, 1.0]


def test_future_change_does_not_change_past_targets():
    base = series([0.5] * 5)
    original = prices([100, 110, 111, 112, 113])
    revised = original.copy()
    revised.iloc[-1, revised.columns.get_loc("Close")] = 1
    signal = pd.Series([True, False, False, False, False], index=base.index)
    a, _ = fill_stopped_addon_weights(base, original, signal)
    b, _ = fill_stopped_addon_weights(base, revised, signal)
    pd.testing.assert_series_equal(a.iloc[:-1], b.iloc[:-1])
