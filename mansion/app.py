from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import parse_qs, quote, urlparse


ROOT = Path(__file__).parent
STATIC = ROOT / "static"
DATA_DIR = ROOT / "data"
ROOMS_FILE = DATA_DIR / "rooms.json"
SESSION_COOKIE = "mansion_session"
SESSION_TTL_SECONDS = 60 * 60 * 8
FAILED_WINDOW_SECONDS = 60 * 10
MAX_FAILED_ATTEMPTS = 7
LOCKOUT_SECONDS = 60 * 15
PBKDF2_ITERATIONS = 390_000
PLURALKIT_API = "https://api.pluralkit.me/v2"
USER_AGENT = "did-osdd-personal-site/1.0"
STATIC_VERSION = "20260712-01"
MAP_PAGE_SIZE = 48
ROOMS_PAGE_SIZE = 24

SESSIONS: dict[str, dict[str, float | str]] = {}
FAILED_LOGINS: dict[str, list[float]] = {}
LOCKOUTS: dict[str, float] = {}
ROLE_LABELS = {
    "owner": "Dev / owner / alter",
    "viewer": "View only",
}
ROOM_STATES = ("open", "unlocked", "internally locked", "external lock")

STATE_GUIDE = {
    "open": (
        "Open",
        "Shared spaces that stay reachable — foyer, halls, and common areas.",
    ),
    "unlocked": (
        "Unlocked",
        "Active or reachable parts. The door is open.",
    ),
    "internally locked": (
        "Dormant",
        "Locked from the inside. No one outside the room can force it open.",
    ),
    "external lock": (
        "Force-dormant",
        "External lock — needs extra boundaries, time, or protection before opening.",
    ),
}


DEFAULT_ROOMS = [
    {
        "name": "Foyer",
        "state": "open",
        "note": "The first room inside: chandelier overhead, chimney ahead, and the house stretching wider than it should.",
    },
    {
        "name": "Staircase",
        "state": "open",
        "note": "A dark stone spiral stair climbing up toward the rooms. It feels old, steady, and watchful.",
    },
    {
        "name": "Non-dormant doors",
        "state": "unlocked",
        "note": "Doors for active or reachable parts stay unlocked. They can be named and described when you are ready.",
    },
    {
        "name": "Dormant doors",
        "state": "internally locked",
        "note": "Dormant rooms are locked from the inside. No one outside the room can force them open.",
    },
    {
        "name": "Force-dormant doors",
        "state": "external lock",
        "note": "Old-style external locks mark doors that need extra boundaries, time, or protection before opening.",
    },
]


def clean_room(item: dict[str, object]) -> dict[str, object] | None:
    name = str(item.get("name", "")).strip()[:100]
    state = str(item.get("state", "unlocked")).strip()
    note = str(item.get("note", "")).strip()[:4000]
    source = str(item.get("source", "manual")).strip()[:40]
    pk = item.get("pk")
    if not name or not note:
        return None
    room: dict[str, object] = {
        "name": name,
        "state": state if state in ROOM_STATES else "unlocked",
        "note": note,
        "source": source,
    }
    if isinstance(pk, dict):
        room["pk"] = pk
    return room


