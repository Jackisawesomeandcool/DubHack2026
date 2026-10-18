# Haul — AI fashion haul curator

Build outfits ("hauls") from real, currently listed clothing. Every haul opens as a random outfit of
product cutouts on a board. Describe what you want in the finder ("black hoodie under $80", "cozy fall
outfit", "shoes under $30") and a row of matching products appears: press **+** to add one to the board
(up to 10 pieces), or select a piece first and click an option to swap it in. Drag pieces to rearrange,
hover for the price, click for name / brand / stock and a link to the listing.

## Features

- **Hauls:** up to five boards, each with its own prompt history; switching boards plays a sweep animation.
- **Search bar:** understands budget, category, brand and color ("under $50", "adidas jacket", "black") as hard
  filters, and moods ("fall athletic", "comfortable clothes") through an AI ranker (keyword ranking without a key).
  When nothing fits the budget it says so and offers the closest-priced items ("No shoes under $30 — the closest is $35").
- **Swapping:** click a piece, then try alternatives in place with the ‹ › arrows; **keep** commits, clicking away undoes.
- **Favorites:** star listings, view them in the tray, newest first.
- **Share:** send one or several hauls as a read-only link (`/h/<id>`), positions included.
- **Accounts:** sign up / log in to keep favorites, hauls and search history across devices.
- **Color themes:** Studio, Midnight, Maroon, Blush, Sky and Sage; the Theme button sits left of Share and the choice is remembered per browser.
- **Models toggle:** product-only cutouts (default) or on-model photos where available.

Pages: `/` (creator, with login) and `/h/<id>` (shared guest view).

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React 18 + Vite 5, plain JavaScript, one hand-written stylesheet driven by CSS variables (themes) — `frontend/` |
| Backend | Python 3.10+ standard-library HTTP server (`backend/server.py`), Pillow for images — `backend/` |
| Catalog | SQLite (`backend/data/catalog.sqlite`): products, cached searches, hand-removed items, review marks |
| Accounts | Separate SQLite (`backend/data/users.sqlite`), scrypt password hashes, bearer-token sessions |
| AI (optional) | Google Gemini (default) or xAI Grok, only for ranking picks, photo choice and product colors. Search works without any key |
| Image checks | Local models via onnxruntime, no key: YOLOX-tiny person detector and U2Net cloth segmentation (downloaded on first use) |

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

Open http://localhost:5173. On start the backend loads the shared dataset (below), so the catalog is ready
immediately: no scraping and no key needed.

Production-style single process: `cd frontend && npm run build`, then `python3 backend/server.py` serves
`frontend/dist` and `/api` on :8000.

## How it works

**Catalog-only search.** Every product shown comes from the local catalog and already has a finished cutout.
There is no live web search at request time.

```
prompt ─ intent.py ─▶ hard constraints (price, category, brand, color)
       ─ catalog.py ─▶ every in-stock product within them
       ─ ranker.py ─▶ AI picks the best matches (keywords if no key)
       ─ finder.py ─▶ streamed to the UI; if the budget empties the pool: a reason + closest-priced items
```

- `intent.py`: regex parsing of the hard filters. One predicate (`matches`) that every result must pass.
- `ranker.py`: the AI sees compact numbered lines (brand, name, price, category, color) and returns numbers, so it can
  only pick real products. Any AI error falls back to keyword ranking.
- `colors.py`: reads each product's color from its cutout (pixel pass, then Gemini vision when a key is set);
  results are shared through the dataset.
- `fits.py`: pre-builds random outfits for the starting board.
- `stock.py`: background stock re-check of listings; out-of-stock products are not served.

## The catalog

About 550 products from Nike, Stüssy, Uniqlo and Brandy Melville (tops, bottoms, outerwear, shoes, bags,
headwear, accessories). Team/college merch is excluded by default. Brandy Melville adds women's tops and bottoms.

**Shared dataset.** `backend/dataset/` (catalog + cutout images) is committed to git, so a teammate only needs
`git pull` and to start the backend. Details, rules and conflict handling: [docs/DATASET.md](docs/DATASET.md).

```bash
git config core.hooksPath .githooks   # once per clone: commits refresh backend/dataset automatically
python3 backend/dataset.py status     # how local and shared differ
python3 backend/dataset.py export     # local catalog -> backend/dataset/
python3 backend/dataset.py resolve    # finish a merge that conflicted on catalog.json
```

**Adding products** (run from `backend/`, one tool at a time, with the server stopped):

```bash
python3 ingest_sites.py --sites stussy,uniqlo,brandy --categories top,bottom --per-category 40 --dry-run
python3 ingest_sites.py --sites brandy --categories top,bottom --per-category 40
python3 ingest_sitemap.py --categories top,bottom --per-category 40      # Nike (merch: --merch none|some|all)
```

Both scrapers skip products you already have, remember products with no usable photo, and can be split between
teammates with `--shard 1/2`.

**Photo quality.** Retailer photos are often on a model, so each product is cut down to just the garment
(cloth segmentation; head, hands and legs removed) or dropped if it can't be cropped cleanly.

```bash
python3 audit_catalog.py --tidy              # drop stray logos/specks, trim margins
python3 audit_catalog.py --recrop --limit 10 # re-cut cutouts that still show neck/hands/legs
python3 view_catalog.py                      # review UI on :8765: ✕ removes a product for everyone
```

Removing with ✕ is permanent and shared: the product is put on `removed.json`, deleted on every teammate's next
start, and skipped by the scrapers.

## Configuration

`backend/.env` (gitignored; copy from `.env.example`). Nothing is required.

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY`, `GEMINI_MODEL` | AI ranking, vision photo choice, product colors |
| `XAI_API_KEY` | use xAI Grok instead of Gemini (leave the Gemini key empty) |
| `ALLOWED_DOMAINS` | store restriction in the AI prompts (default `nike.com`) |
| `PORT`, `HOST` | server address (default 127.0.0.1:8000) |
| `PHOTOROOM_API_KEY`, `REMOVEBG_API_KEY`, `CUTOUT_PROVIDER` | optional paid background removal for new scrapes |

Keys are read only by the Python backend and never reach the browser.

## API

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/random-fit` | a pre-built random outfit; `?models=1` for on-model photos |
| POST | `/api/suggest` | `{prompt, category?, exclude?, models?}`; NDJSON stream: `{items}`, then `{reason, closest}` when nothing matched, then `{done}` |
| POST | `/api/share` · GET `/api/share/<id>` | create / read a shared link (`{fits}`) |
| POST | `/api/seen` | note products in play so their stock is re-checked |
| POST | `/api/auth/signup`, `/api/auth/login`, `/api/auth/logout` · GET `/api/auth/me` | accounts |
| GET / PUT | `/api/me/state` | signed-in favorites, hauls and search history |
| GET | `/api/health` | cutout / catalog readiness |

Product shape: `name`, `brand`, `price`, `image`, `stock` (`in_stock` / `out_of_stock`), `category`, `url`
(the listing page), plus `x` / `y` (board position, percent) in hauls.

## Hosting (Vercel, free)

The site deploys to Vercel's free Hobby plan with a free Upstash Redis for accounts and share links: static React build,
and a Python `backend` service (`backend/vercel_app.py`, an adapter around `backend/server.py`) that serves `/api` and the product images. Steps and limits are in
[docs/DEPLOY.md](docs/DEPLOY.md). Locally nothing changes.

## Repo layout

```
backend/   server.py (HTTP) · catalog.py · intent.py · ranker.py · finder.py · fits.py · colors.py · stock.py
           auth.py · auth_kv.py · kv.py (hosted accounts on Upstash) · store.py (shares) · llm.py / gemini.py / grok.py · cutouts.py · bgremove.py · images.py
           quality.py · garment.py · people.py (photo checks) · seed.py + seed/ · dataset.py + dataset/
           ingest_sites.py · ingest_sitemap.py · audit_catalog.py · view_catalog.py · test_search.py
vercel.json  two Vercel services (frontend + backend) — see docs/DEPLOY.md · backend/vercel_app.py = ASGI entry
frontend/  src/App.jsx · components/ (board, tray, prompt bar, share, account, theme) · lib/ (api, haul, theme, ...) · styles.css
docs/      DATASET.md · CATALOG_AND_LIVE_AI.md (history of the earlier live-search design)
```

## Tests

```bash
python3 backend/test_search.py    # offline: no network, no key; runs against the shared dataset
```

## Notes

- Product photos and listings belong to their retailers. The scrapers are rate-limited and meant for hackathon-scale
  use; do not redistribute the images.
- Nothing is generated or drawn: every visual is a real product photo with its background removed.
