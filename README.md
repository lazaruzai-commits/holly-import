# Holly Import

Website for **Holly Import** — authorized MG and Maxus dealer in Los Palos
Grandes, Caracas. Static-feeling marketing site backed by a small FastAPI
app that powers an AI chat assistant, lead capture, and service booking.

## Stack

- **FastAPI + Jinja2** for pages and JSON APIs.
- **Vanilla JS** (no framework) for the side-modal chat, model dialogs,
  filters, and compare page. Keeps the page weight light and avoids a
  build step on the VPS.
- **OpenRouter** (Kimi K2 by default) for free-text chat replies.
- **Telegram Bot** ([@HollyImportBot](https://t.me/HollyImportBot)) for
  forwarding every captured lead, service booking, and chat turn to a
  human.
- **CSV** persistence under `leads/` (gitignored) — a small,
  zero-dependency record of every lead and service request, plus a
  full chat transcript log.

## Pages

| Path | Template | Purpose |
|------|----------|---------|
| `/` | `inicio.html` | Hero, featured models, promo card, value props |
| `/modelos` | `modelos.html` | Filterable grid (MG/Maxus, pasajeros/comerciales, promo) |
| `/comparar` | `comparar.html` | Pick a Holly model + a competitor → side-by-side |
| `/servicio` | `servicio.html` | Taller info + CTA to chat in `servicios` flow |
| `/promocion` | `promocion.html` | Asegúrate con 500 landing |
| `/contacto` | `contacto.html` | Address, hours, contact form |

## Chat agent

A side-modal slides in from the right on every page. The first prompt is
two chips: **Compra** and **Servicios**.

- **Compra** → MG/Maxus → model picker → "should an asesor contact you?"
  → mini form (name, phone, contact preference). Default contact
  preference is "Llamada + Texto"; alternative is "Solo texto".
- **Servicios** → "schedule a service?" → date picker + AM/PM + form.
- After either flow finishes, the user can switch to free text. Free
  text hits OpenRouter; the system prompt brands the bot as a Holly
  Import advisor and feeds it the live model lineup.

Every form submission and every free-text turn is forwarded to the
Telegram bot with the session ID, so a human can pick up the
conversation off-channel.

## Models data

`data/models.json` is the source of truth for the lineup:

- 10 MG models (MG 3, MG 3 Hybrid+, MG 5, MG GT, MG ZS, MG ZS EV, MG RX5, MG RX8, MG RX9, Cyberster)
- 9 Maxus models (D60, D90, T60, T90, G10, V80, Serie C, Serie S, Serie H)

Specs are starting estimates from the public mgvzla.com / maxusve.com
listings. **Verify and update** before going public — the dealership
will know the exact Venezuelan-market trim specs.

`data/competitors.json` defines the competitor catalog and the per-pair
talking points used by the Compare page (`vsHolly.summary`,
`vsHolly.puntos`, `vsHolly.relativeBadge`).

## Setup (local dev)

```bash
git clone <repo> holly && cd holly
python -m venv .venv
.venv/Scripts/activate          # Windows
# or: source .venv/bin/activate # macOS/Linux
pip install -r requirements.txt
cp .env.example .env             # then fill in the keys
python scripts/fetch_images.py   # downloads model imagery
uvicorn app:app --reload --port 8000
```

Then open <http://localhost:8000>.

## Required environment variables

See `.env.example`. The site will boot without them, but:

- Without `OPENROUTER_API_KEY`, free-text chat falls back to a
  graceful "an asesor will contact you" message.
- Without `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, leads are still
  saved to CSV, but the human won't be notified in real time.

To get `TELEGRAM_CHAT_ID`: send `/start` to
[@HollyImportBot](https://t.me/HollyImportBot), then visit
`https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the
`"chat":{"id": ...}` value.

## Image attribution

Holly Import is an authorized dealer of MG and Maxus. The hero shots
under `static/img/models/` are downloaded from `mgvzla.com` and
`maxusve.com`, the official Venezuelan brand sites, via
`scripts/fetch_images.py`. The manifest at
`static/img/models/_manifest.json` records the original source URL for
each file. Images are **not** committed to git — the script repopulates
them on every fresh checkout.

## Deploy

`deploy/setup.sh` mirrors the Kairos pattern: subpath under
`andyluciani.com/holly/`, systemd unit `andyluciani-holly.service`,
listens on `127.0.0.1:3003`, fronted by nginx.

```bash
sudo -u lazaruz git clone https://github.com/<owner>/holly-import.git /var/www/holly
sudo bash /var/www/holly/deploy/setup.sh
sudo -u lazaruz nano /var/www/holly/.env   # fill in keys
sudo systemctl restart andyluciani-holly
```

When the customer's domain is ready (e.g. `hollyimport.com`), point its
DNS A record at the server, add a second nginx `server { server_name
hollyimport.com; }` block that `proxy_pass`es to the same
`127.0.0.1:3003`, and unset `APP_ROOT_PATH` for that vhost so URLs
resolve at root. The same systemd unit can serve both endpoints during
the cutover.

## CSV files

Written to `leads/` (gitignored):

- `leads.csv` — purchase-intent captures (Compra flow, Solicitar precio dialog)
- `services.csv` — taller bookings (Servicios flow)
- `chat_log.csv` — every chat turn (user + assistant) for transcript review

## Health check

```
GET /api/health
→ { "ok": true, "models": 19, "competitors": 39,
    "telegram_configured": true, "openrouter_configured": true }
```

## Things to tighten before launch

- Real model specs (verify against actual stock in Caracas).
- Real prices for the Compare page badges (currently "relative" badges
  only — no absolute numbers used).
- Final "Asegúrate con 500" terms (paraphrased here from the public
  promo page; legal/compliance copy should come from the dealership).
- Hero photography that matches Holly Import's exact stock colors and
  trims.
- `SITE_PHONE` and `SITE_WHATSAPP` in `.env`.