def load_rooms() -> list[dict[str, object]]:
    if not ROOMS_FILE.exists():
        return [room.copy() for room in DEFAULT_ROOMS]
    try:
        data = json.loads(ROOMS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [room.copy() for room in DEFAULT_ROOMS]
    rooms = []
    if not isinstance(data, list):
        return [room.copy() for room in DEFAULT_ROOMS]
    for item in data:
        if not isinstance(item, dict):
            continue
        room = clean_room(item)
        if room:
            rooms.append(room)
    return rooms or [room.copy() for room in DEFAULT_ROOMS]


def save_rooms() -> None:
    if os.environ.get("MANSION_WORKER") == "1":
        return
    DATA_DIR.mkdir(exist_ok=True)
    ROOMS_FILE.write_text(json.dumps(ROOMS, indent=2), encoding="utf-8")


def now() -> float:
    return time.time()


def app_path(path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    base = os.environ.get("BASE_PATH", "").rstrip("/")
    return f"{base}{path}" if base else path


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def make_password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${b64(salt)}${b64(digest)}"


def configured_password_hash(prefix: str, fallback_password: str) -> str:
    password_hash = os.environ.get(f"{prefix}_PASSWORD_HASH", "").strip()
    if password_hash:
        return password_hash

    legacy_hash = os.environ.get("SITE_PASSWORD_HASH", "").strip()
    if prefix == "OWNER" and legacy_hash:
        return legacy_hash

    password = os.environ.get(f"{prefix}_PASSWORD", "").strip()
    if prefix == "OWNER" and not password:
        password = os.environ.get("SITE_PASSWORD", "").strip()
    if password:
        return make_password_hash(password)

    if os.environ.get("MANSION_WORKER") == "1":
        raise RuntimeError(
            f"{prefix}_PASSWORD_HASH must be set in the Cloudflare Worker environment."
        )

    return make_password_hash(fallback_password)


_CREDENTIALS: list[dict[str, str]] | None = None


def get_credentials() -> list[dict[str, str]]:
    global _CREDENTIALS
    if _CREDENTIALS is None:
        _CREDENTIALS = [
            {
                "role": "owner",
                "label": ROLE_LABELS["owner"],
                "hash": configured_password_hash("OWNER", "changeme"),
                "permissions": "view, add, edit, lock, unlock, import",
            },
            {
                "role": "viewer",
                "label": ROLE_LABELS["viewer"],
                "hash": configured_password_hash("VIEWER", "view-only"),
                "permissions": "view",
            },
        ]
    return _CREDENTIALS


def password_matches(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations, salt, expected = password_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), unb64(salt), int(iterations)
        )
        return hmac.compare_digest(b64(digest), expected)
    except Exception:
        return False


def verify_password(password: str) -> dict[str, str] | None:
    matched: dict[str, str] | None = None
    for credential in get_credentials():
        if password_matches(password, credential["hash"]):
            matched = credential
    return matched


def client_key(handler: BaseHTTPRequestHandler) -> str:
    forwarded = handler.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return handler.client_address[0]


def is_locked_out(key: str) -> bool:
    until = LOCKOUTS.get(key, 0)
    if until <= now():
        LOCKOUTS.pop(key, None)
        return False
    return True


def record_failed_login(key: str) -> None:
    cutoff = now() - FAILED_WINDOW_SECONDS
    attempts = [stamp for stamp in FAILED_LOGINS.get(key, []) if stamp >= cutoff]
    attempts.append(now())
    FAILED_LOGINS[key] = attempts
    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        LOCKOUTS[key] = now() + LOCKOUT_SECONDS
        FAILED_LOGINS[key] = []


def clear_failed_logins(key: str) -> None:
    FAILED_LOGINS.pop(key, None)
    LOCKOUTS.pop(key, None)


def clean_sessions() -> None:
    cutoff = now() - SESSION_TTL_SECONDS
    expired = [
        token for token, session in SESSIONS.items() if float(session["created"]) < cutoff
    ]
    for token in expired:
        SESSIONS.pop(token, None)


def render_page(
    title: str, body: str, authenticated: bool = False, role: str | None = None
) -> bytes:
    logout = ""
    if authenticated:
        label = ROLE_LABELS.get(role or "", "Signed in")
        logout = f"""
        <div class="topbar">
          <span class="role-pill">{html.escape(label)}</span>
          <form class="logout" method="post" action="{app_path('/logout')}">
            <button type="submit">Lock Site</button>
          </form>
        </div>
        """

    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" href="{html.escape(app_path('/static/styles.css'))}?v={STATIC_VERSION}">
  <script src="{html.escape(app_path('/static/mansion-customize.js'))}?v={STATIC_VERSION}"></script>
</head>
<body>
  <div class="ambient"></div>
  <main>
    {logout}
    {body}
  </main>
  <script src="{html.escape(app_path('/static/app.js'))}?v={STATIC_VERSION}"></script>
</body>
</html>"""
    return page.encode("utf-8")


def login_page(error: str = "") -> bytes:
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    body = f"""
    <section class="login-shell">
      <div class="login-hero" aria-hidden="true">
        <div class="login-hero-sky">
          <span class="login-starfield"></span>
          <span class="login-moon"></span>
        </div>
        <svg class="login-mansion-art" viewBox="0 0 480 340" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Mansion at night">
          <defs>
            <linearGradient id="roof-grad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stop-color="#3d342c"/>
              <stop offset="100%" stop-color="#1a1512"/>
            </linearGradient>
            <linearGradient id="wall-grad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="#2e2824"/>
              <stop offset="100%" stop-color="#1c1815"/>
            </linearGradient>
            <linearGradient id="window-glow" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stop-color="#f0d890"/>
              <stop offset="100%" stop-color="#c45a2c"/>
            </linearGradient>
            <filter id="window-blur" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="4" result="blur"/>
              <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
          </defs>
          <ellipse cx="240" cy="318" rx="210" ry="18" fill="#0a0908" opacity="0.55"/>
          <path d="M40 300 L440 300 L440 310 L40 310 Z" fill="#14110f"/>
          <path d="M120 300 L360 300 L350 268 L130 268 Z" fill="#1a1613"/>
          <rect x="155" y="268" width="170" height="32" fill="url(#wall-grad)" stroke="#3a332c" stroke-width="1"/>
          <path d="M130 268 L240 190 L350 268 Z" fill="url(#roof-grad)" stroke="#4a4036" stroke-width="1.2"/>
          <rect x="218" y="175" width="44" height="58" fill="url(#wall-grad)" stroke="#3a332c" stroke-width="1"/>
          <path d="M210 175 L240 138 L270 175 Z" fill="url(#roof-grad)" stroke="#4a4036" stroke-width="1"/>
          <rect x="88" y="210" width="72" height="90" fill="url(#wall-grad)" stroke="#3a332c" stroke-width="1"/>
          <path d="M80 210 L124 168 L168 210 Z" fill="url(#roof-grad)" stroke="#4a4036" stroke-width="1"/>
          <rect x="320" y="210" width="72" height="90" fill="url(#wall-grad)" stroke="#3a332c" stroke-width="1"/>
          <path d="M312 210 L356 168 L400 210 Z" fill="url(#roof-grad)" stroke="#4a4036" stroke-width="1"/>
          <rect x="278" y="148" width="22" height="36" fill="#2a2420" stroke="#3a332c" stroke-width="0.8"/>
          <rect x="278" y="132" width="22" height="18" fill="#1e1a17" stroke="#3a332c" stroke-width="0.8"/>
          <g class="login-smoke">
            <circle cx="289" cy="118" r="6" fill="#8a7f74" opacity="0.25"/>
            <circle cx="295" cy="102" r="8" fill="#8a7f74" opacity="0.18"/>
            <circle cx="283" cy="88" r="10" fill="#8a7f74" opacity="0.12"/>
          </g>
          <g filter="url(#window-blur)">
            <rect class="login-lit-window" x="104" y="232" width="18" height="28" rx="1" fill="url(#window-glow)"/>
            <rect class="login-lit-window" x="130" y="232" width="18" height="28" rx="1" fill="url(#window-glow)" style="animation-delay:.8s"/>
            <rect class="login-lit-window" x="336" y="232" width="18" height="28" rx="1" fill="url(#window-glow)" style="animation-delay:1.6s"/>
            <rect class="login-lit-window" x="362" y="232" width="18" height="28" rx="1" fill="url(#window-glow)" style="animation-delay:2.4s"/>
            <rect class="login-lit-window" x="178" y="228" width="16" height="22" rx="1" fill="url(#window-glow)" style="animation-delay:.4s"/>
            <rect class="login-lit-window" x="286" y="228" width="16" height="22" rx="1" fill="url(#window-glow)" style="animation-delay:1.2s"/>
            <rect class="login-lit-window" x="228" y="192" width="14" height="18" rx="1" fill="url(#window-glow)" style="animation-delay:2s"/>
          </g>
          <g stroke="#0c0a09" stroke-width="1.2" opacity="0.7">
            <line x1="113" y1="232" x2="113" y2="260"/><line x1="104" y1="246" x2="122" y2="246"/>
            <line x1="139" y1="232" x2="139" y2="260"/><line x1="130" y1="246" x2="148" y2="246"/>
            <line x1="345" y1="232" x2="345" y2="260"/><line x1="336" y1="246" x2="354" y2="246"/>
            <line x1="371" y1="232" x2="371" y2="260"/><line x1="362" y1="246" x2="380" y2="246"/>
          </g>
          <path d="M208 300 L208 248 Q240 220 272 248 L272 300 Z" fill="#241e19" stroke="#3a332c" stroke-width="1.2"/>
          <circle cx="262" cy="276" r="3.5" fill="#d4a853"/>
          <path d="M175 300 L305 300" stroke="#2a2420" stroke-width="3" stroke-linecap="round"/>
          <path d="M168 300 L168 268 L178 268 L178 300 M302 300 L302 268 L312 268 L312 300" stroke="#3a332c" stroke-width="2" fill="none"/>
          <path d="M60 300 Q90 270 120 300" fill="#12100e" stroke="#1e1a17" stroke-width="1"/>
          <path d="M360 300 Q390 272 420 300" fill="#12100e" stroke="#1e1a17" stroke-width="1"/>
        </svg>
        <div class="login-hero-fog"></div>
        <p class="login-hero-caption" data-customize="loginCaption">The headspace stretches wider than it should.</p>
      </div>
      <div class="login-panel-wrap">
        <form class="login-panel" method="post" action="{app_path('/login')}" autocomplete="off">
          <p class="eyebrow" data-customize="loginEyebrow">Private system space</p>
          <h1 data-customize="siteNameLocked">The mansion is locked.</h1>
          <p class="intro" data-customize="loginIntro">Enter the house password to continue.</p>
          {error_html}
          <label for="password">Password</label>
          <input id="password" name="password" type="password" required autofocus autocomplete="current-password">
          <button type="submit">Unlock</button>
          <p class="login-hint">Owner password opens every room. View-only password can look around but not edit.</p>
          <p class="security-note">Not indexed. Session stays in this browser until you lock the site.</p>
        </form>
      </div>
    </section>
    """
    return render_page("Locked Mansion", body)


def can_manage_rooms(role: str) -> bool:
    return role == "owner"


def room_option_tags(selected: str) -> str:
    return "\n".join(
        f'<option value="{html.escape(state)}"{" selected" if state == selected else ""}>{html.escape(state)}</option>'
        for state in ROOM_STATES
    )


def pk_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=True)
    return str(value)


LEGACY_PK_MARKERS = (
    "Avatar:",
    "Webhook avatar:",
    "Banner:",
    "Proxy tags:",
    "Message count:",
    "Last message:",
    "Autoproxy enabled:",
    "Keep proxy:",
    "Privacy:",
)


def pk_room_note(member: dict[str, object]) -> str:
    description = str(member.get("description") or "").strip()
    if description:
        return description[:4000]
    pronouns = str(member.get("pronouns") or "").strip()
    if pronouns:
        return pronouns[:4000]
    return "Imported from PluralKit."


def pk_is_room(room: dict[str, object]) -> bool:
    return isinstance(room.get("pk"), dict)


def pk_is_legacy_dump(note: str) -> bool:
    text = note.strip()
    if not text:
        return False
    if "cdn.pluralkit.me" in text and ("Created:" in text or "Message count:" in text):
        return True
    if "Autoproxy enabled:" in text and "Privacy:" in text:
        return True
    hits = sum(1 for marker in LEGACY_PK_MARKERS if marker in text)
    return hits >= 2


def pk_about_text(room: dict[str, object]) -> str:
    pk = room.get("pk")
    if not isinstance(pk, dict):
        return str(room.get("note", "")).strip()
    note = str(room.get("note", "")).strip()
    description = str(pk.get("description") or "").strip()
    if pk_is_legacy_dump(note):
        return description
    if note in {"", "Imported from PluralKit."}:
        return description
    return note


def pk_sanitized_note(room: dict[str, object]) -> str:
    if not pk_is_room(room):
        return str(room.get("note", "")).strip()[:4000]
    pk = room["pk"]
    if not isinstance(pk, dict):
        return str(room.get("note", "")).strip()[:4000]
    note = str(room.get("note", "")).strip()
    if pk_is_legacy_dump(note):
        return pk_room_note(pk)
    return note[:4000]


def migrate_legacy_pk_notes(rooms: list[dict[str, object]]) -> bool:
    changed = False
    for room in rooms:
        if not pk_is_room(room):
            continue
        note = str(room.get("note", "")).strip()
        if not pk_is_legacy_dump(note):
            continue
        room["note"] = pk_sanitized_note(room)
        if room.get("source") != "pluralkit":
            room["source"] = "pluralkit"
        changed = True
    return changed


def init_rooms() -> list[dict[str, object]]:
    rooms = load_rooms()
    if migrate_legacy_pk_notes(rooms) and os.environ.get("MANSION_WORKER") != "1":
        DATA_DIR.mkdir(exist_ok=True)
        ROOMS_FILE.write_text(json.dumps(rooms, indent=2), encoding="utf-8")
    return rooms


ROOMS: list[dict[str, object]] = [] if os.environ.get("MANSION_WORKER") == "1" else init_rooms()


def refresh_pk_notes() -> None:
    if migrate_legacy_pk_notes(ROOMS):
        save_rooms()


def pk_image_tag(url: object, alt: str, class_name: str) -> str:
    safe_url = str(url or "").strip()
    if not safe_url.startswith(("http://", "https://")):
        return ""
    return (
        f'<img class="{class_name}" src="{html.escape(safe_url)}" '
        f'alt="{html.escape(alt)}" loading="lazy" decoding="async">'
    )


def pk_format_timestamp(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("T", " · ").replace("Z", " UTC")


def pk_format_bool(value: object) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = str(value or "").strip()
    return text


def pk_color_markup(value: object) -> str:
    color = str(value or "").strip()
    if not color:
        return ""
    if color.startswith("#") and len(color) in (4, 7, 9):
        return (
            f'<span class="pk-color"><span class="pk-color-swatch" style="background: {html.escape(color)}"></span>'
            f"{html.escape(color)}</span>"
        )
    return html.escape(color)


def pk_field_rows(fields: list[tuple[str, str]]) -> str:
    rows = []
    for label, value in fields:
        if not value:
            continue
        rows.append(
            f"<div class=\"pk-field\"><dt>{html.escape(label)}</dt><dd>{value}</dd></div>"
        )
    if not rows:
        return '<p class="pk-empty">Nothing recorded here yet.</p>'
    return f'<dl class="pk-field-grid">{"".join(rows)}</dl>'


def pk_proxy_tags_markup(tags: object) -> str:
    if not isinstance(tags, list) or not tags:
        return '<p class="pk-empty">No proxy tags set.</p>'
    items = []
    for tag in tags:
        if not isinstance(tag, dict):
            continue
        prefix = str(tag.get("prefix") or "").strip()
        suffix = str(tag.get("suffix") or "").strip()
        if not prefix and not suffix:
            continue
        items.append(
            "<li>"
            f"<span class=\"pk-proxy-prefix\">{html.escape(prefix) if prefix else '—'}</span>"
            "<span class=\"pk-proxy-sep\">text</span>"
            f"<span class=\"pk-proxy-suffix\">{html.escape(suffix) if suffix else '—'}</span>"
            "</li>"
        )
    if not items:
        return '<p class="pk-empty">No proxy tags set.</p>'
    return f'<ul class="pk-proxy-list">{"".join(items)}</ul>'


def pk_privacy_rows(privacy: object) -> str:
    if not isinstance(privacy, dict) or not privacy:
        return '<p class="pk-empty">No privacy settings available.</p>'
    fields = [
        (key.replace("_", " ").title(), html.escape(str(value)))
        for key, value in sorted(privacy.items())
        if value is not None and str(value).strip()
    ]
    return pk_field_rows(fields)


def pk_room_panel(room: dict[str, object], index: int) -> str:
    pk = room.get("pk")
    if not isinstance(pk, dict):
        return f'<p class="room-note">{html.escape(str(room.get("note", "")))}</p>'

    room_name = str(room.get("name", "Alter"))
    avatar = pk_image_tag(pk.get("avatar_url"), room_name, "pk-avatar")
    banner = pk_image_tag(pk.get("banner"), f"{room_name} banner", "pk-banner")
    webhook = pk_image_tag(pk.get("webhook_avatar_url"), f"{room_name} webhook avatar", "pk-webhook")

    profile_fields = [
        ("PluralKit ID", html.escape(str(pk.get("id") or ""))),
        ("UUID", html.escape(str(pk.get("uuid") or ""))),
        ("System", html.escape(str(pk.get("system") or ""))),
        ("Name", html.escape(str(pk.get("name") or ""))),
        ("Display name", html.escape(str(pk.get("display_name") or ""))),
        ("Pronouns", html.escape(str(pk.get("pronouns") or ""))),
        ("Birthday", html.escape(str(pk.get("birthday") or ""))),
        ("Color", pk_color_markup(pk.get("color"))),
    ]
    profile_html = pk_field_rows(profile_fields)

    description = pk_about_text(room)
    about_html = (
        f'<div class="pk-description">{html.escape(description)}</div>'
        if description
        else '<p class="pk-empty">No description on PluralKit.</p>'
    )

    media_items = []
    if avatar:
        media_items.append(
            f'<figure class="pk-media-card"><figcaption>Avatar</figcaption>{avatar}</figure>'
        )
    if banner:
        media_items.append(
            f'<figure class="pk-media-card pk-media-banner"><figcaption>Banner</figcaption>{banner}</figure>'
        )
    if webhook:
        media_items.append(
            f'<figure class="pk-media-card"><figcaption>Webhook avatar</figcaption>{webhook}</figure>'
        )
    media_html = (
        f'<div class="pk-media-grid">{"".join(media_items)}</div>'
        if media_items
        else '<p class="pk-empty">No images imported for this alter.</p>'
    )

    proxy_fields = [
        ("Keep proxy", html.escape(pk_format_bool(pk.get("keep_proxy")))),
        ("Autoproxy", html.escape(pk_format_bool(pk.get("autoproxy_enabled")))),
        ("TTS", html.escape(pk_format_bool(pk.get("tts")))),
    ]
    proxy_html = pk_field_rows(proxy_fields) + pk_proxy_tags_markup(pk.get("proxy_tags"))

    activity_fields = [
        ("Created", html.escape(pk_format_timestamp(pk.get("created")))),
        ("Messages", html.escape(str(pk.get("message_count") or ""))),
        ("Last message", html.escape(pk_format_timestamp(pk.get("last_message_timestamp")))),
    ]
    activity_html = pk_field_rows(activity_fields)
    privacy_html = pk_privacy_rows(pk.get("privacy"))

    tabs = [
        ("profile", "Profile"),
        ("about", "About"),
        ("media", "Media"),
        ("proxy", "Proxy"),
        ("activity", "Activity"),
        ("privacy", "Privacy"),
    ]
    tab_buttons = []
    tab_panels = []
    for tab_id, label in tabs:
        active = " active" if tab_id == "profile" else ""
        panel_id = f"pk-{index}-{tab_id}"
        tab_buttons.append(
            f'<button type="button" class="pk-tab{active}" data-pk-tab="{panel_id}">{label}</button>'
        )
        panel_body = {
            "profile": profile_html,
            "about": about_html,
            "media": media_html,
            "proxy": proxy_html,
            "activity": activity_html,
            "privacy": privacy_html,
        }[tab_id]
        hidden = "" if tab_id == "profile" else " hidden"
        tab_panels.append(
            f'<section class="pk-panel{active}" id="{panel_id}" role="tabpanel"{hidden}>{panel_body}</section>'
        )

    return f"""
    <div class="pk-room" data-room-index="{index}">
      <nav class="pk-tabs" aria-label="{html.escape(room_name)} PluralKit details">
        {"".join(tab_buttons)}
      </nav>
      <div class="pk-panels">
        {"".join(tab_panels)}
      </div>
    </div>
    """


def room_card_header(room: dict[str, object]) -> str:
    name = html.escape(str(room.get("name", "")))
    state = html.escape(str(room.get("state", "")))
    meta_bits = []
    if pk_is_room(room):
        pk = room["pk"]
        if isinstance(pk, dict):
            pronouns = str(pk.get("pronouns") or "").strip()
            birthday = str(pk.get("birthday") or "").strip()
            if pronouns:
                meta_bits.append(html.escape(pronouns))
            if birthday:
                meta_bits.append(html.escape(birthday))
    meta_html = (
        f'<p class="room-meta">{" · ".join(meta_bits)}</p>' if meta_bits else ""
    )
    avatar_html = ""
    if pk_is_room(room):
        pk = room["pk"]
        if isinstance(pk, dict):
            avatar = pk_image_tag(pk.get("avatar_url"), str(room.get("name", "")), "room-avatar")
            if avatar:
                avatar_html = f'<div class="room-avatar-wrap">{avatar}</div>'
    source_html = (
        '<span class="room-source">PluralKit</span>' if pk_is_room(room) else ""
    )
    return f"""
    <div class="room-card-head">
      {avatar_html}
      <div class="room-card-title">
        <div class="room-card-labels">
          <span class="room-state">{state}</span>
          {source_html}
        </div>
        <h3>{name}</h3>
        {meta_html}
      </div>
    </div>
    """


def room_card_body(room: dict[str, object], index: int) -> str:
    if pk_is_room(room):
        return pk_room_panel(room, index)
    return f'<p class="room-note">{html.escape(str(room.get("note", "")))}</p>'


def room_card_body_wrapped(room: dict[str, object], index: int) -> str:
    if pk_is_room(room):
        return ""
    note = str(room.get("note", "")).strip()
    if len(note) <= 260:
        return f'<p class="room-card-blurb">{html.escape(note)}</p>'
    return f"""
    <details class="room-body-drawer">
      <summary>View note</summary>
      {room_card_body(room, index)}
    </details>
    """


def room_edit_note(room: dict[str, object]) -> str:
    return pk_sanitized_note(room)


def room_quick_hidden_fields(index: int, room: dict[str, object]) -> str:
    return f"""
      <input type="hidden" name="index" value="{index}">
      <input type="hidden" name="name" value="{html.escape(str(room.get("name", "")))}">
      <input type="hidden" name="note" value="{html.escape(room_edit_note(room))}">
      <input type="hidden" name="state" value="{html.escape(str(room.get("state", "unlocked")))}">
    """


def room_card_actions(index: int, room: dict[str, object], role: str) -> str:
    buttons = []
    if pk_is_room(room):
        buttons.append(
            f'<button type="button" class="pk-details-open" data-dialog="pk-dialog-{index}">PluralKit</button>'
        )
    if can_manage_rooms(role):
        hidden = room_quick_hidden_fields(index, room)
        buttons.extend(
            [
                f'<button type="button" class="room-edit-open" data-dialog="room-dialog-{index}">Edit</button>',
                f"""
      <form class="quick-form" method="post" action="{app_path('/rooms/update')}">
        {hidden}
        <button type="submit" name="action" value="unlock">Unlock</button>
      </form>
                """,
                f"""
      <form class="quick-form" method="post" action="{app_path('/rooms/update')}">
        {hidden}
        <button type="submit" name="action" value="dormant">Dormant</button>
      </form>
                """,
                f"""
      <form class="quick-form" method="post" action="{app_path('/rooms/update')}">
        {hidden}
        <button type="submit" name="action" value="force">Lock</button>
      </form>
                """,
                f"""
      <form class="quick-form" method="post" action="{app_path('/rooms/update')}" data-confirm="Delete this room?">
        {hidden}
        <button class="danger" type="submit" name="action" value="delete">Delete</button>
      </form>
                """,
            ]
        )
    if not buttons:
        return ""
    return f'<div class="room-quick-actions">{"".join(buttons)}</div>'


def pk_details_dialog(index: int, room: dict[str, object]) -> str:
    if not pk_is_room(room):
        return ""
    name = html.escape(str(room.get("name", "")))
    return f"""
    <dialog class="room-dialog pk-dialog" id="pk-dialog-{index}">
      <div class="dialog-head">
        <h4>{name}</h4>
        <button type="button" class="dialog-close" aria-label="Close">×</button>
      </div>
      <div class="pk-dialog-body">
        {pk_room_panel(room, index)}
      </div>
    </dialog>
    """


def room_edit_dialog(index: int, room: dict[str, object], role: str) -> str:
    if not can_manage_rooms(role):
        return ""
    state = str(room.get("state", "unlocked"))
    is_pk = pk_is_room(room)
    note_field = ""
    if is_pk:
        note_field = (
            f'<input type="hidden" name="note" value="{html.escape(room_edit_note(room))}">'
            '<p class="pk-edit-hint">Open PluralKit on the card to view imported details. Re-import to refresh from PluralKit.</p>'
        )
    else:
        note_field = f"""
        <label class="wide">
          <span>Details</span>
          <textarea name="note" maxlength="4000" required>{html.escape(room_edit_note(room))}</textarea>
        </label>
        """
    name = html.escape(str(room.get("name", "")))
    return f"""
    <dialog class="room-dialog" id="room-dialog-{index}">
      <div class="dialog-head">
        <h4>Edit {name}</h4>
        <button type="button" class="dialog-close" aria-label="Close">×</button>
      </div>
      <form class="room-manage" method="post" action="{app_path('/rooms/update')}">
        <input type="hidden" name="index" value="{index}">
        <label>
          <span>Name</span>
          <input name="name" maxlength="100" value="{name}" required>
        </label>
        <label>
          <span>State</span>
          <select name="state">{room_option_tags(state)}</select>
        </label>
        {note_field}
        <div class="room-actions">
          <button type="submit" name="action" value="save">Save</button>
          <button type="submit" name="action" value="unlock">Unlock</button>
          <button type="submit" name="action" value="dormant">Dormant</button>
          <button type="submit" name="action" value="force">Force Lock</button>
          <button class="danger" type="submit" name="action" value="delete">Delete</button>
        </div>
      </form>
    </dialog>
    """


def fetch_pluralkit_members(token: str, system_ref: str) -> list[dict[str, object]]:
    safe_ref = system_ref.strip() or "@me"
    url = f"{PLURALKIT_API}/systems/{quote(safe_ref, safe='@')}/members"
    req = urlrequest.Request(
        url,
        headers={
            "Authorization": token,
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urlrequest.urlopen(req, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("PluralKit returned an unexpected response.")
    return [item for item in data if isinstance(item, dict)]


def member_to_room(member: dict[str, object]) -> dict[str, object] | None:
    name = str(member.get("display_name") or member.get("name") or "").strip()
    if not name:
        return None
    return {
        "name": name[:100],
        "state": "unlocked",
        "note": pk_room_note(member),
        "source": "pluralkit",
        "pk": member,
    }


def upsert_pk_rooms(members: list[dict[str, object]]) -> tuple[int, int, int]:
    existing_by_uuid = {}
    for index, room in enumerate(ROOMS):
        pk = room.get("pk")
        if isinstance(pk, dict) and pk.get("uuid"):
            existing_by_uuid[str(pk["uuid"])] = index

    added = 0
    updated = 0
    skipped = 0
    for member in members:
        room = member_to_room(member)
        if not room:
            skipped += 1
            continue
        uuid = str(member.get("uuid") or "")
        if uuid and uuid in existing_by_uuid:
            index = existing_by_uuid[uuid]
            current_state = str(ROOMS[index].get("state", "unlocked"))
            room["state"] = current_state if current_state in ROOM_STATES else "unlocked"
            ROOMS[index] = room
            updated += 1
        else:
            ROOMS.append(room)
            added += 1
    if added or updated:
        save_rooms()
    return added, updated, skipped


def map_room_tile(index: int, room: dict[str, object]) -> str:
    avatar_html = ""
    if pk_is_room(room):
        pk = room.get("pk")
        if isinstance(pk, dict):
            avatar = pk_image_tag(pk.get("avatar_url"), str(room.get("name", "")), "map-avatar")
            if avatar:
                avatar_html = f'<div class="map-avatar-wrap">{avatar}</div>'
    return f"""
        <article class="map-room" data-layout-index="{index}" data-name="{html.escape(str(room.get('name', '')).lower())}" data-state="{html.escape(str(room['state']))}">
          <div class="map-room-top">
            <span class="map-position">{index + 1}</span>
            {avatar_html}
          </div>
          <strong>{html.escape(str(room['name']))}</strong>
          <small>{html.escape(str(room['state']))}</small>
        </article>
        """


def room_state_legend() -> str:
    items = []
    for state in ROOM_STATES:
        label, description = STATE_GUIDE[state]
        items.append(
            f"""
        <div class="state-legend-item" data-state="{html.escape(state)}">
          <div class="state-legend-head">
            <span class="state-legend-pill">{html.escape(label)}</span>
            <span class="state-legend-code">{html.escape(state)}</span>
          </div>
          <p>{html.escape(description)}</p>
        </div>
            """
        )
    return f"""
    <aside class="state-legend" aria-label="What each room state means">
      <h3>State index</h3>
      <div class="state-legend-grid">{"".join(items)}</div>
    </aside>
    """


def layout_sort_controls(target_id: str, control_id: str, page_size: int = 0) -> str:
    page_size_attr = f' data-page-size="{page_size}"' if page_size else ""
    return f"""
    <div class="layout-sort" data-target="{target_id}" data-control-id="{control_id}"{page_size_attr}>
      <div class="layout-sort-row">
        <label class="layout-sort-label" for="{control_id}-search">Search</label>
        <input id="{control_id}-search" class="layout-search" type="search" placeholder="Find a room by name..." autocomplete="off" spellcheck="false">
      </div>
      <div class="layout-sort-row">
        <label class="layout-sort-label" for="{control_id}-sort">Sort</label>
        <select id="{control_id}-sort" class="layout-sort-select">
          <option value="layout">Layout order</option>
          <option value="state">By state</option>
          <option value="name">By name</option>
        </select>
      </div>
      <div class="layout-filter" role="group" aria-label="Filter by state">
        <button type="button" class="layout-filter-btn active" data-filter="all">All</button>
        <button type="button" class="layout-filter-btn" data-filter="open">Open</button>
        <button type="button" class="layout-filter-btn" data-filter="unlocked">Unlocked</button>
        <button type="button" class="layout-filter-btn" data-filter="internally locked">Dormant</button>
        <button type="button" class="layout-filter-btn" data-filter="external lock">Force-dormant</button>
      </div>
    </div>
    """


def layout_pagination(control_id: str) -> str:
    return f"""
    <nav class="layout-pagination" id="{control_id}-pagination" hidden aria-label="Page navigation">
      <button type="button" class="page-btn" data-page="prev">Previous</button>
      <span class="page-status" id="{control_id}-page-status">Page 1 of 1</span>
      <button type="button" class="page-btn" data-page="next">Next</button>
    </nav>
    """


def rooms_toolbar(role: str) -> str:
    if not can_manage_rooms(role):
        return ""
    return """
    <div class="rooms-toolbar">
      <button type="button" class="dialog-open" data-dialog="add-room-dialog">New room</button>
      <button type="button" class="dialog-open dialog-open-pk" data-dialog="pk-import-dialog">Import PluralKit</button>
    </div>
    """


def add_room_dialog(role: str) -> str:
    if not can_manage_rooms(role):
        return ""
    options = room_option_tags("unlocked")
    return f"""
    <dialog class="room-dialog" id="add-room-dialog">
      <div class="dialog-head">
        <h4>Add a new room</h4>
        <button type="button" class="dialog-close" aria-label="Close">×</button>
      </div>
      <form class="dialog-form add-room" method="post" action="{app_path('/rooms')}">
        <label for="room-name">Room name</label>
        <input id="room-name" name="name" maxlength="100" required>
        <label for="room-state">Room state</label>
        <select id="room-state" name="state">
          {options}
        </select>
        <label for="room-note">Note</label>
        <textarea id="room-note" name="note" maxlength="4000" required></textarea>
        <button type="submit">Add room</button>
      </form>
    </dialog>
    """


def customize_panel(role: str) -> str:
    if not can_manage_rooms(role):
        return ""
    return """
      <section class="tab-panel" id="customize" role="tabpanel" hidden data-owner-only>
        <div class="section-heading">
          <h2>Customize</h2>
          <p>Rename your space and tune colors. Changes save in this browser only — each visitor keeps their own look unless you share the same device.</p>
        </div>
        <form class="customize-form" id="customize-form" autocomplete="off">
          <fieldset class="customize-section">
            <legend>Site name &amp; text</legend>
            <div class="customize-grid">
              <label>
                <span>Site name</span>
                <input type="text" name="siteName" data-customize-field="siteName" maxlength="80" placeholder="The Mansion">
              </label>
              <label>
                <span>Locked login title</span>
                <input type="text" name="siteNameLocked" data-customize-field="siteNameLocked" maxlength="80" placeholder="The mansion is locked.">
              </label>
              <label>
                <span>Dashboard eyebrow</span>
                <input type="text" name="eyebrow" data-customize-field="eyebrow" maxlength="60" placeholder="Headspace directory">
              </label>
              <label>
                <span>Login eyebrow</span>
                <input type="text" name="loginEyebrow" data-customize-field="loginEyebrow" maxlength="60" placeholder="Private system space">
              </label>
              <label class="customize-wide">
                <span>Dashboard intro</span>
                <textarea name="intro" data-customize-field="intro" maxlength="400" rows="3" placeholder="A private room system for the mansion headspace..."></textarea>
              </label>
              <label class="customize-wide">
                <span>Login intro</span>
                <textarea name="loginIntro" data-customize-field="loginIntro" maxlength="200" rows="2" placeholder="Enter the house password to continue."></textarea>
              </label>
              <label class="customize-wide">
                <span>Login hero caption</span>
                <input type="text" name="loginCaption" data-customize-field="loginCaption" maxlength="120" placeholder="The headspace stretches wider than it should.">
              </label>
            </div>
          </fieldset>
          <fieldset class="customize-section">
            <legend>Colors</legend>
            <div class="customize-color-grid">
              <label class="customize-color">
                <span>Accent gold</span>
                <input type="color" name="gold" data-customize-color="gold" value="#d4a853">
              </label>
              <label class="customize-color">
                <span>Accent highlight</span>
                <input type="color" name="goldBright" data-customize-color="goldBright" value="#e8c878">
              </label>
              <label class="customize-color">
                <span>Unlocked / open</span>
                <input type="color" name="moss" data-customize-color="moss" value="#6d9470">
              </label>
              <label class="customize-color">
                <span>Dormant</span>
                <input type="color" name="stone" data-customize-color="stone" value="#7a8a94">
              </label>
              <label class="customize-color">
                <span>Force-dormant</span>
                <input type="color" name="red" data-customize-color="red" value="#b85c5c">
              </label>
              <label class="customize-color">
                <span>Warm glow</span>
                <input type="color" name="ember" data-customize-color="ember" value="#c45a2c">
              </label>
              <label class="customize-color">
                <span>Main text</span>
                <input type="color" name="ink" data-customize-color="ink" value="#f4efe6">
              </label>
              <label class="customize-color">
                <span>Muted text</span>
                <input type="color" name="muted" data-customize-color="muted" value="#c4b8aa">
              </label>
            </div>
          </fieldset>
          <div class="customize-actions">
            <button type="button" class="customize-reset" id="customize-reset">Reset to defaults</button>
            <p class="customize-hint">Changes apply instantly and persist in local storage.</p>
          </div>
        </form>
      </section>
    """


def pk_import_dialog(role: str) -> str:
    if not can_manage_rooms(role):
        return ""
    return f"""
    <dialog class="room-dialog" id="pk-import-dialog">
      <div class="dialog-head">
        <h4>Import from PluralKit</h4>
        <button type="button" class="dialog-close" aria-label="Close">×</button>
      </div>
      <form class="dialog-form pk-import" method="post" action="{app_path('/pluralkit/import')}" autocomplete="off">
        <label for="pk-token">PluralKit token</label>
        <input id="pk-token" name="token" type="password" required>
        <label for="pk-system">System ref</label>
        <input id="pk-system" name="system_ref" value="@me" required>
        <p class="pk-edit-hint">Your token is used for this import only and is not saved.</p>
        <button type="submit">Import alters</button>
      </form>
    </dialog>
    """


def dashboard_page(role: str, rooms_page: int = 1, map_page: int = 1) -> bytes:
    refresh_pk_notes()
    room_cards = "\n".join(
        f"""
        <article class="room-card{' pk-room-card' if pk_is_room(room) else ' room-card-manual'}" data-layout-index="{index}" data-name="{html.escape(str(room.get('name', '')).lower())}" data-state="{html.escape(str(room['state']))}">
          {room_card_header(room)}
          {room_card_actions(index, room, role)}
          {room_card_body_wrapped(room, index)}
          {pk_details_dialog(index, room)}
          {room_edit_dialog(index, room, role)}
        </article>
        """
        for index, room in enumerate(ROOMS)
    )
    map_nodes = "\n".join(map_room_tile(index, room) for index, room in enumerate(ROOMS))
    notes_access = (
        '<textarea id="private-notes" spellcheck="true" placeholder="Draft system notes here. Saved browser-side only for now."></textarea>'
        if role == "owner"
        else '<textarea id="private-notes" readonly placeholder="View-only login: notes editing is locked for this password."></textarea>'
    )
    customize_tab = (
        '<button class="tab" type="button" data-tab="customize" data-owner-only>Customize</button>'
        if can_manage_rooms(role)
        else ""
    )
    tabs = f"""
        <button class="tab active" type="button" data-tab="map">Map</button>
        <button class="tab" type="button" data-tab="rooms">Rooms</button>
        <button class="tab" type="button" data-tab="notes">Notes</button>
        {customize_tab}
    """


    body = f"""
    <section class="house">
      <div class="house-hero">
        <div>
          <p class="eyebrow" data-customize="eyebrow">Headspace directory</p>
          <h1 data-customize="siteName">The Mansion</h1>
          <p class="intro" data-customize="intro">A private room system for the mansion headspace. Rooms can be added, edited, locked, unlocked, and imported from PluralKit with dev permissions.</p>
        </div>
        <div class="house-summary" data-customize-aria="summaryLabel" aria-label="Current mansion summary">
          <div><strong>{len(ROOMS)}</strong><span>Total rooms</span></div>
          <div><strong>{sum(1 for room in ROOMS if room.get("state") in ("open", "unlocked"))}</strong><span>Open or unlocked</span></div>
          <div><strong>{sum(1 for room in ROOMS if room.get("state") == "internally locked")}</strong><span>Dormant</span></div>
          <div><strong>{sum(1 for room in ROOMS if room.get("state") == "external lock")}</strong><span>Force-dormant</span></div>
        </div>
      </div>

      <nav class="tabs" data-customize-aria="tabsLabel" aria-label="Mansion sections">
        {tabs}
      </nav>

      <section class="tab-panel active" id="map" role="tabpanel">
        <div class="section-heading">
          <h2>Current Layout</h2>
          <p>Sort and filter the map by room state — dormant, force-dormant, unlocked, and more.</p>
        </div>
        {layout_sort_controls("map-board", "map", MAP_PAGE_SIZE)}
        <div class="map-board" id="map-board">
          {map_nodes}
        </div>
        {layout_pagination("map")}
      </section>

      <section class="tab-panel" id="rooms" role="tabpanel" hidden>
        <div class="section-heading section-heading-actions">
          <div>
            <h2>Room Status</h2>
            <p>Owner/dev/alter permissions can add, edit, lock, unlock, and import rooms. View-only can only read.</p>
          </div>
          {rooms_toolbar(role)}
        </div>
        {room_state_legend()}
        {layout_sort_controls("room-grid", "rooms", ROOMS_PAGE_SIZE)}
        <div class="room-grid" id="room-grid">
          {room_cards}
        </div>
        {layout_pagination("rooms")}
      </section>

      <section class="tab-panel" id="notes" role="tabpanel" hidden>
        <div class="section-heading">
          <h2>Private Notes</h2>
          <p>Keep only what feels okay to write down. This is a protected space, not a demand to document everything.</p>
        </div>
        {notes_access}
      </section>

      {customize_panel(role)}

      {add_room_dialog(role)}
      {pk_import_dialog(role)}
    </section>
    """
    return render_page("The Mansion", body, authenticated=True, role=role)


class MansionHandler(BaseHTTPRequestHandler):
    server_version = "MansionSite/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        if os.environ.get("QUIET_LOGS") != "1":
            super().log_message(fmt, *args)

    def send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str = "text/html; charset=utf-8",
        private: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if private:
            self.send_header("Cache-Control", "no-store, max-age=0")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, target: str) -> None:
        self.send_response(303)
        self.send_header("Location", target)
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()

    def current_session(self) -> str | None:
        clean_sessions()
        raw_cookie = self.headers.get("Cookie", "")
        jar = cookies.SimpleCookie(raw_cookie)
        morsel = jar.get(SESSION_COOKIE)
        if not morsel:
            return None
        token = morsel.value
        session = SESSIONS.get(token)
        if not session:
            return None
        if float(session["created"]) < now() - SESSION_TTL_SECONDS:
            SESSIONS.pop(token, None)
            return None
        return token

    def session_role(self) -> str | None:
        token = self.current_session()
        if not token:
            return None
        session = SESSIONS.get(token)
        if not session:
            return None
        return str(session.get("role", "viewer"))

    def authenticated(self) -> bool:
        return self.current_session() is not None

    def set_session_cookie(self, token: str) -> None:
        cookie = cookies.SimpleCookie()
        cookie[SESSION_COOKIE] = token
        cookie[SESSION_COOKIE]["httponly"] = True
        cookie[SESSION_COOKIE]["samesite"] = "Strict"
        cookie[SESSION_COOKIE]["path"] = "/"
        cookie[SESSION_COOKIE]["max-age"] = str(SESSION_TTL_SECONDS)
        if os.environ.get("COOKIE_SECURE", "1") == "1":
            cookie[SESSION_COOKIE]["secure"] = True
        for morsel in cookie.values():
            self.send_header("Set-Cookie", morsel.OutputString())

    def clear_session_cookie(self) -> None:
        cookie = cookies.SimpleCookie()
        cookie[SESSION_COOKIE] = ""
        cookie[SESSION_COOKIE]["path"] = "/"
        cookie[SESSION_COOKIE]["max-age"] = "0"
        cookie[SESSION_COOKIE]["httponly"] = True
        cookie[SESSION_COOKIE]["samesite"] = "Strict"
        if os.environ.get("COOKIE_SECURE", "1") == "1":
            cookie[SESSION_COOKIE]["secure"] = True
        for morsel in cookie.values():
            self.send_header("Set-Cookie", morsel.OutputString())

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/static/"):
            self.serve_static(path)
            return
        if path == "/login":
            if self.authenticated():
                self.redirect("/")
            else:
                self.send_bytes(200, login_page())
            return
        if path == "/":
            role = self.session_role()
            if not role:
                self.redirect("/login")
                return

            query = parse_qs(urlparse(self.path).query)
            rooms_page = int(query.get("rooms_page", ["1"])[0] or "1")
            map_page = int(query.get("map_page", ["1"])[0] or "1")

            self.send_bytes(200, dashboard_page(role, rooms_page=rooms_page, map_page=map_page), private=True)
            return

        self.send_bytes(404, render_page("Not Found", "<h1>Not found</h1>"))

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/login":
            self.handle_login()
            return
        if path == "/logout":
            token = self.current_session()
            if token:
                SESSIONS.pop(token, None)
            self.send_response(303)
            self.clear_session_cookie()
            self.send_header("Location", "/login")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.end_headers()
            return
        if path == "/rooms":
            self.handle_add_room()
            return
        if path == "/rooms/update":
            self.handle_update_room()
            return
        if path == "/pluralkit/import":
            self.handle_pluralkit_import()
            return
        self.send_bytes(404, render_page("Not Found", "<h1>Not found</h1>"))

    def read_form(self, max_bytes: int = 8192) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(min(length, max_bytes)).decode("utf-8", "replace")
        return parse_qs(body)

    def require_manager(self) -> str | None:
        role = self.session_role()
        if not role:
            self.redirect("/login")
            return None
        if not can_manage_rooms(role):
            self.send_bytes(
                403,
                render_page(
                    "Viewing Only",
                    "<h1>Viewing only</h1><p>This password can look around, but it cannot add, edit, import, lock, or unlock rooms.</p>",
                    authenticated=True,
                    role=role,
                ),
                private=True,
            )
            return None
        return role

    def handle_login(self) -> None:
        key = client_key(self)
        if is_locked_out(key):
            self.send_bytes(
                429,
                login_page("Too many attempts. The lock needs a few minutes before trying again."),
                private=True,
            )
            return

        fields = self.read_form(4096)
        password = fields.get("password", [""])[0]

        credential = verify_password(password)
        if not credential:
            record_failed_login(key)
            self.send_bytes(401, login_page("That password did not open the door."), private=True)
            return

        clear_failed_logins(key)
        token = secrets.token_urlsafe(32)
        SESSIONS[token] = {
            "created": now(),
            "ip": key,
            "role": credential["role"],
            "permissions": credential["permissions"],
        }
        self.send_response(303)
        self.set_session_cookie(token)
        self.send_header("Location", "/")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()

    def handle_add_room(self) -> None:
        role = self.require_manager()
        if not role:
            return

        fields = self.read_form()
        name = fields.get("name", [""])[0].strip()[:100]
        state = fields.get("state", ["unlocked"])[0].strip()
        note = fields.get("note", [""])[0].strip()[:4000]

        if not name or not note:
            self.send_bytes(
                400,
                render_page(
                    "Missing Room Info",
                    "<h1>Missing room info</h1><p>A room needs a name and a note before it can be added.</p>",
                    authenticated=True,
                    role=role,
                ),
                private=True,
            )
            return

        if state not in ROOM_STATES:
            state = "unlocked"

        ROOMS.append({"name": name, "state": state, "note": note, "source": "manual"})
        save_rooms()
        self.redirect("/")

    def handle_update_room(self) -> None:
        role = self.require_manager()
        if not role:
            return

        fields = self.read_form()
        try:
            index = int(fields.get("index", ["-1"])[0])
        except ValueError:
            index = -1
        if index < 0 or index >= len(ROOMS):
            self.send_bytes(
                404,
                render_page(
                    "Room Not Found",
                    "<h1>Room not found</h1><p>That room is not in the saved mansion list.</p>",
                    authenticated=True,
                    role=role,
                ),
                private=True,
            )
            return

        action = fields.get("action", ["save"])[0]
        if action == "delete":
            ROOMS.pop(index)
            save_rooms()
            self.redirect("/")
            return

        name = fields.get("name", [""])[0].strip()[:100]
        state = fields.get("state", ["unlocked"])[0].strip()
        note = fields.get("note", [""])[0].strip()[:4000]
        if action == "unlock":
            state = "unlocked"
        elif action == "dormant":
            state = "internally locked"
        elif action == "force":
            state = "external lock"
        if state not in ROOM_STATES:
            state = "unlocked"
        if not name or not note:
            self.send_bytes(
                400,
                render_page(
                    "Missing Room Info",
                    "<h1>Missing room info</h1><p>A room needs a name and details before saving.</p>",
                    authenticated=True,
                    role=role,
                ),
                private=True,
            )
            return

        room = ROOMS[index]
        room["name"] = name
        room["state"] = state
        room["note"] = note
        save_rooms()
        self.redirect("/")

    def handle_pluralkit_import(self) -> None:
        role = self.require_manager()
        if not role:
            return

        fields = self.read_form()
        token = fields.get("token", [""])[0].strip()
        system_ref = fields.get("system_ref", ["@me"])[0].strip() or "@me"
        if not token:
            self.send_bytes(
                400,
                render_page(
                    "Missing Token",
                    "<h1>Missing token</h1><p>PluralKit import needs a system token.</p>",
                    authenticated=True,
                    role=role,
                ),
                private=True,
            )
            return

        try:
            members = fetch_pluralkit_members(token, system_ref)
            added, updated, skipped = upsert_pk_rooms(members)
        except urlerror.HTTPError as exc:
            message = f"PluralKit returned HTTP {exc.code}. Check the token, system ref, and member privacy."
            self.send_bytes(
                502,
                render_page("PluralKit Import Failed", f"<h1>Import failed</h1><p>{html.escape(message)}</p>", authenticated=True, role=role),
                private=True,
            )
            return
        except (urlerror.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            message = f"Could not import from PluralKit: {exc}"
            self.send_bytes(
                502,
                render_page("PluralKit Import Failed", f"<h1>Import failed</h1><p>{html.escape(message)}</p>", authenticated=True, role=role),
                private=True,
            )
            return

        self.send_bytes(
            200,
            render_page(
                "PluralKit Imported",
                f"<h1>PluralKit import complete</h1>"
                f"<p>PluralKit returned <strong>{len(members)}</strong> members.</p>"
                f"<ul>"
                f"<li><strong>{added}</strong> new rooms added</li>"
                f"<li><strong>{updated}</strong> existing rooms refreshed</li>"
                f"<li><strong>{skipped}</strong> skipped (missing names)</li>"
                f"</ul>"
                f"<p><a href=\"{app_path('/')}\">Back to the mansion</a></p>",
                authenticated=True,
                role=role,
            ),
            private=True,
        )

    def serve_static(self, path: str) -> None:
        relative = path.removeprefix("/static/").strip("/")
        file_path = (STATIC / relative).resolve()
        if not str(file_path).startswith(str(STATIC.resolve())) or not file_path.is_file():
            self.send_bytes(404, b"Not found", "text/plain")
            return

        content_types = {
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".json": "application/json; charset=utf-8",
        }
        self.send_bytes(
            200,
            file_path.read_bytes(),
            content_types.get(file_path.suffix, "application/octet-stream"),
        )


def run(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), MansionHandler)
    print(f"Mansion site running at http://{host}:{port}")
    print("Set OWNER_PASSWORD_HASH and VIEWER_PASSWORD_HASH before sharing this anywhere public.")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Private DID/OSDD personal system site.")
    default_host = os.environ.get("HOST")
    if not default_host:
        default_host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    parser.add_argument("--host", default=default_host)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--hash-password", action="store_true")
    args = parser.parse_args()

    if args.hash_password:
        password = input("Password to hash: ")
        print(make_password_hash(password))
        return

    run(args.host, args.port)


if __name__ == "__main__":
    main()
