from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.send_daily_briefing import (
    Briefing,
    build_briefing,
    format_briefing,
    vo_weight,
)


def frame(closes: list[float]) -> pd.DataFrame:
    index = pd.bdate_range("2026-01-02", periods=len(closes))
    return pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes},
        index=index,
        dtype=float,
    )


def test_vo_weight_includes_thresholds_in_lower_volatility_bands():
    assert vo_weight(0.60) == 1.0
    assert vo_weight(np.nextafter(0.60, 1.0)) == 0.5
    assert vo_weight(0.90) == 0.5
    assert vo_weight(np.nextafter(0.90, 1.0)) == 0.0


def test_build_briefing_uses_latest_close_and_previous_close():
    closes = [100.0]
    for change in np.linspace(-0.04, 0.04, 31):
        closes.append(closes[-1] * (1.0 + change))
    market = frame(closes)
    frames = {symbol: market.copy() for symbol in ("IXIC", "QQQ", "TQQQ", "SPY")}

    briefing = build_briefing(frames)

    assert briefing.market_date == market.index[-1]
    assert briefing.closes["TQQQ"] == pytest.approx(closes[-1])
    assert briefing.changes["TQQQ"] == pytest.approx(0.04)
    expected = pd.Series(closes).pct_change().rolling(30).std(ddof=1).iloc[-1] * np.sqrt(252)
    previous = pd.Series(closes).pct_change().rolling(30).std(ddof=1).iloc[-2] * np.sqrt(252)
    assert briefing.volatility == pytest.approx(expected)
    assert briefing.volatility_change == pytest.approx(expected - previous)


def test_trade_warning_is_shown_only_when_target_state_changes():
    changed = Briefing(
        market_date=pd.Timestamp("2026-08-04"),
        closes={"IXIC": 23412.28, "QQQ": 621.47, "TQQQ": 57.82, "SPY": 689.21},
        changes={"IXIC": 0.0112, "QQQ": 0.0135, "TQQQ": 0.0408, "SPY": -0.0026},
        volatility=0.95,
        stock_weight=0.0,
        previous_stock_weight=0.5,
    )
    unchanged = Briefing(
        market_date=changed.market_date,
        closes=changed.closes,
        changes=changed.changes,
        volatility=0.70,
        stock_weight=0.5,
        previous_stock_weight=0.5,
    )

    assert "TQQQ 매도" in format_briefing(changed)
    assert "비중이 변경되어 매매가 필요합니다" in format_briefing(changed)
    assert "매매할 필요가 없습니다" in format_briefing(unchanged)


def test_market_summary_shows_close_and_colored_change():
    briefing = Briefing(
        market_date=pd.Timestamp("2026-08-04"),
        closes={"IXIC": 23412.28, "QQQ": 621.47, "TQQQ": 57.82, "SPY": 689.21},
        changes={"IXIC": 0.0112, "QQQ": 0.0, "TQQQ": 0.0408, "SPY": -0.0026},
        volatility=0.246,
        stock_weight=0.5,
        previous_stock_weight=0.5,
        volatility_change=-0.005,
    )

    message = format_briefing(briefing)

    assert message == """📊 2026.08.04 미국 시장 마감

• IXIC: 23,412.28pt (🔴 +1.12%)
• QQQ: $621.47 (⚪️ 0.00%)
• TQQQ: $57.82 (🔴 +4.08%)
• SPY: $689.21 (🔵 -0.26%)

⚡ VO 변동성: 24.6% (▼0.5%p)
🎯 권장 비중: 주식 50% · 현금 50%

✅ 직전 비중과 동일합니다.
오늘은 매매할 필요가 없습니다."""
