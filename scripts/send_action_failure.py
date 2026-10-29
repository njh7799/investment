#!/usr/bin/env python3
"""Send a GitHub Actions failure notice to the repository owner's KakaoTalk."""

from __future__ import annotations

import json
import os
import subprocess
from urllib.parse import urlencode
from urllib.request import Request, urlopen

KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def post_form(
    url: str,
    payload: dict[str, str],
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    request = Request(
        url,
        data=urlencode(payload).encode(),
        headers=headers or {},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read())


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
    body = post_form(KAKAO_TOKEN_URL, payload)
    return str(body["access_token"]), body.get("refresh_token")  # type: ignore[return-value]


def format_failure_message(workflow: str, details: str, repository: str, sha: str) -> str:
    return "\n".join(
        [
            "🚨 GitHub Actions 실패",
            f"• 작업: {workflow}",
            f"• 상태: {details}",
            f"• 저장소: {repository}",
            f"• 커밋: {sha[:7]}",
            "로그를 확인해 주세요.",
        ]
    )


def send_failure_notice(access_token: str, message: str, run_url: str) -> None:
    template = {
        "object_type": "text",
        "text": message,
        "link": {"web_url": run_url, "mobile_web_url": run_url},
        "button_title": "실패 로그 확인",
    }
    post_form(
        KAKAO_MEMO_URL,
        {"template_object": json.dumps(template, ensure_ascii=False)},
        headers={"Authorization": f"Bearer {access_token}"},
    )


def persist_rotated_refresh_token(refresh_token: str) -> None:
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


def main() -> int:
    required = (
        "FAILURE_WORKFLOW",
        "FAILURE_DETAILS",
        "GITHUB_REPOSITORY",
        "GITHUB_RUN_ID",
        "KAKAO_REST_API_KEY",
        "KAKAO_REFRESH_TOKEN",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"missing environment variables: {', '.join(missing)}")

    repository = os.environ["GITHUB_REPOSITORY"]
    run_url = (
        f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
        f"{repository}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    )
    access_token, rotated_refresh_token = refresh_access_token(
        os.environ["KAKAO_REST_API_KEY"],
        os.environ.get("KAKAO_CLIENT_SECRET", ""),
        os.environ["KAKAO_REFRESH_TOKEN"],
    )
    message = format_failure_message(
        os.environ["FAILURE_WORKFLOW"],
        os.environ["FAILURE_DETAILS"],
        repository,
        os.environ.get("GITHUB_SHA", "unknown"),
    )
    send_failure_notice(access_token, message, run_url)
    if rotated_refresh_token:
        persist_rotated_refresh_token(rotated_refresh_token)
    print(f"Kakao failure notice sent for {os.environ['FAILURE_WORKFLOW']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
