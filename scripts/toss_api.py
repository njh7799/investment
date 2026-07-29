#!/usr/bin/env python3
"""Authenticate with Toss Securities Open API and fetch account information."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


BASE_URL = "https://openapi.tossinvest.com"
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
REQUEST_TIMEOUT = 15


class TossApiError(RuntimeError):
    """An error returned by Toss Securities Open API."""


class TossApiClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        session: requests.Session | None = None,
        base_url: str = BASE_URL,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError("TOSS_CLIENT_ID and TOSS_CLIENT_SECRET are required")
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip("/")
        self._access_token: str | None = None

    @classmethod
    def from_env(cls, *, session: requests.Session | None = None) -> "TossApiClient":
        load_dotenv(ENV_FILE, override=False)
        return cls(
            os.environ.get("TOSS_CLIENT_ID", ""),
            os.environ.get("TOSS_CLIENT_SECRET", ""),
            session=session,
        )

    @staticmethod
    def _raise_for_api_error(response: requests.Response) -> None:
        if response.ok:
            return
        code = None
        message = None
        request_id = None
        try:
            payload = response.json()
            error = payload.get("error", payload)
            if isinstance(error, dict):
                code = error.get("code") or error.get("error")
                message = error.get("message") or error.get("error_description")
                request_id = error.get("requestId")
        except (ValueError, AttributeError):
            pass

        details = [f"HTTP {response.status_code}"]
        if code:
            details.append(str(code))
        if message:
            details.append(str(message))
        if request_id:
            details.append(f"requestId={request_id}")
        raise TossApiError(": ".join(details))

    def issue_access_token(self) -> str:
        response = self.session.post(
            f"{self.base_url}/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=REQUEST_TIMEOUT,
        )
        self._raise_for_api_error(response)
        payload = response.json()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise TossApiError("token response is missing access_token")
        self._access_token = token
        return token

    def get_accounts(self) -> list[dict[str, Any]]:
        token = self._access_token or self.issue_access_token()
        response = self.session.get(
            f"{self.base_url}/api/v1/accounts",
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT,
        )
        self._raise_for_api_error(response)
        payload = response.json()
        accounts = payload.get("result")
        if not isinstance(accounts, list):
            raise TossApiError("account response result must be a list")
        for account in accounts:
            if not isinstance(account, dict):
                raise TossApiError("account response contains a non-object item")
            missing = {"accountNo", "accountSeq", "accountType"} - account.keys()
            if missing:
                raise TossApiError(
                    f"account response is missing fields: {', '.join(sorted(missing))}"
                )
        return accounts


def main() -> int:
    try:
        accounts = TossApiClient.from_env().get_accounts()
    except (ValueError, TossApiError, requests.RequestException) as error:
        print(f"Toss API request failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(accounts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
