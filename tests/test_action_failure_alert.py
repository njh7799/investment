from __future__ import annotations

import json

from scripts import send_action_failure as alert


def test_failure_message_identifies_workflow_result_and_commit():
    message = alert.format_failure_message(
        "Publish investment reports",
        "build=failure, deploy=skipped",
        "njh7799/investment",
        "1234567890abcdef",
    )

    assert "GitHub Actions 실패" in message
    assert "Publish investment reports" in message
    assert "build=failure, deploy=skipped" in message
    assert "1234567" in message


def test_failure_notice_links_to_run_without_exposing_token(monkeypatch):
    captured = {}

    def fake_post(url, payload, *, headers=None):
        captured.update(url=url, payload=payload, headers=headers)
        return {"result_code": 0}

    monkeypatch.setattr(alert, "post_form", fake_post)

    alert.send_failure_notice(
        "secret-access-token",
        "failure details",
        "https://github.com/njh7799/investment/actions/runs/123",
    )

    template = json.loads(captured["payload"]["template_object"])
    assert template["object_type"] == "text"
    assert template["text"] == "failure details"
    assert template["link"]["web_url"].endswith("/actions/runs/123")
    assert captured["headers"] == {"Authorization": "Bearer secret-access-token"}


def test_refresh_access_token_supports_kakao_token_rotation(monkeypatch):
    captured = {}

    def fake_post(url, payload, *, headers=None):
        captured.update(url=url, payload=payload, headers=headers)
        return {"access_token": "access", "refresh_token": "rotated"}

    monkeypatch.setattr(alert, "post_form", fake_post)

    result = alert.refresh_access_token("app-key", "client-secret", "refresh")

    assert result == ("access", "rotated")
    assert captured["payload"]["client_secret"] == "client-secret"
    assert captured["payload"]["refresh_token"] == "refresh"
