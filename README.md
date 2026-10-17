# Haul — AI fashion haul curator

Build an outfit board from real listings. The board opens with empty "+" slots (jacket, top,
bottoms, shoes, bag, hat, accessory). Type a piece or a vibe in the finder and a row of real
product options appears above it; pick one to place it on the board — picking another option for
the same slot swaps it out, Pinterest-style. Click an empty slot to point the finder at that
category. Hover a piece for its price, click it for name / brand / stock (and remove), keep up to
five fits, and share the haul as a read-only link.

Two pages only: `/` (creator) and `/h/<id>` (shared guest view).

## Stack

- **Frontend:** React + Vite, plain JavaScript and custom CSS — `frontend/`
- **Backend:** Python 3.10+ standard library only (no pip installs) — `backend/`
- **AI:** Grok (xAI) via the Python backend. The API key is read from `backend/.env` and never reaches the browser.

## Run locally

Two terminals.

**1. Backend (port 8000)**

```bash
cd backend
cp .env.example .env     # add your XAI_API_KEY (optional, see below)
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

A search takes roughly 10–40 s; the options row shows a shimmer while it runs and the board stays usable.
If Grok or the search fails, the UI shows "couldn't curate that one — try again" — it never
substitutes placeholder items.

### Without an xAI key (UI testing only)

If `XAI_API_KEY` is empty the backend serves a small offline catalog so the interface can be
exercised with no network. Those entries have no listing URLs, so they render as garment cutouts.

## Production-style single process

```bash
cd frontend && npm run build
cd ../backend && python3 server.py      # serves frontend/dist and /api on :8000
```

## API

| Method | Path              | Body                        | Returns                       |
|--------|-------------------|-----------------------------|-------------------------------|
| POST   | `/api/suggest`    | `{"prompt", "category"?, "exclude"?}` | `{"items": [...options], "source"}` |
| POST   | `/api/share`      | `{"fits": [{"items": [...]}]}` | `{"id": "..."}`            |
| GET    | `/api/share/<id>` | —                           | `{"fits": [...]}`             |

Product shape: `name`, `brand`, `price`, `image`, `stock` (`in_stock` / `out_of_stock`),
plus internal `url` (the listing page the image was pulled from), `category` and `color`
(collage placement).
