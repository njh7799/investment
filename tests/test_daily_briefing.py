from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.send_daily_briefing import (
    Briefing,
    HistoricalMove,
    _drawdown_episodes,
    build_briefing,
    extremeness_level,
    format_briefing,
    historical_move,
    stress_context,
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
    expected_move = historical_move(market["Close"], 5)
    assert briefing.historical_context == expected_move
    assert briefing.historical_context.horizon == 5


def test_historical_move_uses_directional_tail_including_latest_window():
    close = pd.Series([100.0, 90.0, 99.0, 79.2, 95.04])

    falling = historical_move(close.iloc[:-1], 1)
    rising = historical_move(close, 1)

    assert falling.return_value == pytest.approx(-0.20)
    assert falling.tail_probability == pytest.approx(1 / 3)
    assert falling.extremeness_score == pytest.approx(200 / 3)
    assert rising.return_value == pytest.approx(0.20)
    assert rising.tail_probability == pytest.approx(1 / 4)
    assert rising.extremeness_score == pytest.approx(75.0)


def test_drawdown_episodes_keep_peak_trough_recovery_and_open_duration():
    index = pd.to_datetime(
        ["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
    )
    equity = pd.Series([100.0, 80.0, 100.0, 90.0, 95.0], index=index)

    episodes = _drawdown_episodes(equity)

    assert len(episodes) == 2
    assert episodes.iloc[0]["mdd"] == pytest.approx(-0.20)
    assert episodes.iloc[0]["recovery_date"] == pd.Timestamp("2026-01-05")
    assert episodes.iloc[0]["underwater_days"] == 4
    assert episodes.iloc[1]["mdd"] == pytest.approx(-0.10)
    assert pd.isna(episodes.iloc[1]["recovery_date"])
    assert episodes.iloc[1]["underwater_days"] == 2


def test_stress_context_uses_prelaunch_synthetic_history():
    closes = [100.0, 80.0, 100.0, *np.linspace(101.0, 130.0, 37)]
    market = frame(closes)
    market.index = pd.bdate_range("1999-03-10", periods=len(closes))
    frames = {symbol: market.copy() for symbol in ("IXIC", "QQQ", "TQQQ", "SPY")}

    context = stress_context(frames)

    assert context.mdd_qualifying_episodes >= 1
    assert context.duration_qualifying_episodes == 0
    assert context.historical_worst_mdd <= -0.19
    assert context.episode_start < pd.Timestamp("2010-02-11")


@pytest.mark.parametrize(
    ("score", "label"),
    [
        (99.0, "extreme"),
        (98.999, "rare"),
        (95.0, "rare"),
        (94.999, "notable"),
        (80.0, "notable"),
        (79.999, "normal"),
    ],
)
def test_extremeness_colors_have_fixed_inclusive_boundaries(score, label):
    assert extremeness_level(score) == label


@pytest.mark.parametrize("return_value", [-0.20, 0.20])
def test_historical_context_uses_one_extremeness_scale_for_both_directions(
    return_value,
):
    state = Briefing(
        market_date=pd.Timestamp("2026-08-04"),
        closes={"IXIC": 23412.28, "QQQ": 621.47, "TQQQ": 57.82, "SPY": 689.21},
        changes={"IXIC": 0.0112, "QQQ": 0.0135, "TQQQ": 0.0408, "SPY": -0.0026},
        volatility=0.70,
        stock_weight=0.5,
        previous_stock_weight=0.5,
        historical_context=HistoricalMove(
            horizon=5,
            return_value=return_value,
            tail_probability=0.02,
            observations=100,
        ),
    )

    message = format_briefing(state)

    assert "극단도 98.0" in message
    assert "상위" not in message
    assert "하위" not in message


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
🧩 활성 addon: 5/20 상향돌파 · 구간당 1회
🎯 최종 권장 비중: 주식 50% · 현금 50%

✅ 직전 비중과 동일합니다.
오늘은 매매할 필요가 없습니다."""
