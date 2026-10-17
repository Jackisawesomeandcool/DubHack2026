# Haul — AI fashion haul curator

Every fit opens as a completely random outfit of real, currently listed products with their real
product photos. Type a piece in the finder and a row of real options appears above it: press **+**
on an option to add it to the board (up to 10 pieces), or select a piece on the board first and
click an option to swap it in — the new piece takes the old one's spot. Each prompt is kept as a
small speech bubble beside the board; click one to bring its options back. Drag pieces anywhere to
rearrange them. Hover a piece for its price, click it for name / brand / stock, a direct link to the
listing, and remove. Keep up to five fits and share the haul — positions included — as a read-only
link; guests get the same popup and listing link.

**Swapping, Pinterest-style.** Click a piece: alternatives in the same category load into the tray,
and ‹ › arrows appear on the piece. Each arrow press (or clicking a tray option) *tries* that product
in place. Press **keep** to commit; **undo** or simply clicking away drops the change.

**Images are real product cutouts.** Every photo comes from the product's own listing page. Grok's
vision picks a photo that shows only the item — on-model shots with a person are rejected — and
`rembg` removes the background, so each piece is a transparent PNG. Products without a usable
product-only photo are dropped. Nothing is generated or drawn.

Two pages only: `/` (creator) and `/h/<id>` (shared guest view).

## Stack

- **Frontend:** React + Vite, plain JavaScript and custom CSS — `frontend/`
- **Backend:** Python 3.10+ — `backend/` (standard library, plus `rembg` for background removal)
- **AI:** Grok (xAI) via the Python backend. The API key is read from `backend/.env` and never reaches the browser.

## Run locally

Two terminals.

**1. Backend (port 8000)**

```bash
cd backend
pip install -r requirements.txt   # rembg + onnxruntime (~180 MB model downloads on first run)
cp .env.example .env              # add your XAI_API_KEY
python3 server.py
```

**2. Frontend (port 5173)**

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### How products are found

With `XAI_API_KEY` set, the backend calls the xAI Responses API with the `web_search` tool
(filtered to `ALLOWED_DOMAINS`, default `nike.com`) and a strict JSON schema. Grok searches the
store for real, currently listed products matching the request and returns each one's product
page URL. The backend then opens that page and pulls the retailer's own
product photo (`og:image`, Twitter card, or JSON-LD `Product.image`), verifies it serves an image,
and sends it to the UI. Every visual comes directly from the listing site.

**Cutout pipeline.** For each product the backend gathers candidate photos (the page's `og:image`,
JSON-LD images, and the one Grok saw), asks Grok (vision) which one shows only the product with no
person, then runs `rembg` (isnet) to strip the background and trims the result. Cutouts are cached
in `backend/data/cutouts/` and served at `/cutouts/<id>.png`; each source photo is processed once.
Without `rembg` installed the server warns at startup and falls back to the chosen photo as-is.

**Random fits are pre-built.** On startup the backend builds a small pool of complete random fits in
the background (stored in `backend/data/fits.json`), so `GET /api/random-fit` returns instantly and
the pool refills after each one is used. Only the very first load on a fresh install waits for a live
search (~10–40 s). Finder searches run live and show a shimmer row while they work.

An xAI key is required; there is no offline mode.

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
