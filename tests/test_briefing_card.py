from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pandas as pd
from PIL import Image, ImageColor, ImageFont

from scripts.render_briefing_card import (
    ALLOCATION_BAR_HEIGHT,
    ALLOCATION_BAR_WIDTH,
    ALLOCATION_BAR_X,
    ALLOCATION_ICON_BOX,
    ALLOCATION_LABEL_FONT_SIZE,
    ALLOCATION_PANEL,
    ALLOCATION_ROW_Y,
    ALLOCATION_TITLE_POSITION,
    ALLOCATION_VALUE_FONT_SIZE,
    CARD_SIZE,
    allocation_display_values,
    render_briefing_card,
    volatility_gauge_angle,
    volatility_state,
)
from scripts.send_daily_briefing import (
    Briefing,
    TradePlan,
    send_to_kakao,
    upload_card_to_kakao,
)


def briefing(
    *,
    volatility: float,
    stock_weight: float,
    previous_stock_weight: float,
    volatility_change: float = 0.0,
) -> Briefing:
    return Briefing(
        market_date=pd.Timestamp("2026-08-06"),
        closes={"IXIC": 23412.28, "QQQ": 621.47, "TQQQ": 57.82, "SPY": 689.21},
        changes={"IXIC": 0.0112, "QQQ": 0.0135, "TQQQ": 0.0408, "SPY": -0.0026},
        volatility=volatility,
        stock_weight=stock_weight,
        previous_stock_weight=previous_stock_weight,
        volatility_change=volatility_change,
    )


def test_volatility_state_labels_match_vo_thresholds():
    assert volatility_state(0.60)[0] == "저변동"
    assert volatility_state(0.61)[0] == "중변동"
    assert volatility_state(0.90)[0] == "중변동"
    assert volatility_state(0.91)[0] == "고변동"


def test_volatility_gauge_marks_thresholds_and_clamps_extremes():
    assert volatility_gauge_angle(-0.1) == 180.0
    assert volatility_gauge_angle(0.60) == 270.0
    assert volatility_gauge_angle(0.90) == 315.0
    assert volatility_gauge_angle(1.20) == 360.0
    assert volatility_gauge_angle(1.50) == 360.0


def test_allocation_rows_keep_stock_then_cash_semantics_when_state_changes():
    unchanged = briefing(volatility=0.246, stock_weight=1.0, previous_stock_weight=1.0)
    changed = briefing(volatility=0.246, stock_weight=1.0, previous_stock_weight=0.5)

    assert allocation_display_values(unchanged) == ("100%", "0%")
    assert allocation_display_values(changed) == ("50% → 100%", "50% → 0%")


def test_all_card_states_share_one_allocation_layout(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "scripts.render_briefing_card._font",
        lambda size, **_: ImageFont.load_default(size=size),
    )
    states = {
        "low": (briefing(volatility=0.246, stock_weight=1.0, previous_stock_weight=1.0), None),
        "high": (briefing(volatility=0.952, stock_weight=0.0, previous_stock_weight=0.0), None),
        "trade": (
            briefing(volatility=0.246, stock_weight=1.0, previous_stock_weight=0.5),
            TradePlan(
                account_mask="••••8901",
                side="매수",
                quantity=12,
                current_quantity=10,
                target_quantity=22,
                reference_price=Decimal("57.82"),
                cash_buying_power=Decimal("1200"),
            ),
        ),
    }
    rendered: dict[str, Image.Image] = {}
    for name, (state, plan) in states.items():
        path = tmp_path / f"{name}.png"
        render_briefing_card(state, path, plan)
        rendered[name] = Image.open(path).copy()
        assert rendered[name].size == CARD_SIZE
        assert path.stat().st_size < 5 * 1024 * 1024

    assert ALLOCATION_PANEL == (60, 695, 740, 850)
    assert ALLOCATION_ICON_BOX == (86, 716, 126, 756)
    assert ALLOCATION_TITLE_POSITION == (142, 712)
    assert ALLOCATION_ROW_Y == (776, 828)
    assert (ALLOCATION_BAR_X, ALLOCATION_BAR_WIDTH, ALLOCATION_BAR_HEIGHT) == (420, 290, 18)
    assert ALLOCATION_LABEL_FONT_SIZE == ALLOCATION_VALUE_FONT_SIZE == 25

    fixed_header = (75, 705, 310, 760)
    assert rendered["low"].crop(fixed_header).tobytes() == rendered["high"].crop(
        fixed_header
    ).tobytes()
    assert rendered["low"].crop(fixed_header).tobytes() == rendered["trade"].crop(
        fixed_header
    ).tobytes()


