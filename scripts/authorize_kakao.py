#!/usr/bin/env python3
"""Complete one-time Kakao authorization and store the refresh token locally."""

from __future__ import annotations

import argparse
import os
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests
from dotenv import load_dotenv, set_key


ROOT = Path(__file__).resolve().parents[1]
REDIRECT_URI = "http://localhost:8765/oauth/kakao/callback"
AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"


class CallbackHandler(BaseHTTPRequestHandler):
    server: "CallbackServer"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/oauth/kakao/callback":
            self.send_error(404)
            return
        params = urllib.parse.parse_qs(parsed.query)
        self.server.callback = {key: values[0] for key, values in params.items()}
        body = "카카오 인증이 완료되었습니다. 이 창을 닫아도 됩니다.".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.server.completed.set()

    def log_message(self, format: str, *args: object) -> None:
        return


class CallbackServer(ThreadingHTTPServer):
    callback: dict[str, str]

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 8765), CallbackHandler)
        self.callback = {}
        self.completed = threading.Event()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    rest_api_key = os.environ.get("KAKAO_REST_API_KEY")
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET", "")
    if not rest_api_key:
        raise SystemExit("KAKAO_REST_API_KEY is missing from .env")

    state = secrets.token_urlsafe(24)
    query = urllib.parse.urlencode(
        {
            "client_id": rest_api_key,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "talk_message",
            "state": state,
        }
    )
    authorization_url = f"{AUTHORIZE_URL}?{query}"
    with CallbackServer() as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        if args.no_browser:
            print(authorization_url, flush=True)
        else:
            webbrowser.open(authorization_url)
            print("Kakao authorization opened in the browser.", flush=True)
        if not server.completed.wait(timeout=180):
            raise SystemExit("timed out waiting for Kakao authorization")
        server.shutdown()

    callback = server.callback
    if callback.get("state") != state:
        raise SystemExit("Kakao authorization state did not match")
    if "error" in callback:
        raise SystemExit(f"Kakao authorization failed: {callback['error']}")
    code = callback.get("code")
    if not code:
        raise SystemExit("Kakao authorization code was missing")

    payload = {
        "grant_type": "authorization_code",
        "client_id": rest_api_key,
        "redirect_uri": REDIRECT_URI,
        "code": code,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    response = requests.post(TOKEN_URL, data=payload, timeout=20)
    response.raise_for_status()
    refresh_token = response.json().get("refresh_token")
    if not refresh_token:
        raise SystemExit("Kakao did not return a refresh token")
    set_key(
        str(ROOT / ".env"),
        "KAKAO_REFRESH_TOKEN",
        str(refresh_token),
        quote_mode="never",
    )
    print("Stored KAKAO_REFRESH_TOKEN in the ignored local .env file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
