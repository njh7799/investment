#!/usr/bin/env python3
"""Run the latest local market update, Kakao briefing, and git synchronization."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.send_daily_briefing import (
    REPOSITORY_URL,
    persist_rotated_refresh_token,
    refresh_access_token,
    send_text_to_kakao,
)
from scripts.update_market_data import (
    DAILY_SYMBOLS,
    NEW_YORK,
    is_nasdaq_session,
    latest_settled_session,
)

STATE_FILE = ROOT / ".daily-routine-state.json"
MARKET_UPDATE_ATTEMPTS = 3
MARKET_UPDATE_RETRY_DELAY_SECONDS = 60


def target_session(now: pd.Timestamp | None = None) -> pd.Timestamp | None:
    current = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    else:
        current = current.tz_convert("UTC")
    current_day = pd.Timestamp(current.tz_convert(NEW_YORK).date())
    if not is_nasdaq_session(current_day):
        return None
    if current_day > latest_settled_session(current):
        return None
    return current_day


def load_state(path: Path = STATE_FILE) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def save_state(state: dict[str, object], path: Path = STATE_FILE) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def latest_asset_dates() -> dict[str, pd.Timestamp]:
    result = {}
    for symbol in DAILY_SYMBOLS:
        dates = pd.read_csv(
            ROOT / "assets" / f"{symbol}.csv",
            usecols=["Date"],
            parse_dates=["Date"],
            date_format="%Y.%m.%d",
        )["Date"]
        if dates.empty:
            raise RuntimeError(f"{symbol}: market data is empty")
        result[symbol] = pd.Timestamp(dates.iloc[-1])
    return result


def run_checked(arguments: list[str]) -> None:
    subprocess.run(arguments, cwd=ROOT, check=True)


def update_market_data(target: pd.Timestamp) -> None:
    dates = latest_asset_dates()
    if all(date == target for date in dates.values()):
        return
    if any(date > target for date in dates.values()):
        details = ", ".join(
            f"{symbol}={date.date()}" for symbol, date in dates.items() if date > target
        )
        raise RuntimeError(f"market data is ahead of target {target.date()}: {details}")
    run_checked(
        [
            sys.executable,
            "scripts/update_market_data.py",
            "--mode",
            "daily",
            "--attempts",
            str(MARKET_UPDATE_ATTEMPTS),
            "--retry-delay",
            str(MARKET_UPDATE_RETRY_DELAY_SECONDS),
        ]
    )
    dates = latest_asset_dates()
    missing = [symbol for symbol, date in dates.items() if date != target]
    if missing:
        raise RuntimeError(
            f"market data update did not reach {target.date()}: {', '.join(missing)}"
        )


def send_briefing() -> None:
    run_checked([sys.executable, "scripts/send_daily_briefing.py"])


def commit_and_push(target: pd.Timestamp) -> None:
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    if branch != "main":
        raise RuntimeError(f"daily routine requires main branch, found {branch or 'detached HEAD'}")

    asset_paths = [f"assets/{symbol}.csv" for symbol in DAILY_SYMBOLS]
    run_checked(["git", "add", "--", *asset_paths])
    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", *asset_paths], cwd=ROOT
    )
    if staged.returncode not in (0, 1):
        raise RuntimeError("failed to inspect staged market data")
    if staged.returncode == 1:
        run_checked(["git", "commit", "-m", f"Update market data {target.date()}"])
    run_checked(["git", "push", "origin", "HEAD:main"])


def notify_failure(target: pd.Timestamp) -> None:
    load_dotenv(ROOT / ".env")
    rest_api_key = os.environ.get("KAKAO_REST_API_KEY")
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN")
    if not rest_api_key or not refresh_token:
        return
    access_token, rotated_refresh_token = refresh_access_token(
        rest_api_key,
        os.environ.get("KAKAO_CLIENT_SECRET", ""),
        refresh_token,
    )
    send_text_to_kakao(
        access_token,
        "\n".join(
            [
                "📭 오늘 아침 브리핑을 보내지 못했어요",
                "",
                "브리핑을 준비하는 중 일시적인 문제가 생겼습니다.",
                "자동으로 다시 시도했지만 아직 해결되지 않았어요.",
                "다음 실행에서 다시 확인할게요.",
            ]
        ),
        REPOSITORY_URL,
    )
    if rotated_refresh_token:
        persist_rotated_refresh_token(rotated_refresh_token)


def notify_failure_once(
    target: pd.Timestamp, state_path: Path = STATE_FILE
) -> None:
    target_text = str(target.date())
    state = load_state(state_path)
    if state.get("market_date") == target_text and state.get("failure_notified") is True:
        print(f"Failure notice already sent for {target_text}; skipping")
        return

    notify_failure(target)
    state = load_state(state_path)
    if state.get("market_date") != target_text:
        state = {
            "market_date": target_text,
            "briefing_sent": False,
            "pushed": False,
        }
    state["failure_notified"] = True
    state["failure_notified_at"] = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    save_state(state, state_path)


def execute(target: pd.Timestamp, state_path: Path = STATE_FILE) -> None:
    target_text = str(target.date())
    state = load_state(state_path)
    if state.get("market_date") != target_text:
        state = {
            "market_date": target_text,
            "briefing_sent": False,
            "pushed": False,
            "failure_notified": False,
        }
        save_state(state, state_path)
    if state.get("pushed") is True:
        print(f"Daily routine already completed for {target_text}; skipping")
        return

    update_market_data(target)
    if state.get("briefing_sent") is not True:
        send_briefing()
        state["briefing_sent"] = True
        save_state(state, state_path)
    commit_and_push(target)
    state["pushed"] = True
    state["completed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    save_state(state, state_path)
    print(f"Daily routine completed for {target_text}")


def main() -> int:
    target = target_session()
    if target is None:
        print("No current settled Nasdaq session; skipping daily routine")
        return 0
    try:
        execute(target)
    except Exception:
        try:
            notify_failure_once(target)
        except Exception as notification_error:
            print(
                f"Failed to send routine failure notice: {notification_error}",
                file=sys.stderr,
            )
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
