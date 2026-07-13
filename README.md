# Mansion — headspace room map

A private, password-protected room map for DID/OSDD headspaces. Name your rooms, set lock states (open, unlocked, dormant, force-dormant), take private notes, and optionally import alters from PluralKit.

This repo is a **starter template**. Clone it, make it yours, and host it privately. Your real room data and passwords should stay in **your** copy — not in a public fork.

![The Mansion dashboard with room stats and tab navigation](https://media.discordapp.net/attachments/1523097457687265493/1523826769428349069/k2jx2ktpnr.png?ex=6a556ec5&is=6a541d45&hm=47d12fa737c1e3b4b7d9312cabcf81b08eed0cab2c8efd97992bc5154712a601&=&format=webp&quality=lossless&width=2636&height=1162)

---

## Screenshots

### Map — layout overview

Sort, search, and filter rooms on a visual grid.

![Map tab showing room layout grid with search and state filters](https://media.discordapp.net/attachments/1523097457687265493/1523826768883224766/xt3h9pz8f3.png?ex=6a556ec5&is=6a541d45&hm=4dba3d369272e39f1fcdb647fe93e572f99b029653bd378087b1aae8513a5043&=&format=webp&quality=lossless&width=2636&height=1166)

### Rooms — edit, lock, and import

Manage each room’s state, add new rooms, or import from PluralKit.

![Rooms tab with state legend, room cards, and quick actions](https://media.discordapp.net/attachments/1523097457687265493/1523826768253943918/dmntwhh61r.png?ex=6a556ec4&is=6a541d44&hm=4e9d01aefc5724879589bca572592c1b0f332d74b8b203f77cfa4c8b9eb1baec&=&format=webp&quality=lossless&width=2416&height=1400)

### Notes — private scratch space

Browser-side notes that stay on your device.

![Notes tab with private text area](https://media.discordapp.net/attachments/1523097457687265493/1523826767624933539/4r4fbtf336.png?ex=6a556ec4&is=6a541d44&hm=b74ac524646b65bd596fadec052a4131ffb4727c3c28ef65b3c1c2445f2da010&=&format=webp&quality=lossless&width=2636&height=1192)

### Customize — make it yours

Rename the site, edit login text, and pick your own colors.

![Customize tab with site name fields and color pickers](https://cdn.discordapp.com/attachments/1523097457687265493/1523826767624933539/4r4fbtf336.png?ex=6a4d85c4&is=6a4c3444&hm=c1c1151eac687a7840afd342060f0a57073bdf8fa18b0c8dc7724ffc9cd4ab08&)

---

## What you need

- **Git** — to download and update the project
- **Python 3** — to build the site and set passwords (no extra packages required)
- A place to host the built files (GitHub Pages, Netlify, Cloudflare Pages, your own server, or just open locally)

---

## Get your own copy

### Option A — Clone with Git (recommended)

```bash
git clone https://github.com/YOUR_USERNAME/mansion-blueprint.git
cd mansion-blueprint
```

Replace the URL with wherever you host the repo (your fork, a friend's template, etc.).

### Option B — Download without Git

1. Click **Code → Download ZIP** on GitHub
2. Unzip the folder
3. Open a terminal in that folder for the steps below

> **Tip:** Fork the repo on GitHub first if you want your own copy you can push changes to, without touching the original template.

---

## Try it locally in 2 minutes

The fastest way to see it working — demo passwords included:

```bash
python3 scripts/build-mansion-page.py
```

Then open `mansion.html` in your browser (double-click it, or drag it into a browser window).

| Role | Password | What you can do |
|------|----------|-----------------|
| Owner | `changeme` | Add, edit, lock/unlock rooms, customize colors & name, edit notes |
| View-only | `view-only` | Look around — no editing |

**Change these passwords before sharing the site with anyone.**

---

## Set up for real use

### Step 1 — Choose your passwords

Pick two passwords:

- **Owner** — full control (you, a host alter, etc.)
- **View-only** — trusted people who can look but not edit

Generate secure hashes:

```bash
python3 scripts/hash-password.py owner
# Enter your owner password when prompted — copy the long hash it prints

python3 scripts/hash-password.py viewer
# Same for your view-only password
```

Create your secrets file:

```bash
cp .sharing.env.example .sharing.env
```

Open `.sharing.env` and paste the hashes:

```env
OWNER_PASSWORD_HASH=pbkdf2_sha256$...
VIEWER_PASSWORD_HASH=pbkdf2_sha256$...
```

Apply them to the static site:

```bash
python3 scripts/update-auth-hashes.py
```

### Step 2 — Add your rooms (optional)

Edit `mansion/rooms.json` with your room list, or skip this to keep the five starter rooms (Foyer, Staircase, etc.).

Example room entry:

```json
{
  "name": "Library",
  "state": "unlocked",
  "note": "Quiet room for reading and co-regulation."
}
```

**Room states:** `open` · `unlocked` · `internally locked` (dormant) · `external lock` (force-dormant)

### Step 3 — Build the site

```bash
python3 scripts/build-mansion-page.py
```

This creates `mansion.html` with your rooms baked in.

### Step 4 — Deploy

Upload these to any static host:

- `mansion.html`
- the entire `mansion/` folder (scripts, styles, auth)

**Do not upload** `.sharing.env` — that file stays on your machine only.

Works on GitHub Pages, Netlify, Cloudflare Pages, Neocities, or any web server that serves HTML files.

---

## Customize the look

After signing in with the **owner** password, open the **Customize** tab (see screenshot above) to:

- Rename the site (replace "The Mansion" with your own name)
- Edit login text and taglines
- Change accent and state colors

Changes save in your browser's local storage — great for personalizing your copy on your device.

---

## Run the Python server (optional)

Use this if you want PluralKit import or traditional server sessions instead of the all-in-one static file.

```bash
cp .sharing.env.example .sharing.env
# Fill in your password hashes, then:

export $(grep -v '^#' .sharing.env | xargs)
COOKIE_SECURE=0 python3 -m mansion.app --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

PluralKit import is available from the **Rooms** tab when running this server.

---

## Embed in an existing website

1. Run `python3 scripts/build-mansion-page.py`
2. Copy `mansion.html` and the `mansion/` folder into your site
3. Link to `mansion.html` from your navigation

If your site lives in a subfolder (e.g. `yoursite.com/headspace/`), edit the `static_path` function in `scripts/build-mansion-page.py` so asset paths point to the right place, then rebuild.

---

## How editing works

| Hosting mode | Room edits | Notes | Customize |
|--------------|------------|-------|-----------|
| Static (`mansion.html`) | Saved in browser localStorage | Saved in browser | Saved in browser |
| Python server | Saved to `mansion/data/rooms.json` | Browser localStorage | Browser localStorage |

On static hosting, room changes persist in **that browser only**. Rebuild and redeploy to share room updates across devices.

---

## Keep private — never commit these

| File | Why |
|------|-----|
| `.sharing.env` | Your password hashes |
| `mansion/rooms.json` | Your personal room / alter data |
| `mansion.html` | Built output (may embed your room list) |
| PluralKit tokens | Never stored — used once per import |

These are already listed in `.gitignore`. Double-check before `git push`.

---

## Troubleshooting

**"That password did not open the door."**
- On the static site, make sure you ran `update-auth-hashes.py` after editing `.sharing.env`
- Default demo passwords are `changeme` / `view-only` until you change them

**Page looks unstyled or broken**
- Keep `mansion.html` and the `mansion/` folder together — don't upload only the HTML file
- If hosted in a subfolder, rebuild with corrected paths in `build-mansion-page.py`

**Room edits disappeared on another device**
- Expected on static hosting — edits are per-browser. Rebuild with updated `rooms.json` to sync everywhere.

**Python command not found**
- Try `python` instead of `python3`, or install Python 3 from [python.org](https://www.python.org/downloads/)

---

## License

MIT — see [LICENSE](LICENSE). Use freely, modify, and host your own. No warranty.
