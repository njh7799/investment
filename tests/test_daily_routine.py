from __future__ import annotations

import json

import pandas as pd

from scripts import run_daily_routine as routine


def test_target_session_runs_only_after_current_new_york_session_is_settled():
    assert routine.target_session(pd.Timestamp("2026-10-28 21:59:00Z")) is None
    assert routine.target_session(pd.Timestamp("2026-10-29 00:00:00Z")) == pd.Timestamp(
        "2026-10-28"
    )


def test_target_session_skips_non_trading_day_instead_of_backfilling():
    assert routine.target_session(pd.Timestamp("2026-11-01 00:00:00Z")) is None


def test_routine_state_round_trips_and_invalid_state_is_ignored(tmp_path):
    path = tmp_path / "state.json"
    state = {"market_date": "2026-10-28", "briefing_sent": True, "pushed": False}

    routine.save_state(state, path)

    assert routine.load_state(path) == state
    assert json.loads(path.read_text()) == state
    path.write_text("not-json")
    assert routine.load_state(path) == {}


def test_completed_session_is_not_replayed(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    target = pd.Timestamp("2026-10-28")
    routine.save_state(
        {"market_date": "2026-10-28", "briefing_sent": True, "pushed": True},
        path,
    )
    monkeypatch.setattr(
        routine,
        "update_market_data",
        lambda _: (_ for _ in ()).throw(AssertionError("update replayed")),
    )

    routine.execute(target, path)


def test_failed_push_resumes_without_resending_briefing(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    target = pd.Timestamp("2026-10-28")
    routine.save_state(
        {"market_date": "2026-10-28", "briefing_sent": True, "pushed": False},
        path,
    )
    calls = []
    monkeypatch.setattr(routine, "update_market_data", lambda value: calls.append(("update", value)))
    monkeypatch.setattr(
        routine,
        "send_briefing",
        lambda: (_ for _ in ()).throw(AssertionError("briefing resent")),
    )
    monkeypatch.setattr(routine, "commit_and_push", lambda value: calls.append(("push", value)))

    routine.execute(target, path)

    assert [name for name, _ in calls] == ["update", "push"]
    assert routine.load_state(path)["pushed"] is True
