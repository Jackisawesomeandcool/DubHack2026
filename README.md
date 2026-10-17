# Haul — AI fashion haul curator

Type a fashion prompt, get a cohesive haul of real clothing laid out as a floating collage.
Hover a piece for its price, click it for name / brand / stock, switch between up to five fits,
and share the haul as a read-only link.

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

With `XAI_API_KEY` set, the backend calls the xAI Responses API with the `web_search` tool and a
strict JSON schema. Grok searches the live web for real, currently listed products and returns
each one's product page URL. The backend then opens that page and pulls the retailer's own
product photo (`og:image`, Twitter card, or JSON-LD `Product.image`), verifies it serves an image,
and sends it to the UI. Every visual comes directly from the listing site.

A curation takes roughly 20–60 s because of the live search; the prompt bar shows a loading state.
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
| POST   | `/api/curate`     | `{"prompt": "..."}`         | `{"items": [...], "source"}`  |
| POST   | `/api/share`      | `{"fits": [{"items": [...]}]}` | `{"id": "..."}`            |
| GET    | `/api/share/<id>` | —                           | `{"fits": [...]}`             |

Product shape: `name`, `brand`, `price`, `image`, `stock` (`in_stock` / `out_of_stock`),
plus internal `url` (the listing page the image was pulled from), `category` and `color`
(collage placement).
