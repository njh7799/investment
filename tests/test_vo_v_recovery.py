import pandas as pd

from backtests.vo_v_recovery import controlled_addon_weights, variant_specs


def _series(values):
    return pd.Series(values, index=pd.bdate_range("2026-01-02", periods=len(values)), dtype=float)


def _prices(opens, closes):
    o, c = _series(opens), _series(closes)
    return pd.DataFrame({"Open": o, "High": o.combine(c, max), "Low": o.combine(c, min), "Close": c})


def test_registered_grid_has_24_unique_variants():
    specs = variant_specs()
    assert len(specs) == 24
    assert len({s.name for s in specs}) == 24
    assert {s.policy for s in specs} == {"one_attempt", "cooldown", "timebox", "ratchet", "staged"}


def test_one_attempt_does_not_reenter_before_episode_reset():
    base = _series([0.5] * 6 + [1.0, 0.5, 0.5, 0.5])
    prices = _prices([100, 110, 90, 95, 100, 105, 110, 100, 105, 106], [100, 109, 90, 95, 100, 105, 110, 100, 105, 106])
    signal = pd.Series([True, False, True, False, True, False, False, False, True, False], index=base.index)
    w = controlled_addon_weights(base, prices, signal, rearm_level=signal, policy="one_attempt", parameter=None)
    assert w.tolist() == [1.0, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0, 0.5, 1.0, 1.0]


def test_staged_policy_uses_quarter_then_half_addon():
    base = _series([0.0, 0.0, 0.0, 0.0])
    prices = _prices([100, 100, 106, 107], [100, 100, 106, 107])
    signal = pd.Series([True, False, False, False], index=base.index)
    w = controlled_addon_weights(base, prices, signal, rearm_level=signal, policy="staged", parameter=0.05)
    assert w.tolist() == [0.25, 0.25, 0.5, 0.5]


def test_timebox_exits_after_registered_active_sessions():
    base = _series([0.5] * 5)
    prices = _prices([100, 100, 101, 102, 103], [100, 100, 101, 102, 103])
    signal = pd.Series([True, False, False, False, False], index=base.index)
    w = controlled_addon_weights(base, prices, signal, rearm_level=signal, policy="timebox", parameter=2)
    assert w.tolist() == [1.0, 1.0, 0.5, 0.5, 0.5]