def test_allocation_bars_use_color_only_for_increases(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "scripts.render_briefing_card._font",
        lambda size, **_: ImageFont.load_default(size=size),
    )
    states = {
        "unchanged": briefing(
            volatility=0.763, stock_weight=0.5, previous_stock_weight=0.5
        ),
        "stock_increase": briefing(
            volatility=0.763, stock_weight=1.0, previous_stock_weight=0.5
        ),
        "cash_increase": briefing(
            volatility=0.763, stock_weight=0.0, previous_stock_weight=0.5
        ),
    }
    rendered = {}
    for name, state in states.items():
        path = tmp_path / f"{name}.png"
        render_briefing_card(state, path)
        rendered[name] = Image.open(path).convert("RGB")

    quarter = ALLOCATION_BAR_X + ALLOCATION_BAR_WIDTH // 4
    three_quarters = ALLOCATION_BAR_X + ALLOCATION_BAR_WIDTH * 3 // 4
    stock_y, cash_y = ALLOCATION_ROW_Y
    gray = ImageColor.getrgb("#8b95a1")
    empty = ImageColor.getrgb("#edf0f3")
    red = ImageColor.getrgb("#f04452")
    blue = ImageColor.getrgb("#3182f6")

    assert rendered["unchanged"].getpixel((quarter, stock_y)) == gray
    assert rendered["unchanged"].getpixel((quarter, cash_y)) == gray
    assert rendered["unchanged"].getpixel((three_quarters, stock_y)) == empty
    assert rendered["unchanged"].getpixel((three_quarters, cash_y)) == empty

    assert rendered["stock_increase"].getpixel((quarter, stock_y)) == gray
    assert rendered["stock_increase"].getpixel((three_quarters, stock_y)) == red
    assert rendered["stock_increase"].getpixel((quarter, cash_y)) == empty

    assert rendered["cash_increase"].getpixel((quarter, stock_y)) == empty
    assert rendered["cash_increase"].getpixel((quarter, cash_y)) == gray
    assert rendered["cash_increase"].getpixel((three_quarters, cash_y)) == blue


class FakeResponse:
    def __init__(self, body: dict[str, object]):
        self.body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.body


def test_kakao_upload_uses_app_key_and_returns_temporary_image_url(
    tmp_path: Path, monkeypatch
):
    image_path = tmp_path / "briefing.png"
    Image.new("RGB", (200, 200), "white").save(image_path)
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse(
            {"infos": {"original": {"url": "https://example.kakao/briefing.png"}}}
        )

    monkeypatch.setattr("scripts.send_daily_briefing.requests.post", fake_post)

    result = upload_card_to_kakao("rest-key", image_path)

    assert result == "https://example.kakao/briefing.png"
    assert captured["headers"] == {"Authorization": "KakaoAK rest-key"}
    assert captured["files"]["file"][2] == "image/png"


def test_kakao_message_uses_feed_template_with_card(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse({"result_code": 0})

    monkeypatch.setattr("scripts.send_daily_briefing.requests.post", fake_post)
    state = briefing(volatility=0.246, stock_weight=1.0, previous_stock_weight=1.0)

    send_to_kakao("access-token", state, "https://example.kakao/briefing.png")

    template = json.loads(captured["data"]["template_object"])
    assert template["object_type"] == "feed"
    assert template["content"]["image_url"] == "https://example.kakao/briefing.png"
    assert template["content"]["image_width"] == 800
    assert template["content"]["image_height"] == 1067
    assert "description" not in template["content"]
