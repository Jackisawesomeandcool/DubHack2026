# FitCheck — build outfits from real clothes, then buy them

**Live demo: https://dubhack2026.vercel.app/**

Pinterest outfit boards look great, but the pieces in them are dead ends: no name, no price, no stock status, no
store. **FitCheck keeps the board and adds the shopping.** Every piece is a real product listing with its price, a
live stock status and a link to the store. Describe what you want ("cozy fall fit", "black hoodie under $80"), drop the
results onto a board, arrange them, share the fit as one link, and jump straight to each store page.

Built for DubHacks 2026.

## What makes it different

- **A board where every item is shoppable.** Name, brand, price, in-stock status and a direct store link on every piece,
  plus a *Store links* window with the whole fit and its total.
- **AI that explains itself.** Gemini picks pieces and each one carries a one-line reason ("Suggested by Gemini!"), so
  suggestions aren't a black box. A switch turns the AI off for instant keyword results.
- **Clothes only, no models.** Product photos are cleaned up automatically so you see the garment, not a person.
- **Built to be trusted.** Visible AI labels, stock re-checks, keys that never reach the browser, and *Clear my data* /
  *Delete account* in one click.

## Features

- **Fits:** up to five boards, each with its own prompt history; switching boards plays a sweep animation.
- **Search bar:** understands budget, category, brand and color ("under $50", "adidas jacket", "black") as hard
  filters, and moods ("fall athletic", "comfortable clothes") through an AI ranker (keyword ranking without a key).
  When nothing fits the budget it says so and offers the closest-priced items ("No shoes under $30 — the closest is $35").
- **Swapping:** click a piece, then try alternatives in place with the ‹ › arrows; **keep** commits, clicking away undoes.
- **Favorites:** star listings, view them in the tray, newest first.
- **Share:** send one or several fits as a read-only link (`/h/<id>`), positions included.
- **Accounts:** sign up / log in to keep favorites, fits and search history across devices.
- **AI-powered fits switch:** the pill in the search bar turns Gemini ranking on or off (off = instant keyword results).
  With it on, instant keyword results show first and Gemini's picks (the model reads ~80 candidates and names 10, each with a
  one-line reason) replace the top of the list a moment later.
- **Why this piece:** pieces Gemini picked carry a small ✦ in the results tray; clicking one on the board shows
  "Suggested by Gemini!" with a one-line reason. The note travels with shared links.
- **Store links:** the *Store links* window (next to Share) lists every piece on the board with its store, price and total, plus *Copy list*.
- **Privacy controls:** the account menu has *Clear my data* (keeps the account) and *Delete account*; both confirm first.
  Links already shared stay viewable.
- **Color themes:** Studio, Midnight, Maroon, Blush, Sky and Sage; the choice is remembered per browser.
- **Models toggle:** product-only cutouts (default) or on-model photos where available.

Pages: `/` (creator, with login) and `/h/<id>` (shared guest view). Fits can be explored as a guest too.

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React 18 + Vite 5, plain JavaScript, one hand-written stylesheet driven by CSS variables (themes) — `frontend/` |
| Backend | Python 3.10+ standard-library HTTP server (`backend/server.py`), Pillow for images — `backend/` |
| Catalog | SQLite: products, cached searches, hand-removed items, review marks |
| Accounts | SQLite locally (scrypt password hashes, bearer-token sessions); Upstash Redis when hosted |
| AI (optional) | Google Gemini (default) or xAI Grok, only for ranking picks and photo choice. Search works without any key |
| Image checks | Local models via onnxruntime, no key: YOLOX-tiny person detector and U2Net cloth segmentation |
| Hosting | Vercel (free Hobby plan) + free Upstash Redis |

## Quick start

Needs Python 3.10+ and Node 18+. Two terminals.

```bash
# 1. backend (port 8000)
cd backend
pip install -r requirements-local.txt
cp .env.example .env            # optional: add GEMINI_API_KEY
python3 server.py

# 2. frontend (port 5173)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. On start the backend loads the shared dataset, so the catalog is ready immediately: no
scraping and no key needed.

Production-style single process: `cd frontend && npm run build`, then `python3 backend/server.py` serves
`frontend/dist` and `/api` on :8000.

## How it works

**Catalog-only search.** Every product shown comes from the local catalog and already has a finished cutout.

```
prompt ─ intent.py ─▶ hard constraints (price, category, brand, color)
       ─ catalog.py ─▶ every in-stock product within them
       ─ ranker.py ─▶ AI picks the best matches (keywords if no key)
       ─ finder.py ─▶ streamed to the UI; if the budget empties the pool: a reason + closest-priced items
