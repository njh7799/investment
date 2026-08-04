from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.send_daily_briefing import (
    Briefing,
    build_briefing,
    build_trade_plan,
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
    assert briefing.volatility == pytest.approx(expected)


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
    )

    message = format_briefing(briefing)

    assert message == """📊 2026.08.04 미국 시장 마감

• IXIC: 23,412.28pt (🔴 +1.12%)
• QQQ: $621.47 (⚪️ 0.00%)
• TQQQ: $57.82 (🔴 +4.08%)
• SPY: $689.21 (🔵 -0.26%)

⚡ VO 변동성: 24.6%
🎯 권장 비중: 주식 50% · 현금 50%

✅ 직전 비중과 동일합니다.
오늘은 매매할 필요가 없습니다."""


class FakeTossClient:
    def __init__(self, *, quantity="20", cash="2000"):
        self.quantity = quantity
        self.cash = cash

    def get_accounts(self):
        return [
            {
                "accountNo": "12345678901",
                "accountSeq": 7,
                "accountType": "BROKERAGE",
            }
        ]

    def get_holdings(self, account_seq, *, symbol=None):
        assert account_seq == 7
        assert symbol == "TQQQ"
        return {"items": [{"quantity": self.quantity}]}

    def get_buying_power(self, account_seq, currency):
        assert account_seq == 7
        assert currency == "USD"
        return {"currency": "USD", "cashBuyingPower": self.cash}


def test_trade_plan_uses_tqqq_and_usd_cash_to_compute_target_shares():
    changed = Briefing(
        market_date=pd.Timestamp("2026-08-04"),
        closes={symbol: 100.0 for symbol in ("IXIC", "QQQ", "TQQQ", "SPY")},
        changes={symbol: 0.01 for symbol in ("IXIC", "QQQ", "TQQQ", "SPY")},
        volatility=0.95,
        stock_weight=0.0,
        previous_stock_weight=0.5,
    )

    plan = build_trade_plan(FakeTossClient(), changed, 100.0)

    assert plan.side == "매도"
    assert plan.quantity == 20
    assert plan.current_quantity == 20
    assert plan.target_quantity == 0
    assert plan.account_mask == "••••8901"


def test_trade_plan_caps_buy_quantity_for_fee_and_message_masks_account():
    changed = Briefing(
        market_date=pd.Timestamp("2026-08-04"),
        closes={symbol: 100.0 for symbol in ("IXIC", "QQQ", "TQQQ", "SPY")},
        changes={symbol: 0.01 for symbol in ("IXIC", "QQQ", "TQQQ", "SPY")},
        volatility=0.50,
        stock_weight=1.0,
        previous_stock_weight=0.5,
    )

    plan = build_trade_plan(FakeTossClient(quantity="10", cash="1000"), changed, 100.0)
    message = format_briefing(changed, plan)

    assert plan.side == "매수"
    assert plan.target_quantity == 20
    assert plan.quantity == 9
    assert "••••8901" in message
    assert "매수 9주" in message
    assert "12345678901" not in message
