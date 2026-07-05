#!/usr/bin/env python3
"""Paste new OWNER/VIEWER hashes into mansion/mansion-auth.js from .sharing.env."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".sharing.env"
AUTH = ROOT / "mansion" / "mansion-auth.js"


def read_env_value(key: str) -> str:
    if not ENV.exists():
        raise SystemExit(f"Missing {ENV}. Copy from .sharing.env.example first.")
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip("'\"")
    raise SystemExit(f"{key} not found in {ENV}")


def main() -> None:
    owner = read_env_value("OWNER_PASSWORD_HASH")
    viewer = read_env_value("VIEWER_PASSWORD_HASH")
    text = AUTH.read_text(encoding="utf-8")
    text, owner_count = re.subn(
        r'const OWNER_HASH\s*=\s*\n\s*"[^"]*";',
        f'const OWNER_HASH =\n    "{owner}";',
        text,
        count=1,
    )
    text, viewer_count = re.subn(
        r'const VIEWER_HASH\s*=\s*\n\s*"[^"]*";',
        f'const VIEWER_HASH =\n    "{viewer}";',
        text,
        count=1,
    )
    if owner_count != 1 or viewer_count != 1:
        raise SystemExit("Could not update hashes in mansion-auth.js")
    AUTH.write_text(text, encoding="utf-8")
    print(f"Updated {AUTH}")


if __name__ == "__main__":
    main()
