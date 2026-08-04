#!/usr/bin/env python3
"""Store one approved local secret from the macOS clipboard without printing it."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from dotenv import set_key


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_NAMES = (
    "KAKAO_REST_API_KEY",
    "KAKAO_CLIENT_SECRET",
    "GH_SECRETS_TOKEN",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=ALLOWED_NAMES)
    args = parser.parse_args()
    result = subprocess.run(
        ["pbpaste"], capture_output=True, text=True, check=True
    )
    value = result.stdout.strip()
    if not value or "\n" in value or "\r" in value:
        raise SystemExit("clipboard must contain exactly one non-empty value")
    set_key(str(ROOT / ".env"), args.name, value, quote_mode="never")
    print(f"Stored {args.name} in the ignored local .env file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
