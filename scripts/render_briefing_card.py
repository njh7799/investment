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
SGOV = "#00a67e"

STRESS_PANEL = (60, 450, 740, 545)
ALLOCATION_PANEL = (60, 675, 740, 864)
ALLOCATION_ICON_BOX = (86, 696, 126, 736)
ALLOCATION_TITLE_POSITION = (142, 692)
ALLOCATION_ROW_Y = (756, 808)
ALLOCATION_BAR_X = 420
ALLOCATION_BAR_WIDTH = 290
ALLOCATION_BAR_HEIGHT = 16
ALLOCATION_LABEL_FONT_SIZE = 22
ALLOCATION_VALUE_FONT_SIZE = 22
SGOV_WAIT_POSITION = (710, 852)
DEFENSIVE_BREAKDOWN_POSITION = (710, 830)
SGOV_CONFIRMATION_SESSIONS = 15


class BriefingLike(Protocol):
    market_date: object
    closes: dict[str, float]
    changes: dict[str, float]
    volatility: float
    volatility_change: float
    stock_weight: float
    previous_stock_weight: float
    sgov_weight: float
    previous_sgov_weight: float
    sgov_lower_sessions: int
    sgov_upper_sessions: int
    historical_context: "HistoricalMoveLike | None"
    stress_context: "StressContextLike | None"

    @property
    def needs_trade(self) -> bool: ...

    @property
    def resolved_cash_weight(self) -> float: ...

    @property
    def resolved_previous_cash_weight(self) -> float: ...

    @property
    def tqqq_needs_trade(self) -> bool: ...

    @property
    def sgov_needs_trade(self) -> bool: ...


class HistoricalMoveLike(Protocol):
    horizon: int
    return_value: float
    tail_probability: float
    observations: int
    extremeness_score: float
    extremeness_level: str


class StressContextLike(Protocol):
    vo_current_drawdown: float
    vo_episode_mdd: float
    underwater_days: int
    depth_rank: int | None
    duration_rank: int | None
    mdd_qualifying_episodes: int
    duration_qualifying_episodes: int


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
    current = (
        briefing.stock_weight,
        briefing.sgov_weight + briefing.resolved_cash_weight,
    )
    previous = (
        briefing.previous_stock_weight,
        briefing.previous_sgov_weight + briefing.resolved_previous_cash_weight,
    )
    values: list[str] = []
    for before, after in zip(previous, current):
        after_text = f"{after:.0%}"
        values.append(
            f"{before:.0%} → {after_text}"
            if not math.isclose(before, after)
            else after_text
        )
    return values[0], values[1]


def defensive_breakdown_display(briefing: BriefingLike) -> str:
    values: list[str] = []
    for label, before, after in (
        ("SGOV", briefing.previous_sgov_weight, briefing.sgov_weight),
        ("현금", briefing.resolved_previous_cash_weight, briefing.resolved_cash_weight),
    ):
        current = f"{after:.0%}"
        values.append(
            f"{label} {before:.0%} → {current}"
            if not math.isclose(before, after)
            else f"{label} {current}"
        )
    return " · ".join(values)


def sgov_wait_display(briefing: BriefingLike) -> str:
    layers: list[str] = []
    if briefing.sgov_lower_sessions:
        lower = min(briefing.sgov_lower_sessions, SGOV_CONFIRMATION_SESSIONS)
        layers.append(f"60% 현금 {lower}/15")
    if briefing.sgov_upper_sessions:
        upper = min(briefing.sgov_upper_sessions, SGOV_CONFIRMATION_SESSIONS)
        layers.append(f"90% 현금 {upper}/15")
    return "SGOV 대기  " + (" · ".join(layers) if layers else "없음")


