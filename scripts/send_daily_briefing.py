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
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv, set_key

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.toss_api import TossApiClient, TossApiError
from scripts.render_briefing_card import render_briefing_card


SYMBOLS = ("IXIC", "QQQ", "TQQQ", "SPY")
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
KAKAO_IMAGE_UPLOAD_URL = "https://kapi.kakao.com/v2/api/talk/message/image/upload"
REPOSITORY_URL = "https://github.com/njh7799/investment"


@dataclass(frozen=True)
class Briefing:
    market_date: pd.Timestamp
    closes: dict[str, float]
    changes: dict[str, float]
    volatility: float
    stock_weight: float
    previous_stock_weight: float

    @property
    def needs_trade(self) -> bool:
        return self.stock_weight != self.previous_stock_weight


@dataclass(frozen=True)
class TradePlan:
    account_mask: str
    side: str
    quantity: int
    current_quantity: int
    target_quantity: int
    reference_price: Decimal
    cash_buying_power: Decimal


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


def format_briefing(
    briefing: Briefing,
    trade_plan: TradePlan | None = None,
    trade_plan_error: str | None = None,
) -> str:
    lines = [
        f"📊 {briefing.market_date:%Y.%m.%d} 미국 시장 마감",
        "",
    ]
    for symbol in SYMBOLS:
        lines.append(
            _market_line(symbol, briefing.closes[symbol], briefing.changes[symbol])
        )
    lines.extend(
        [
            "",
            f"⚡ VO 변동성: {briefing.volatility:.1%}",
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
        if trade_plan is not None:
            lines.extend(
                [
                    "",
                    f"[토스 계좌 {trade_plan.account_mask} 주문 예상]",
                    f"보유 {trade_plan.current_quantity}주 → 목표 {trade_plan.target_quantity}주",
                    f"{trade_plan.side} {trade_plan.quantity}주",
                    f"계산 기준: TQQQ ${trade_plan.reference_price:.2f}, USD 현금 ${trade_plan.cash_buying_power:.2f}",
                    "※ 최신 종가 기준 예상 수량입니다. 다음 거래일 시가와 수수료에 따라 주문 직전 다시 확인하세요.",
                ]
            )
        elif trade_plan_error:
            lines.extend(["", f"⚠️ 토스 계좌 기준 주문 수량 계산 불가: {trade_plan_error}"])
    else:
        lines.extend(["", "✅ 직전 비중과 동일합니다.", "오늘은 매매할 필요가 없습니다."])
    return "\n".join(lines)


def _select_brokerage_account(
    accounts: list[dict[str, object]], requested_seq: str | None
) -> dict[str, object]:
    brokerage = [account for account in accounts if account.get("accountType") == "BROKERAGE"]
    if requested_seq:
        selected = [
            account for account in brokerage if str(account.get("accountSeq")) == requested_seq
        ]
        if len(selected) != 1:
            raise TossApiError("TOSS_ACCOUNT_SEQ does not identify one brokerage account")
        return selected[0]
    if len(brokerage) != 1:
        raise TossApiError(
            "exactly one brokerage account is required unless TOSS_ACCOUNT_SEQ is set"
        )
    return brokerage[0]


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise TossApiError(f"{field} is not a decimal") from error
    if not result.is_finite() or result < 0:
        raise TossApiError(f"{field} must be finite and non-negative")
    return result


def build_trade_plan(
    client: TossApiClient,
    briefing: Briefing,
    reference_price: float,
    *,
    requested_account_seq: str | None = None,
    fee_rate: Decimal = Decimal("0.001"),
) -> TradePlan:
    if not briefing.needs_trade:
        raise ValueError("a trade plan is only created when the VO state changes")
    account = _select_brokerage_account(client.get_accounts(), requested_account_seq)
    account_seq = account.get("accountSeq")
    if not isinstance(account_seq, int):
        raise TossApiError("selected account is missing an integer accountSeq")

    holdings = client.get_holdings(account_seq, symbol="TQQQ")
    items = holdings["items"]
    if len(items) > 1:
        raise TossApiError("TQQQ holdings response contains multiple items")
    quantity = _decimal(items[0].get("quantity"), "TQQQ quantity") if items else Decimal(0)
    if quantity != quantity.to_integral_value():
        raise TossApiError("fractional TQQQ holdings are not supported by the VO rule")
    current_quantity = int(quantity)

    buying_power = client.get_buying_power(account_seq, "USD")
    cash = _decimal(buying_power["cashBuyingPower"], "USD cashBuyingPower")
    price = _decimal(reference_price, "TQQQ reference price")
    if price == 0:
        raise TossApiError("TQQQ reference price must be positive")

    equity = Decimal(current_quantity) * price + cash
    target_value = equity * Decimal(str(briefing.stock_weight))
    target_quantity = int((target_value / price).to_integral_value(rounding=ROUND_FLOOR))
    delta = target_quantity - current_quantity
    if delta > 0:
        affordable = int(
            (cash / (price * (Decimal(1) + fee_rate))).to_integral_value(
                rounding=ROUND_FLOOR
            )
        )
        quantity_to_trade = min(delta, affordable)
        side = "매수"
    else:
        quantity_to_trade = -delta
        side = "매도"

    account_number = str(account.get("accountNo", ""))
    account_mask = f"••••{account_number[-4:]}" if len(account_number) >= 4 else "••••"
    return TradePlan(
        account_mask=account_mask,
        side=side,
        quantity=quantity_to_trade,
        current_quantity=current_quantity,
        target_quantity=target_quantity,
        reference_price=price,
        cash_buying_power=cash,
    )


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

    trade_plan = None
    trade_plan_error = None
    if briefing.needs_trade:
        toss_credentials = (
            os.environ.get("TOSS_CLIENT_ID"),
            os.environ.get("TOSS_CLIENT_SECRET"),
        )
        if all(toss_credentials):
            try:
                trade_plan = build_trade_plan(
                    TossApiClient(str(toss_credentials[0]), str(toss_credentials[1])),
                    briefing,
                    float(frames["TQQQ"]["Close"].iloc[-1]),
                    requested_account_seq=os.environ.get("TOSS_ACCOUNT_SEQ"),
                )
            except (TossApiError, requests.RequestException, ValueError) as error:
                trade_plan_error = str(error)
                print(f"Toss trade-plan calculation failed: {error}")
        else:
            trade_plan_error = "토스 API 자격증명이 설정되지 않았습니다."

    access_token, rotated_refresh_token = refresh_access_token(
        os.environ["KAKAO_REST_API_KEY"],
        os.environ.get("KAKAO_CLIENT_SECRET", ""),
        os.environ["KAKAO_REFRESH_TOKEN"],
    )
    with tempfile.TemporaryDirectory(prefix="daily-briefing-") as directory:
        card_path = Path(directory) / "briefing.png"
        render_briefing_card(briefing, card_path, trade_plan, trade_plan_error)
        image_url = upload_card_to_kakao(os.environ["KAKAO_REST_API_KEY"], card_path)
        send_to_kakao(access_token, briefing, image_url)
    if rotated_refresh_token:
        persist_rotated_refresh_token(rotated_refresh_token)
    print(f"Kakao briefing sent for {briefing.market_date:%Y-%m-%d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