```

- `intent.py`: regex parsing of the hard filters. One predicate (`matches`) that every result must pass.
- `ranker.py`: the AI sees compact numbered lines (brand, name, price, category, color) and returns numbers, so it can
  only pick real products. Any AI error falls back to keyword ranking and the app tells the shopper.
- `colors.py`: reads each product's color from its cutout pixels.
- `fits.py`: pre-builds random outfits for the starting board.
- `stock.py`: background stock re-check of listings; out-of-stock products are not served.

## The catalog

About 550 products from Nike, Stüssy, Uniqlo and Brandy Melville (tops, bottoms, outerwear, shoes, bags,
headwear, accessories). Team/college merch is excluded from new scrapes.

**Photo pipeline.** Retailer photos are often on a model, and we wanted product-only images. For every product:

1. Pick the best photo. A **YOLOX-tiny person detector** (a YOLO-family model, run through onnxruntime) is combined with a
   **skin-tone check**. Requiring both to agree fixed the detector calling flat hoodies "people" and skin tone alone
   missing dark clothes on dark backgrounds. The rule was tuned on 391 real cutouts; it has not had a formal fairness
   evaluation across skin tones.
2. If a person is still in the shot, **U2Net cloth segmentation** keeps only the garment and drops head, skin, hands and
   shoes. A cut that is too small or fragmented is rejected rather than shown.
3. Remove the background: a free flood-fill for flat product shots, **rembg (isnet)** otherwise.
4. Read the product's color from the cutout's pixels. No API call is needed.

All of this runs locally with no key.

**Shared dataset.** `backend/dataset/` (catalog + cutout images) is committed to git, so a teammate only needs
`git pull` and to start the backend. Details: [docs/DATASET.md](docs/DATASET.md).

**Adding products** (run from `backend/`, one tool at a time, with the server stopped):

```bash
python3 ingest_sites.py --sites stussy,uniqlo,brandy --categories top,bottom --per-category 40 --dry-run
python3 ingest_sitemap.py --categories top,bottom --per-category 40      # Nike
```

## Configuration

`backend/.env` (gitignored; copy from `.env.example`). Nothing is required.

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY`, `GEMINI_MODEL` | AI ranking |
| `COLOR_VISION=1` | optional Gemini double-check of product colors (off by default: it uses up the free key's quota) |
| `XAI_API_KEY` | use xAI Grok instead of Gemini (leave the Gemini key empty) |
| `PORT`, `HOST` | server address (default 127.0.0.1:8000) |

Keys are read only by the Python backend and never reach the browser. Run `python3 backend/check_ai.py` to confirm your
Gemini key works.

## API

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/random-fit` | a pre-built random outfit |
| POST | `/api/suggest` | `{prompt, category?, exclude?, models?, ai?}`; NDJSON stream of results |
| POST | `/api/share` · GET `/api/share/<id>` | create / read a shared link |
| POST | `/api/auth/signup`, `/login`, `/logout` · GET `/api/auth/me` | accounts |
| POST | `/api/auth/clear-data`, `/api/auth/delete-account` | wipe saved data, or remove the account |
| GET / PUT | `/api/me/state` | signed-in favorites, fits and search history |
| GET | `/api/health` | readiness |

## Hosting

Live at **https://dubhack2026.vercel.app/** on Vercel's free Hobby plan: a static React build plus a Python `backend`
service, with a free Upstash Redis for accounts and share links. Steps and limits are in
[docs/DEPLOY.md](docs/DEPLOY.md).

## Trust & responsibility

- **AI is labelled and optional.** Gemini-picked pieces are marked ✦ and explain themselves; the "AI-powered fits" switch
  turns it off. If Gemini fails or runs out of quota, the app says so and falls back to keyword results.
- **Gemini only sees the search text and a short product list** (brand, name, price, category, color), never account data,
  and can only pick products that exist: every pick is checked against the hard filters.
- **Your data is yours.** Passwords are scrypt-hashed; keys stay on the server. The account menu has *Clear my data* and
  *Delete account* (links already shared stay viewable).
- **Real products only.** Nothing is generated: every visual is a retailer product photo with its background removed, and
  stock is re-checked so out-of-stock items aren't served.

## Known limits

- The catalog is a snapshot (about 550 products). With an API key that allows live retrieval the same pipeline would serve
  live listings; that is the main next step.
- The free Gemini key has a small quota.
- The hosted site streams less smoothly than a local run, so AI results appear all at once.
- A few older team/college merch listings may remain in the dataset.

## Tests

```bash
python3 backend/test_search.py    # offline: no network, no key
```

## Notes

Product photos and listings belong to their retailers. The scrapers are rate-limited and meant for hackathon-scale use;
do not redistribute the images.
