# Mansion — headspace room map (template)

A private, password-gated headspace mansion for DID/OSDD systems. Map rooms, set lock states, and optionally import alters from PluralKit.

This repo is the **public blueprint**. Your personal rooms, passwords, and live data stay in your own private copy — never commit those here.

## What you get

- Login with owner vs view-only passwords
- Room map and room list with state filters
- Room states: open, unlocked, dormant (internally locked), force-dormant (external lock)
- Browser-side edits (saved in localStorage on static hosting)
- Optional PluralKit import when running the Python server locally

## Quick start

### 1. Set your passwords

```bash
python3 scripts/hash-password.py owner
python3 scripts/hash-password.py viewer
```

Copy the output into `.sharing.env` (create from `.sharing.env.example`), then:

```bash
python3 scripts/update-auth-hashes.py
```

Default demo passwords (change these before going live):

| Role | Demo password |
|------|----------------|
| Owner | `changeme` |
| View-only | `view-only` |

### 2. Add your rooms (optional)

Put your room list at `mansion/rooms.json`, or skip this to use the five default starter rooms (Foyer, Staircase, etc.).

**Do not commit real room data to a public repo.**

### 3. Build the static page

```bash
python3 scripts/build-mansion-page.py
```

This writes `mansion.html` (gitignored). Upload `mansion.html`, the `mansion/` folder, and nothing from `.sharing.env` to any static host (GitHub Pages, Cloudflare Pages, Netlify, etc.).

### 4. Open it

Deploy `mansion.html` at your site root or subpath and open it in a browser.

## Local Python server (optional)

For server-side sessions and PluralKit import:

```bash
cp .sharing.env.example .sharing.env
# fill in hashes, then:
export $(grep -v '^#' .sharing.env | xargs)
COOKIE_SECURE=0 python3 -m mansion.app --host 127.0.0.1 --port 8000
```

Or from the `mansion/` package:

```bash
cd mansion && python3 app.py
```

## Embed in an existing site

Copy `mansion.html` plus the `mansion/` folder into your site repo. Link to `mansion.html` from your nav. If your site lives in a subfolder, adjust paths in `scripts/build-mansion-page.py` (`static_path`).

## What never goes in git

- `.sharing.env` — password hashes
- `mansion/rooms.json` — your room / alter data
- `mansion.html` — built output (may contain embedded room JSON)
- PluralKit tokens (never stored by this app)

## License

MIT — see [LICENSE](LICENSE). Use freely, modify, host your own. No warranty.
