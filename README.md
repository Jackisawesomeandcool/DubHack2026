# Haul — AI fashion haul curator

Every fit opens as a completely random outfit of real, currently listed products with their real
product photos. Type a piece in the finder and a row of real options appears above it: press **+**
on an option to add it to the board (up to 10 pieces), or select a piece on the board first and
click an option to swap it in — the new piece takes the old one's spot. Each prompt is kept as a
small speech bubble beside the board; click one to bring its options back. Drag pieces anywhere to
rearrange them. Hover a piece for its price, click it for name / brand / stock, a direct link to the
listing, and remove. Keep up to five hauls (delete one with the × on its tab) and share — positions included — as a read-only
link; guests get the same popup and listing link.

**Swapping, Pinterest-style.** Click a piece: alternatives in the same category load into the tray,
and ‹ › arrows appear on the piece. Each arrow press (or clicking a tray option) *tries* that product
in place. Press **keep** to commit; **undo** or simply clicking away drops the change.

**Models toggle.** The switch beside the prompt bar decides what gets pulled next: off = product-only
cutouts (no people); on = the item worn on a model is allowed and preferred. It applies to searches,
swap alternatives and new random fits; pieces already on the board are unchanged.

**Images are real product cutouts.** Every photo comes from the product's own listing page. Grok's
vision picks a photo that shows only the item — on-model shots with a person are rejected — and
`rembg` removes the background, so each piece is a transparent PNG. Products without a usable
product-only photo are dropped. Nothing is generated or drawn.

Two pages only: `/` (creator) and `/h/<id>` (shared guest view).

## Stack

- **Frontend:** React + Vite, plain JavaScript and custom CSS — `frontend/`
- **Backend:** Python 3.10+ — `backend/` (standard library, plus `rembg` for background removal)
- **AI:** Google Gemini (default; xAI Grok also supported) via the Python backend. Keys are read from `backend/.env` and never reach the browser.

## Run locally

Two terminals.

**1. Backend (port 8000)**

```bash
cd backend
cp .env.example .env              # add your GEMINI_API_KEY
python3 server.py                 # needs only Pillow (installed automatically if missing)
```

**2. Frontend (port 5173)**

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### How products are found

With `GEMINI_API_KEY` set, live searches that the catalog and nike.com's API can't answer go to
Gemini (`gemini-2.5-flash`) with Google Search grounding, restricted to `ALLOWED_DOMAINS` (default
`nike.com`). It returns real, currently listed products with their product page URLs. (Set
`XAI_API_KEY` instead to use Grok's web search.) The backend then opens that page and pulls the retailer's own
product photo (`og:image`, Twitter card, or JSON-LD `Product.image`), verifies it serves an image,
and sends it to the UI. Every visual comes directly from the listing site.

**Speed: local catalog + nike.com search API.** On startup the backend warms a local catalog of
popular Nike items (dunks, AF1, tech fleece, …) in the background, each stored with its finished
cutout in `backend/data/catalog.sqlite` (SQLite, standard library). Random fits are assembled from the catalog in milliseconds,
swap alternatives and most searches are answered from it instantly, and live searches go to nike.com's
own product-search API first (sub-second; it returns a product-only photo and an on-model photo, so no
vision call is needed) with Gemini (Google Search grounding) as the fallback. Everything that comes back with a
cutout joins the catalog, so the app gets faster the more it's used. Identical searches within an hour
are served from a result cache. A background thread re-checks stock on the oldest-checked listings
(rate-limited, via the page's JSON-LD) and re-checks any product you place on the board; out-of-stock
products are never served.

Seed the catalog in advance (optional, a few minutes):

```bash
cd backend && python3 ingest.py            # product-only cutouts
cd backend && python3 ingest.py --models   # also on-model cutouts
```

**Cutout pipeline.** For each product the backend picks the right photo (nike.com's API hands over a
product-only and an on-model photo directly; otherwise Gemini's vision chooses among the listing's
photos, sent inline) and removes the background in the cheapest tier that works:

1. **flat-key** — product photos on a flat light backdrop (Nike's product shots, most flat lays):
   flood-filled from the edges and keyed transparent. ~80 ms, free, Pillow only. This covers the
   default product-only mode almost entirely.
2. **API** — Photoroom or remove.bg if `PHOTOROOM_API_KEY` / `REMOVEBG_API_KEY` is set in `.env`
   (~1–2 s per image, paid). Used for on-model shots and busy backgrounds.
3. **local rembg** — free, slow, heavy install; only installed on first need if no API key is set.

Cutouts are cached in `backend/data/cutouts/` and served at `/cutouts/<id>.png`; every photo is
processed once, so API usage stays at one call per new product.

**Random fits are pre-built.** On startup the backend builds a small pool of complete random fits in
the background (stored in `backend/data/fits.json`), so `GET /api/random-fit` returns instantly and
the pool refills after each one is used. Only the very first load on a fresh install waits for a live
search (~10–40 s). Finder searches stream: the products appear in the tray as soon as Grok finds them (as shimmering placeholders), and each one fills in the moment its cutout is ready.

A Gemini (or xAI) key is required; there is no offline mode.

## Production-style single process

```bash
cd frontend && npm run build
cd ../backend && python3 server.py      # serves frontend/dist and /api on :8000
```

## API

| Method | Path              | Body                        | Returns                       |
|--------|-------------------|-----------------------------|-------------------------------|
| GET    | `/api/random-fit` | —                           | `{"prompt", "items": [...]}`  |
| POST   | `/api/suggest`    | `{"prompt", "category"?, "exclude"?}` | `{"items": [...options], "source"}` |
| POST   | `/api/share`      | `{"fits": [{"items": [...]}]}` | `{"id": "..."}`            |
| GET    | `/api/share/<id>` | —                           | `{"fits": [...]}`             |

Product shape: `name`, `brand`, `price`, `image`, `stock` (`in_stock` / `out_of_stock`),
plus internal `url` (the listing page the image was pulled from), `category`, and `x` / `y`
(board position in percent, saved with shares).
