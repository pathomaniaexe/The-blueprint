#!/usr/bin/env python3
"""Generate a PBKDF2 password hash for mansion-auth.js or .sharing.env."""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mansion"))

import app as mansion  # noqa: E402


def main() -> None:
    label = (sys.argv[1] if len(sys.argv) > 1 else "password").strip()
    if sys.stdin.isatty():
        password = getpass.getpass(f"{label} password to hash: ")
    else:
        password = sys.stdin.read().strip()
    if not password:
        raise SystemExit("No password provided.")
    print(mansion.make_password_hash(password))


if __name__ == "__main__":
    main()
