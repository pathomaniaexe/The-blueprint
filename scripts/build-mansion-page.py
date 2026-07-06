#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mansion"))

import app as mansion  # noqa: E402


def static_path(path: str) -> str:
    if path.startswith("/static/"):
        return "mansion/static/" + path.removeprefix("/static/")
    return path


mansion.app_path = static_path  # type: ignore[attr-defined]


def main() -> None:
    rooms_file = ROOT / "mansion" / "rooms.json"
    if rooms_file.exists():
        mansion.ROOMS = json.loads(rooms_file.read_text(encoding="utf-8"))
    else:
        mansion.ROOMS = mansion.init_rooms()

    login_body = mansion.login_page().decode("utf-8")
    login_start = login_body.index('<section class="login-shell">')
    login_end = login_body.index("</section>", login_start) + len("</section>")
    login_html = login_body[login_start:login_end]
    login_html = login_html.replace(
        f'<form class="login-panel" method="post" action="{static_path("/login")}" autocomplete="off">',
        '<form class="login-panel" id="login-form" autocomplete="off">',
    )
    login_html = login_html.replace(
        '<p class="intro">Enter the house password to continue.</p>',
        '<p class="intro">Enter the house password to continue.</p>\n        <p class="error" id="login-error" hidden></p>',
    )

    dashboard = mansion.dashboard_page("owner").decode("utf-8")
    dash_start = dashboard.index('<section class="house">')
    dash_end = dashboard.rindex("</section>") + len("</section>")
    dashboard_html = dashboard[dash_start:dash_end]

    for marker, repl in [
        ('class="rooms-toolbar"', 'class="rooms-toolbar" data-owner-only'),
        ('class="dialog-open"', 'class="dialog-open" data-owner-only'),
        ('class="room-edit-open"', 'class="room-edit-open" data-owner-only'),
        ('class="quick-form"', 'class="quick-form" data-owner-only'),
        ('id="add-room-dialog"', 'id="add-room-dialog" data-owner-only'),
        ('id="pk-import-dialog"', 'id="pk-import-dialog" data-owner-only'),
        ('id="room-dialog-', 'data-owner-only id="room-dialog-'),
    ]:
        dashboard_html = dashboard_html.replace(marker, repl)

    rooms_json = json.dumps(mansion.ROOMS, ensure_ascii=True)

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>The Mansion</title>
  <link rel="stylesheet" href="{static_path("/static/styles.css")}?v={mansion.STATIC_VERSION}">
  <script src="{static_path("/static/mansion-customize.js")}?v={mansion.STATIC_VERSION}"></script>
</head>
<body>
  <script id="mansion-rooms-data" type="application/json">{rooms_json}</script>
  <div class="ambient"></div>
  <main>
    <div id="login-view">
      {login_html}
    </div>
    <div id="mansion-view" hidden>
      <div class="topbar">
        <span class="role-pill" id="role-pill">Signed in</span>
        <div class="logout"><button type="button" id="lock-site">Lock Site</button></div>
      </div>
      {dashboard_html}
    </div>
  </main>
  <script src="mansion/mansion-auth.js?v={mansion.STATIC_VERSION}"></script>
  <script src="mansion/mansion-rooms.js?v={mansion.STATIC_VERSION}"></script>
  <script src="{static_path("/static/app.js")}?v={mansion.STATIC_VERSION}"></script>
</body>
</html>
"""

    out = ROOT / "mansion.html"
    out.write_text(page, encoding="utf-8")
    print(f"Wrote {out} ({len(mansion.ROOMS)} rooms)")


if __name__ == "__main__":
    main()
