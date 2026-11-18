from __future__ import annotations

import numpy as np
import pandas as pd

from .core import MarketData
from .vo_v_recovery import build_active_vo_weights


SGOV_CONFIRMATION_SESSIONS = 15


def layered_sgov_state(
    core_weights: pd.Series,
    confirmation_sessions: int = SGOV_CONFIRMATION_SESSIONS,
) -> pd.DataFrame:
    """Track independent 50% SGOV eligibility at the 60% and 90% VO boundaries."""
    if confirmation_sessions <= 0:
        raise ValueError("confirmation_sessions must be positive")
    lower_sessions = upper_sessions = 0
    rows: list[dict[str, float | int | bool]] = []
    for risk_weight in core_weights.astype(float):
        lower_sessions = lower_sessions + 1 if risk_weight < 1.0 - 1e-12 else 0
        upper_sessions = upper_sessions + 1 if np.isclose(risk_weight, 0.0) else 0
        lower_matured = lower_sessions >= confirmation_sessions
        upper_matured = upper_sessions >= confirmation_sessions
        rows.append(
            {
                "LowerSessions": lower_sessions,
                "UpperSessions": upper_sessions,
                "LowerMatured": lower_matured,
                "UpperMatured": upper_matured,
                "SGOVCapacity": 0.5 * (int(lower_matured) + int(upper_matured)),
            }
        )
    return pd.DataFrame(rows, index=core_weights.index)


def build_active_vo_allocation(
    data: MarketData,
    confirmation_sessions: int = SGOV_CONFIRMATION_SESSIONS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.DataFrame]:
    """Return current VO+5/20 targets with the layered SGOV cash-sleeve addon on."""
    prices, active_tqqq, core_tqqq = build_active_vo_weights(data)
    state = layered_sgov_state(core_tqqq, confirmation_sessions)
    available_cash = 1.0 - active_tqqq
    sgov = pd.Series(
        np.minimum(state["SGOVCapacity"].to_numpy(), available_cash.to_numpy()),
        index=active_tqqq.index,
        dtype=float,
    )
    allocation = pd.DataFrame(
        {
            "TQQQ": active_tqqq,
            "SGOV": sgov,
            "Cash": available_cash - sgov,
        },
        index=active_tqqq.index,
    )
    if not np.allclose(allocation.sum(axis=1), 1.0):
        raise ValueError("active VO allocation does not sum to 100%")
    return prices, allocation, core_tqqq, state
