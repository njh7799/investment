#!/usr/bin/env python3
"""Build and optionally send the daily market/VO briefing to KakaoTalk."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv, set_key

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtests import MarketData, build_target_weights, run_weight_strategy
from scripts.render_briefing_card import render_briefing_card


SYMBOLS = ("IXIC", "QQQ", "TQQQ", "SPY")
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
KAKAO_IMAGE_UPLOAD_URL = "https://kapi.kakao.com/v2/api/talk/message/image/upload"
REPOSITORY_URL = "https://github.com/njh7799/investment"


@dataclass(frozen=True)
class HistoricalMove:
    horizon: int
    return_value: float
    tail_probability: float
    observations: int

    @property
    def extremeness_score(self) -> float:
        """Return a 0-100 score where larger values are historically rarer."""
        return (1.0 - self.tail_probability) * 100.0

    @property
    def extremeness_level(self) -> str:
        return extremeness_level(self.extremeness_score)


@dataclass(frozen=True)
class StressContext:
    episode_start: pd.Timestamp
    vo_current_drawdown: float
    vo_episode_mdd: float
    tqqq_current_drawdown: float
    tqqq_episode_mdd: float
    underwater_days: int
    depth_rank: int | None
    duration_rank: int | None
    mdd_qualifying_episodes: int
    duration_qualifying_episodes: int
    historical_worst_mdd: float
    historical_longest_underwater_days: int


@dataclass(frozen=True)
class Briefing:
    market_date: pd.Timestamp
    closes: dict[str, float]
    changes: dict[str, float]
    volatility: float
    stock_weight: float
    previous_stock_weight: float
    volatility_change: float = 0.0
    historical_context: HistoricalMove | None = None
    stress_context: StressContext | None = None

    @property
    def needs_trade(self) -> bool:
        return self.stock_weight != self.previous_stock_weight


def load_prices(root: Path = ROOT) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for symbol in SYMBOLS:
        path = root / "assets" / f"{symbol}.csv"
        frame = pd.read_csv(path, parse_dates=["Date"], date_format="%Y.%m.%d")
        frame = frame.set_index("Date").sort_index()
        if len(frame) < 32 or frame[["Open", "High", "Low", "Close"]].isna().any().any():
            raise ValueError(f"{symbol}: insufficient or missing market data")
        frames[symbol] = frame

    latest_dates = {symbol: frame.index[-1] for symbol, frame in frames.items()}
    if len(set(latest_dates.values())) != 1:
        details = ", ".join(f"{symbol}={date.date()}" for symbol, date in latest_dates.items())
        raise ValueError(f"market data latest dates do not match: {details}")
    return frames


def vo_weight(volatility: float) -> float:
    if volatility <= 0.60:
        return 1.0
    if volatility <= 0.90:
        return 0.5
    return 0.0


def historical_move(close: pd.Series, horizon: int) -> HistoricalMove:
    """Locate the latest rolling return in the matching historical tail."""
    returns = close.pct_change(horizon).dropna()
    if returns.empty:
        raise ValueError(f"TQQQ: {horizon} daily returns are required for historical context")
    current = float(returns.iloc[-1])
    if current > 0:
        tail_count = int(returns.ge(current).sum())
    elif current < 0:
        tail_count = int(returns.le(current).sum())
    else:
        tail_count = len(returns)
    return HistoricalMove(
        horizon=horizon,
        return_value=current,
        tail_probability=tail_count / len(returns),
        observations=len(returns),
    )


def extremeness_level(score: float) -> str:
    if score >= 99.0:
        return "extreme"
    if score >= 95.0:
        return "rare"
    if score >= 80.0:
        return "notable"
    return "normal"


def _drawdown_episodes(equity: pd.Series) -> pd.DataFrame:
    """Return non-overlapping high-water-mark drawdown episodes."""
    equity = equity.dropna().astype(float)
    if equity.empty or not equity.index.is_monotonic_increasing or equity.index.has_duplicates:
        raise ValueError("VO equity dates must be complete, sorted, and unique")
    if (equity <= 0).any():
        raise ValueError("VO equity must stay positive")

    rows: list[dict[str, object]] = []
    peak_date = equity.index[0]
    peak_value = float(equity.iloc[0])
    trough_date = peak_date
    trough_value = peak_value
    active = False

    for date, raw_value in equity.iloc[1:].items():
        value = float(raw_value)
        if not active:
            if value >= peak_value:
                peak_date = date
                peak_value = value
                trough_date = date
                trough_value = value
            else:
                active = True
                trough_date = date
                trough_value = value
            continue

        if value < trough_value:
            trough_date = date
            trough_value = value
        if value >= peak_value:
            rows.append(
                {
                    "peak_date": peak_date,
                    "trough_date": trough_date,
                    "recovery_date": date,
                    "mdd": trough_value / peak_value - 1.0,
                    "underwater_days": int((date - peak_date).days),
                }
            )
            active = False
            peak_date = date
            peak_value = value
            trough_date = date
            trough_value = value

    if active:
        rows.append(
            {
                "peak_date": peak_date,
                "trough_date": trough_date,
                "recovery_date": pd.NaT,
                "mdd": trough_value / peak_value - 1.0,
                "underwater_days": int((equity.index[-1] - peak_date).days),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "peak_date",
            "trough_date",
            "recovery_date",
            "mdd",
            "underwater_days",
        ],
    )


def stress_context(frames: dict[str, pd.DataFrame]) -> StressContext:
    """Measure the current VO drawdown against the full synthetic history."""
    data = MarketData(
        ixic=frames["IXIC"],
        qqq=frames["QQQ"],
        tqqq=frames["TQQQ"],
    )
    prices, weights = build_target_weights("vo", data)
    result = run_weight_strategy(prices, weights, fee_rate=0.001)
    equity = result.equity
    episodes = _drawdown_episodes(equity)

    if episodes.empty or pd.notna(episodes.iloc[-1]["recovery_date"]):
        episode_start = equity.index[-1]
        vo_current_drawdown = 0.0
        vo_episode_mdd = 0.0
        underwater_days = 0
        depth_rank = None
        duration_rank = None
    else:
        current = episodes.iloc[-1]
        episode_start = pd.Timestamp(current["peak_date"])
        peak_equity = float(equity.loc[episode_start])
        vo_current_drawdown = float(equity.iloc[-1] / peak_equity - 1.0)
        vo_episode_mdd = float(current["mdd"])
        underwater_days = int(current["underwater_days"])
        depth_rank = None
        duration_rank = None

    mdd_qualifying = episodes.loc[episodes["mdd"] <= -0.10].copy()
    duration_qualifying = episodes.loc[episodes["underwater_days"] >= 30].copy()
    if vo_episode_mdd <= -0.10:
        depth_rank = int((mdd_qualifying["mdd"] < vo_episode_mdd).sum() + 1)
    if underwater_days >= 30:
        duration_rank = int(
            (duration_qualifying["underwater_days"] > underwater_days).sum() + 1
        )

    tqqq = frames["TQQQ"]["Close"].reindex(equity.index).loc[episode_start:]
    tqqq_start = float(tqqq.iloc[0])
    return StressContext(
        episode_start=episode_start,
        vo_current_drawdown=vo_current_drawdown,
        vo_episode_mdd=vo_episode_mdd,
        tqqq_current_drawdown=float(tqqq.iloc[-1] / tqqq_start - 1.0),
        tqqq_episode_mdd=float(tqqq.min() / tqqq_start - 1.0),
        underwater_days=underwater_days,
        depth_rank=depth_rank,
        duration_rank=duration_rank,
        mdd_qualifying_episodes=int(len(mdd_qualifying)),
        duration_qualifying_episodes=int(len(duration_qualifying)),
        historical_worst_mdd=float(episodes["mdd"].min()) if not episodes.empty else 0.0,
        historical_longest_underwater_days=(
            int(episodes["underwater_days"].max()) if not episodes.empty else 0
        ),
    )


def build_briefing(frames: dict[str, pd.DataFrame]) -> Briefing:
    closes = {symbol: float(frame["Close"].iloc[-1]) for symbol, frame in frames.items()}
    changes = {
        symbol: float(frame["Close"].iloc[-1] / frame["Close"].iloc[-2] - 1.0)
        for symbol, frame in frames.items()
    }
    returns = frames["TQQQ"]["Close"].pct_change()
    volatility = returns.rolling(30).std(ddof=1) * np.sqrt(252)
    current_volatility = float(volatility.iloc[-1])
    previous_volatility = float(volatility.iloc[-2])
    if not np.isfinite(current_volatility) or not np.isfinite(previous_volatility):
        raise ValueError("TQQQ: 30 daily returns are required for VO volatility")
    return Briefing(
        market_date=frames["TQQQ"].index[-1],
        closes=closes,
        changes=changes,
        volatility=current_volatility,
        stock_weight=vo_weight(current_volatility),
        previous_stock_weight=vo_weight(previous_volatility),
        volatility_change=current_volatility - previous_volatility,
        historical_context=historical_move(frames["TQQQ"]["Close"], 5),
        stress_context=stress_context(frames),
    )


def _ratio(stock_weight: float) -> str:
    stock = int(round(stock_weight * 100))
    return f"주식 {stock}% · 현금 {100 - stock}%"


def _market_line(symbol: str, close: float, change: float) -> str:
    price = f"{close:,.2f}pt" if symbol == "IXIC" else f"${close:,.2f}"
    if change > 0:
        movement = f"🔴 {change:+.2%}"
    elif change < 0:
        movement = f"🔵 {change:.2%}"
    else:
        movement = "⚪️ 0.00%"
    return f"• {symbol}: {price} ({movement})"


def format_briefing(briefing: Briefing) -> str:
    lines = [
        f"📊 {briefing.market_date:%Y.%m.%d} 미국 시장 마감",
        "",
    ]
    for symbol in SYMBOLS:
        lines.append(
            _market_line(symbol, briefing.closes[symbol], briefing.changes[symbol])
        )
    if briefing.stress_context:
        stress = briefing.stress_context
        depth = (
            f"{stress.depth_rank}위/{stress.mdd_qualifying_episodes}회"
            if stress.depth_rank is not None
            else "10% 미만"
        )
        duration = (
            f"{stress.duration_rank}위/{stress.duration_qualifying_episodes}회"
            if stress.duration_rank is not None
            else "30일 미만"
        )
        lines.extend(
            [
                "",
                "📉 VO 스트레스 · 합성 포함 전체",
                f"• 현재 낙폭 {stress.vo_current_drawdown:.2%} · "
                f"구간 MDD {stress.vo_episode_mdd:.2%} ({depth})",
                f"• 고점 미회복 {stress.underwater_days:,}일 ({duration})",
                f"• 같은 구간 TQQQ 현재 {stress.tqqq_current_drawdown:.2%} · "
                f"최대 {stress.tqqq_episode_mdd:.2%}",
                f"• 전체 최악 {stress.historical_worst_mdd:.2%} · "
                f"최장 {stress.historical_longest_underwater_days:,}일",
            ]
        )
    if briefing.historical_context:
        lines.extend(["", "🔎 TQQQ 하락 속도 · 합성 포함 전체"])
        move = briefing.historical_context
        lines.append(
            f"• {move.horizon}거래일 {move.return_value:+.2%} · "
            f"극단도 {move.extremeness_score:.1f}"
        )
    lines.extend(
        [
            "",
            f"⚡ VO 변동성: {briefing.volatility:.1%} ({_volatility_change(briefing.volatility_change)})",
            f"🎯 권장 비중: {_ratio(briefing.stock_weight)}",
        ]
    )
    if briefing.needs_trade:
        direction = "TQQQ 매수" if briefing.stock_weight > briefing.previous_stock_weight else "TQQQ 매도"
        lines.extend(
            [
                f"↔️ 직전 비중: {_ratio(briefing.previous_stock_weight)}",
                "",
                "🚨 비중이 변경되어 매매가 필요합니다.",
                f"다음 거래일 시가에 {direction}하여 목표 비중으로 리밸런싱하세요.",
            ]
        )
    else:
        lines.extend(["", "✅ 직전 비중과 동일합니다.", "오늘은 매매할 필요가 없습니다."])
    return "\n".join(lines)


def _volatility_change(change: float) -> str:
    if change > 0:
        return f"▲{change:.1%}p"
    if change < 0:
        return f"▼{abs(change):.1%}p"
    return "―0.0%p"


def refresh_access_token(
    rest_api_key: str, client_secret: str, refresh_token: str
) -> tuple[str, str | None]:
    payload = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    response = requests.post(KAKAO_TOKEN_URL, data=payload, timeout=20)
    response.raise_for_status()
    body = response.json()
    return str(body["access_token"]), body.get("refresh_token")


def upload_card_to_kakao(rest_api_key: str, image_path: Path) -> str:
    with image_path.open("rb") as image:
        response = requests.post(
            KAKAO_IMAGE_UPLOAD_URL,
            headers={"Authorization": f"KakaoAK {rest_api_key}"},
            files={"file": (image_path.name, image, "image/png")},
            timeout=30,
        )
    response.raise_for_status()
    return str(response.json()["infos"]["original"]["url"])


def send_to_kakao(
    access_token: str,
    briefing: Briefing,
    image_url: str,
) -> None:
    template = {
        "object_type": "feed",
        "content": {
            "title": f"{briefing.market_date:%Y.%m.%d} 미국 시장 마감",
            "image_url": image_url,
            "image_width": 800,
            "image_height": 1067,
            "link": {"web_url": REPOSITORY_URL, "mobile_web_url": REPOSITORY_URL},
        },
        "button_title": "저장소 열기",
    }
    response = requests.post(
        KAKAO_MEMO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        data={"template_object": json.dumps(template, ensure_ascii=False)},
        timeout=20,
    )
    response.raise_for_status()


def persist_rotated_refresh_token(refresh_token: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        repository = os.environ.get("GITHUB_REPOSITORY")
        secrets_token = os.environ.get("GH_SECRETS_TOKEN")
        if not repository or not secrets_token:
            raise RuntimeError(
                "rotated Kakao refresh token cannot be persisted: "
                "GITHUB_REPOSITORY and GH_SECRETS_TOKEN are required"
            )
        environment = os.environ.copy()
        environment["GH_TOKEN"] = secrets_token
        result = subprocess.run(
            ["gh", "secret", "set", "KAKAO_REFRESH_TOKEN", "--repo", repository],
            input=refresh_token,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("failed to update the rotated Kakao refresh token in GitHub Secrets")
        return

    env_path = ROOT / ".env"
    set_key(str(env_path), "KAKAO_REFRESH_TOKEN", refresh_token, quote_mode="never")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a daily market and VO briefing")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the briefing without contacting Kakao",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    frames = load_prices()
    briefing = build_briefing(frames)
    if args.dry_run:
        print(format_briefing(briefing))
        return 0

    load_dotenv(ROOT / ".env")
    required = ("KAKAO_REST_API_KEY", "KAKAO_REFRESH_TOKEN")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"missing environment variables: {', '.join(missing)}")

    access_token, rotated_refresh_token = refresh_access_token(
        os.environ["KAKAO_REST_API_KEY"],
        os.environ.get("KAKAO_CLIENT_SECRET", ""),
        os.environ["KAKAO_REFRESH_TOKEN"],
    )
    with tempfile.TemporaryDirectory(prefix="daily-briefing-") as directory:
        card_path = Path(directory) / "briefing.png"
        render_briefing_card(briefing, card_path)
        image_url = upload_card_to_kakao(os.environ["KAKAO_REST_API_KEY"], card_path)
        send_to_kakao(access_token, briefing, image_url)
    if rotated_refresh_token:
        persist_rotated_refresh_token(rotated_refresh_token)
    print(f"Kakao briefing sent for {briefing.market_date:%Y-%m-%d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
