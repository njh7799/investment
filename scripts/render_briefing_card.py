#!/usr/bin/env python3
"""Render the daily market and VO briefing as a deterministic PNG card."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageDraw, ImageFont


CARD_SIZE = (800, 1067)
CARD_BACKGROUND = "#f5f6f8"
CARD_WHITE = "#ffffff"
TEXT = "#191f28"
MUTED = "#6b7684"
LINE = "#e5e8eb"
UP = "#f04452"
DOWN = "#3182f6"
NEUTRAL = "#8b95a1"

ALLOCATION_PANEL = (60, 695, 740, 850)
ALLOCATION_ICON_BOX = (86, 716, 126, 756)
ALLOCATION_TITLE_POSITION = (142, 712)
ALLOCATION_ROW_Y = (776, 828)
ALLOCATION_BAR_X = 420
ALLOCATION_BAR_WIDTH = 290
ALLOCATION_BAR_HEIGHT = 18
ALLOCATION_LABEL_FONT_SIZE = 25
ALLOCATION_VALUE_FONT_SIZE = 25


class BriefingLike(Protocol):
    market_date: object
    closes: dict[str, float]
    changes: dict[str, float]
    volatility: float
    volatility_change: float
    stock_weight: float
    previous_stock_weight: float

    @property
    def needs_trade(self) -> bool: ...


class TradePlanLike(Protocol):
    side: str
    quantity: int
    current_quantity: int
    target_quantity: int


def _font_path(bold: bool) -> str:
    configured = os.environ.get("BRIEFING_FONT_PATH")
    if configured and Path(configured).is_file():
        return configured

    names = (
        [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        ]
        if bold
        else [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/System/Library/Fonts/Supplemental/NotoSansGothic-Regular.ttf",
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        ]
    )
    for name in names:
        if Path(name).is_file():
            return name
    raise RuntimeError(
        "Korean font not found; install fonts-noto-cjk or set BRIEFING_FONT_PATH"
    )


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_font_path(bold), size=size)


def volatility_state(volatility: float) -> tuple[str, str, str]:
    if volatility <= 0.60:
        return "저변동", "#e8f0fa", "#28527a"
    if volatility <= 0.90:
        return "중변동", "#fff2d6", "#ad6800"
    return "고변동", "#ffebee", "#c62828"


def volatility_gauge_angle(volatility: float) -> float:
    """Map 0-120% annualized volatility to a 180-degree gauge."""
    return 180.0 + min(max(volatility, 0.0), 1.20) / 1.20 * 180.0


def allocation_display_values(briefing: BriefingLike) -> tuple[str, str]:
    stock = int(round(briefing.stock_weight * 100))
    cash = 100 - stock
    if not briefing.needs_trade:
        return f"{stock}%", f"{cash}%"
    previous_stock = int(round(briefing.previous_stock_weight * 100))
    previous_cash = 100 - previous_stock
    return f"{previous_stock}% → {stock}%", f"{previous_cash}% → {cash}%"


def _rounded_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: str = CARD_WHITE,
    outline: str = LINE,
    radius: int = 22,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1)


def _calendar_icon(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.rounded_rectangle((x, y + 8, x + 42, y + 46), radius=7, outline=MUTED, width=4)
    draw.line((x, y + 19, x + 42, y + 19), fill=MUTED, width=3)
    draw.line((x + 11, y + 2, x + 11, y + 13), fill=MUTED, width=4)
    draw.line((x + 31, y + 2, x + 31, y + 13), fill=MUTED, width=4)
    for dx in (12, 22, 32):
        for dy in (29, 38):
            draw.ellipse((x + dx - 2, y + dy - 2, x + dx + 2, y + dy + 2), fill=MUTED)


def _vo_icon(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.rounded_rectangle((x, y, x + 42, y + 42), radius=12, fill="#707985")
    draw.line((x + 8, y + 29, x + 17, y + 20, x + 24, y + 26, x + 34, y + 13), fill="white", width=4)
    draw.polygon(((x + 29, y + 13), (x + 35, y + 12), (x + 34, y + 19)), fill="white")


def _volatility_gauge(draw: ImageDraw.ImageDraw, volatility: float) -> None:
    center_x, center_y, radius = 650, 645, 55
    box = (
        center_x - radius,
        center_y - radius,
        center_x + radius,
        center_y + radius,
    )
    for start, end, color in (
        (180, 270, "#6aa9f4"),
        (270, 315, "#f5b544"),
        (315, 360, "#ef5b67"),
    ):
        draw.arc(box, start=start, end=end, fill=color, width=12)

    for threshold, label in ((0.60, "60"), (0.90, "90")):
        angle = math.radians(volatility_gauge_angle(threshold))
        inner = radius - 10
        outer = radius + 3
        draw.line(
            (
                center_x + inner * math.cos(angle),
                center_y + inner * math.sin(angle),
                center_x + outer * math.cos(angle),
                center_y + outer * math.sin(angle),
            ),
            fill=CARD_WHITE,
            width=3,
        )
        label_radius = radius + 13
        draw.text(
            (
                center_x + label_radius * math.cos(angle),
                center_y + label_radius * math.sin(angle),
            ),
            label,
            font=_font(13, bold=True),
            fill=MUTED,
            anchor="mm",
        )

    needle_angle = math.radians(volatility_gauge_angle(volatility))
    needle_length = radius - 16
    draw.line(
        (
            center_x,
            center_y,
            center_x + needle_length * math.cos(needle_angle),
            center_y + needle_length * math.sin(needle_angle),
        ),
        fill=TEXT,
        width=4,
    )
    draw.ellipse(
        (center_x - 6, center_y - 6, center_x + 6, center_y + 6), fill=TEXT
    )
    label, _, foreground = volatility_state(volatility)
    draw.text(
        (center_x, 662),
        label,
        font=_font(16, bold=True),
        fill=foreground,
        anchor="mm",
    )


def _allocation_icon(draw: ImageDraw.ImageDraw) -> None:
    x1, y1, x2, y2 = ALLOCATION_ICON_BOX
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    draw.ellipse((x1, y1, x2, y2), fill="#707985")
    draw.pieslice((x1 + 5, y1 + 5, x2 - 5, y2 - 5), 270, 360, fill=CARD_WHITE)
    draw.line((cx, y1 + 3, cx, cy), fill=CARD_WHITE, width=3)
    draw.line((cx, cy, x2 - 3, cy), fill=CARD_WHITE, width=3)


def _status_icon(draw: ImageDraw.ImageDraw, *, trade: bool, side: str | None) -> None:
    color = UP if side != "매도" else DOWN
    if trade:
        draw.ellipse((82, 878, 148, 944), fill=color)
        draw.line((115, 893, 115, 921), fill="white", width=6)
        draw.ellipse((112, 928, 118, 934), fill="white")
    else:
        draw.ellipse((82, 900, 148, 966), fill="#25b45b")
        draw.line((99, 933, 111, 945, 132, 920), fill="white", width=6)


def _draw_market_row(
    draw: ImageDraw.ImageDraw,
    symbol: str,
    close: float,
    change: float,
    y: int,
) -> None:
    color = UP if change > 0 else DOWN if change < 0 else NEUTRAL
    arrow = "▲" if change > 0 else "▼" if change < 0 else "―"
    price = f"{close:,.2f}pt" if symbol == "IXIC" else f"${close:,.2f}"
    change_text = f"{change:+.2%}" if change != 0 else "0.00%"
    draw.text((80, y), symbol, font=_font(37, bold=True), fill=color, anchor="lm")
    draw.text((510, y), price, font=_font(33, bold=True), fill=color, anchor="rm")
    draw.text((735, y), f"{arrow} {change_text}", font=_font(29, bold=True), fill=color, anchor="rm")
    draw.line((62, y + 54, 738, y + 54), fill=LINE, width=1)


def _draw_vo_panel(draw: ImageDraw.ImageDraw, briefing: BriefingLike) -> None:
    _rounded_panel(draw, (60, 565, 740, 675))
    _vo_icon(draw, 88, 599)
    draw.text((145, 620), "VO 변동성", font=_font(30, bold=True), fill=TEXT, anchor="lm")
    draw.text((430, 620), f"{briefing.volatility:.1%}", font=_font(37, bold=True), fill=TEXT, anchor="rm")
    change = briefing.volatility_change
    change_color = UP if change > 0 else DOWN if change < 0 else NEUTRAL
    change_arrow = "▲" if change > 0 else "▼" if change < 0 else "―"
    draw.text(
        (445, 620),
        f"{change_arrow}{abs(change):.1%}p",
        font=_font(27, bold=True),
        fill=change_color,
        anchor="lm",
    )
    _volatility_gauge(draw, briefing.volatility)


def _draw_allocation_panel(draw: ImageDraw.ImageDraw, briefing: BriefingLike) -> None:
    _rounded_panel(draw, ALLOCATION_PANEL)
    _allocation_icon(draw)
    draw.text(
        ALLOCATION_TITLE_POSITION,
        "권장 비중",
        font=_font(29, bold=True),
        fill=TEXT,
        anchor="la",
    )
    if briefing.needs_trade:
        draw.text((710, 729), "직전 → 현재", font=_font(17), fill=MUTED, anchor="ra")

    values = allocation_display_values(briefing)
    current = (briefing.stock_weight, 1.0 - briefing.stock_weight)
    previous = (briefing.previous_stock_weight, 1.0 - briefing.previous_stock_weight)
    increase_colors = (UP, DOWN)
    for index, (label, value, y) in enumerate(zip(("주식", "현금"), values, ALLOCATION_ROW_Y)):
        draw.text((92, y), label, font=_font(ALLOCATION_LABEL_FONT_SIZE, bold=True), fill=TEXT, anchor="lm")
        draw.text((375, y), value, font=_font(ALLOCATION_VALUE_FONT_SIZE, bold=True), fill=TEXT, anchor="rm")
        top = y - ALLOCATION_BAR_HEIGHT // 2
        box = (ALLOCATION_BAR_X, top, ALLOCATION_BAR_X + ALLOCATION_BAR_WIDTH, top + ALLOCATION_BAR_HEIGHT)
        draw.rounded_rectangle(box, radius=ALLOCATION_BAR_HEIGHT // 2, fill="#edf0f3")
        current_width = int(ALLOCATION_BAR_WIDTH * current[index])
        if current_width:
            draw.rounded_rectangle(
                (ALLOCATION_BAR_X, top, ALLOCATION_BAR_X + current_width, top + ALLOCATION_BAR_HEIGHT),
                radius=ALLOCATION_BAR_HEIGHT // 2,
                fill=NEUTRAL,
            )
        previous_width = int(ALLOCATION_BAR_WIDTH * previous[index])
        if briefing.needs_trade and current_width > previous_width:
            start = ALLOCATION_BAR_X + previous_width
            end = ALLOCATION_BAR_X + current_width
            radius = ALLOCATION_BAR_HEIGHT // 2
            draw.rectangle((start, top, max(start, end - radius), top + ALLOCATION_BAR_HEIGHT), fill=increase_colors[index])
            draw.ellipse((end - ALLOCATION_BAR_HEIGHT, top, end, top + ALLOCATION_BAR_HEIGHT), fill=increase_colors[index])


def _draw_status_panel(
    draw: ImageDraw.ImageDraw,
    briefing: BriefingLike,
    trade_plan: TradePlanLike | None,
    trade_plan_error: str | None,
) -> None:
    if not briefing.needs_trade:
        _rounded_panel(draw, (60, 870, 740, 1025), fill="#f3fbf5", outline="#dcefe1")
        _status_icon(draw, trade=False, side=None)
        draw.text((178, 925), "직전 비중과 동일합니다", font=_font(28, bold=True), fill=TEXT, anchor="lm")
        draw.text((178, 973), "오늘은 매매할 필요가 없습니다", font=_font(23), fill=TEXT, anchor="lm")
        return

    side = trade_plan.side if trade_plan else None
    action_color = DOWN if side == "매도" else UP
    _rounded_panel(draw, (60, 860, 740, 1032), fill="#fff5f6" if side != "매도" else "#f2f7ff", outline="#ffd7dc" if side != "매도" else "#d7e7ff")
    _status_icon(draw, trade=True, side=side)
    draw.text((178, 898), "리밸런싱이 필요합니다", font=_font(26, bold=True), fill=TEXT, anchor="lm")

    if trade_plan:
        action = f"TQQQ {trade_plan.quantity}주 {trade_plan.side}"
        detail = f"보유 {trade_plan.current_quantity}주 → 목표 {trade_plan.target_quantity}주"
    else:
        action = "주문 수량 확인 필요"
        detail = trade_plan_error or "토스 계좌 정보를 확인할 수 없습니다"
    draw.rounded_rectangle((178, 920, 710, 974), radius=14, fill=action_color)
    draw.text((444, 947), action, font=_font(28, bold=True), fill="white", anchor="mm")
    draw.text((444, 995), detail[:34], font=_font(22, bold=True), fill=TEXT, anchor="mm")
    draw.text((444, 1020), "다음 거래일 시가 기준 · 주문 전 수량 확인", font=_font(17), fill=MUTED, anchor="mm")


def render_briefing_card(
    briefing: BriefingLike,
    output: Path,
    trade_plan: TradePlanLike | None = None,
    trade_plan_error: str | None = None,
) -> None:
    image = Image.new("RGB", CARD_SIZE, CARD_BACKGROUND)
    draw = ImageDraw.Draw(image)
    _rounded_panel(draw, (25, 25, 775, 1042), radius=28)

    _calendar_icon(draw, 82, 75)
    draw.text(
        (145, 103),
        f"{briefing.market_date:%Y.%m.%d} 미국 시장 마감",
        font=_font(34, bold=True),
        fill=TEXT,
        anchor="lm",
    )
    draw.line((62, 155, 738, 155), fill=LINE, width=1)

    for symbol, y in zip(("IXIC", "QQQ", "TQQQ", "SPY"), (205, 300, 395, 490)):
        _draw_market_row(draw, symbol, briefing.closes[symbol], briefing.changes[symbol], y)

    _draw_vo_panel(draw, briefing)
    _draw_allocation_panel(draw, briefing)
    _draw_status_panel(draw, briefing, trade_plan, trade_plan_error)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)
    if output.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("briefing card exceeds Kakao's 5 MB image limit")