def trade_action_display(briefing: BriefingLike) -> str:
    actions: list[str] = []
    for symbol, current, previous in (
        ("TQQQ", briefing.stock_weight, briefing.previous_stock_weight),
        ("SGOV", briefing.sgov_weight, briefing.previous_sgov_weight),
    ):
        delta = current - previous
        if math.isclose(delta, 0.0):
            continue
        actions.append(f"{symbol} {abs(delta):.0%} {'매수' if delta > 0 else '매도'}")
    return " · ".join(actions)


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
    center_x, center_y, radius = 650, 628, 45
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
        label_radius = radius + 11
        draw.text(
            (
                center_x + label_radius * math.cos(angle),
                center_y + label_radius * math.sin(angle),
            ),
            label,
            font=_font(11, bold=True),
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
        (center_x, 647),
        label,
        font=_font(14, bold=True),
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


def _status_icon(draw: ImageDraw.ImageDraw, *, trade: bool, color: str = UP) -> None:
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
    draw.text((80, y), symbol, font=_font(31, bold=True), fill=color, anchor="lm")
    draw.text((510, y), price, font=_font(28, bold=True), fill=color, anchor="rm")
    draw.text((735, y), f"{arrow} {change_text}", font=_font(25, bold=True), fill=color, anchor="rm")
    draw.line((62, y + 42, 738, y + 42), fill=LINE, width=1)


def _stress_colors(drawdown: float) -> tuple[str, str]:
    if drawdown <= -0.45:
        return "#fff0f1", "#d92d3a"
    if drawdown <= -0.30:
        return "#fff4e5", "#f08c00"
    if drawdown <= -0.20:
        return "#fff9db", "#d4a000"
    return "#f4f6f8", "#8b95a1"


def _draw_stress_panel(draw: ImageDraw.ImageDraw, briefing: BriefingLike) -> None:
    stress = briefing.stress_context
    background, accent = (
        _stress_colors(stress.vo_current_drawdown) if stress else (CARD_WHITE, LINE)
    )
    _rounded_panel(draw, STRESS_PANEL, fill=background, outline=accent)
    draw.rounded_rectangle((72, 463, 80, 532), radius=4, fill=accent)
    draw.text((96, 472), "VO + 5/20 스트레스", font=_font(23, bold=True), fill=TEXT, anchor="lm")
    draw.text((714, 472), "전체", font=_font(15), fill=MUTED, anchor="rm")
    if not stress:
        draw.text((400, 515), "비교 자료 없음", font=_font(20), fill=MUTED, anchor="mm")
        return

    draw.line((383, 489, 383, 535), fill="#d9dde3", width=1)
    duration_rank = (
        f"{stress.duration_rank}/{stress.duration_qualifying_episodes}위"
        if stress.duration_rank is not None
        else "30일 미만"
    )
    draw.text((98, 507), "현재 낙폭", font=_font(19, bold=True), fill=TEXT, anchor="lm")
    draw.text(
        (362, 507),
        f"{stress.vo_current_drawdown:.2%}",
        font=_font(21, bold=True),
        fill=DOWN if stress.vo_current_drawdown < 0 else NEUTRAL,
        anchor="rm",
    )
    draw.text((405, 507), "미회복", font=_font(19, bold=True), fill=TEXT, anchor="lm")
    draw.text(
        (704, 507),
        f"{stress.underwater_days:,}일 · {duration_rank}",
        font=_font(21, bold=True),
        fill=TEXT,
        anchor="rm",
    )
    draw.text(
        (230, 534),
        "직전 고점 대비",
        font=_font(12),
        fill=MUTED,
        anchor="mm",
    )
    draw.text(
        (555, 534),
        "30일 이상 미회복 사건 중",
        font=_font(12),
        fill=MUTED,
        anchor="mm",
    )


def _draw_vo_panel(draw: ImageDraw.ImageDraw, briefing: BriefingLike) -> None:
    _rounded_panel(draw, (60, 560, 740, 655))
    _vo_icon(draw, 88, 587)
    draw.text((145, 608), "VO 변동성", font=_font(28, bold=True), fill=TEXT, anchor="lm")
    draw.text((430, 608), f"{briefing.volatility:.1%}", font=_font(34, bold=True), fill=TEXT, anchor="rm")
    change = briefing.volatility_change
    change_color = UP if change > 0 else DOWN if change < 0 else NEUTRAL
    change_arrow = "▲" if change > 0 else "▼" if change < 0 else "―"
    draw.text(
        (445, 608),
        f"{change_arrow}{abs(change):.1%}p",
        font=_font(24, bold=True),
        fill=change_color,
        anchor="lm",
    )
    _volatility_gauge(draw, briefing.volatility)


def _draw_allocation_panel(draw: ImageDraw.ImageDraw, briefing: BriefingLike) -> None:
    _rounded_panel(draw, ALLOCATION_PANEL)
    _allocation_icon(draw)
    draw.text(
        ALLOCATION_TITLE_POSITION,
        "최종 권장 비중",
        font=_font(29, bold=True),
        fill=TEXT,
        anchor="la",
    )
    values = allocation_display_values(briefing)
    current = (briefing.stock_weight, 1.0 - briefing.stock_weight)
    previous = (briefing.previous_stock_weight, 1.0 - briefing.previous_stock_weight)
    increase_colors = (UP, DOWN)
    for index, (label, value, y) in enumerate(
        zip(("TQQQ", "방어자산"), values, ALLOCATION_ROW_Y)
    ):
        draw.text((92, y), label, font=_font(ALLOCATION_LABEL_FONT_SIZE, bold=True), fill=TEXT, anchor="lm")
        draw.text((375, y), value, font=_font(ALLOCATION_VALUE_FONT_SIZE, bold=True), fill=TEXT, anchor="rm")
        top = y - ALLOCATION_BAR_HEIGHT // 2
        box = (ALLOCATION_BAR_X, top, ALLOCATION_BAR_X + ALLOCATION_BAR_WIDTH, top + ALLOCATION_BAR_HEIGHT)
        draw.rounded_rectangle(box, radius=ALLOCATION_BAR_HEIGHT // 2, fill="#edf0f3")
        current_width = int(ALLOCATION_BAR_WIDTH * current[index])
        if index == 1 and current_width:
            draw.rounded_rectangle(
                (ALLOCATION_BAR_X, top, ALLOCATION_BAR_X + current_width, top + ALLOCATION_BAR_HEIGHT),
                radius=ALLOCATION_BAR_HEIGHT // 2,
                fill=NEUTRAL,
            )
            sgov_width = int(ALLOCATION_BAR_WIDTH * briefing.sgov_weight)
            if sgov_width:
                draw.rounded_rectangle(
                    (ALLOCATION_BAR_X, top, ALLOCATION_BAR_X + sgov_width, top + ALLOCATION_BAR_HEIGHT),
                    radius=ALLOCATION_BAR_HEIGHT // 2,
                    fill=SGOV,
                )
        elif current_width:
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
    draw.text(
        DEFENSIVE_BREAKDOWN_POSITION,
        defensive_breakdown_display(briefing),
        font=_font(13),
        fill=MUTED,
        anchor="ra",
    )
    draw.text(
        SGOV_WAIT_POSITION,
        sgov_wait_display(briefing),
        font=_font(13),
        fill=MUTED,
        anchor="ra",
    )


def _draw_status_panel(
    draw: ImageDraw.ImageDraw,
    briefing: BriefingLike,
) -> None:
    if not briefing.needs_trade:
        _rounded_panel(draw, (60, 870, 740, 1025), fill="#f3fbf5", outline="#dcefe1")
        _status_icon(draw, trade=False)
        draw.text((178, 925), "직전 비중과 동일합니다", font=_font(28, bold=True), fill=TEXT, anchor="lm")
        draw.text((178, 973), "오늘은 매매할 필요가 없습니다", font=_font(23), fill=TEXT, anchor="lm")
        return

    if briefing.tqqq_needs_trade:
        action_color = UP if briefing.stock_weight > briefing.previous_stock_weight else DOWN
    else:
        action_color = SGOV
    panel_fill = (
        "#f2f7ff"
        if action_color == DOWN
        else "#f1fbf7" if action_color == SGOV else "#fff5f6"
    )
    panel_outline = (
        "#d7e7ff"
        if action_color == DOWN
        else "#cceee4" if action_color == SGOV else "#ffd7dc"
    )
    _rounded_panel(draw, (60, 875, 740, 1032), fill=panel_fill, outline=panel_outline)
    _status_icon(draw, trade=True, color=action_color)
    draw.text((178, 898), "리밸런싱이 필요합니다", font=_font(26, bold=True), fill=TEXT, anchor="lm")

    action = trade_action_display(briefing)
    detail = "다음 거래일 시가에 리밸런싱하세요"
    draw.rounded_rectangle((178, 920, 710, 974), radius=14, fill=action_color)
    draw.text((444, 947), action, font=_font(24, bold=True), fill="white", anchor="mm")
    draw.text((444, 995), detail[:34], font=_font(22, bold=True), fill=TEXT, anchor="mm")


def render_briefing_card(
    briefing: BriefingLike,
    output: Path,
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

    for symbol, y in zip(("IXIC", "QQQ", "TQQQ", "SPY"), (180, 250, 320, 390)):
        _draw_market_row(draw, symbol, briefing.closes[symbol], briefing.changes[symbol], y)

    _draw_stress_panel(draw, briefing)
    _draw_vo_panel(draw, briefing)
    _draw_allocation_panel(draw, briefing)
    _draw_status_panel(draw, briefing)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)
    if output.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("briefing card exceeds Kakao's 5 MB image limit")
