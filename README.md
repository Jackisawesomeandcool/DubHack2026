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

### Without an xAI key

If `XAI_API_KEY` is empty the backend curates from a small built-in catalog of real products,
so the whole app can be tested on localhost with no network or key. Add a key to switch to Grok;
if a Grok call fails the backend logs the error and falls back to the catalog.

### Images

Grok is asked for official product image URLs. The backend verifies each URL actually serves an
image; anything unverified renders as a clean colored garment cutout instead of a broken image.

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
plus internal `category` and `color` used only for collage placement and cutouts.
