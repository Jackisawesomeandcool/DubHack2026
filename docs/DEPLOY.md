# Hosting Haul on Vercel (free, no card)

Everything below fits Vercel's **Hobby** plan and Upstash's **free** Redis. No payment method is asked for.
Hobby is for non-commercial use — fine for a hackathon demo or portfolio project.

## How it is put together

| Piece | Where it runs |
|-------|---------------|
| `frontend` service (`frontend/`, Vite) | built by Vercel, served as static files; receives every path except the two below |
| `backend` service (`backend/`, Python) | `/api/*` and `/cutouts/*`; `backend/vercel_app.py` is a small ASGI adapter that runs the same `server.Handler` used locally |
| Product images (`backend/dataset/cutouts/*.png`, ~31 MB) | shipped inside the backend service and served at `/cutouts/<name>.png` with a long CDN cache, so repeat views don't run the function |
| Product catalog | the function rebuilds a small SQLite catalog in `/tmp` from `backend/dataset/catalog.json` on each cold start (~0.2 s) |
| Accounts, favorites, hauls, search history, share links | Upstash Redis (`backend/kv.py`, `backend/auth_kv.py`) |
| AI ranking (optional) | Gemini, if `GEMINI_API_KEY` is set; otherwise keyword ranking |

Locally nothing changes: `python3 server.py` still uses SQLite and the JSON files in `backend/data/`.

Hosted mode switches on by itself (Vercel sets `VERCEL=1`). In it there are no background jobs:
no stock re-checks, no color/quality sweeps, no scraping. **The catalog on the site is whatever is committed in
`backend/dataset/`**; to update it, run the scrapers locally, `python3 backend/dataset.py export`, commit, push — Vercel redeploys.

## One-time setup

1. **Push the repo to GitHub** (it already is) — including `vercel.json` and `backend/vercel_app.py`.
2. **Create a free Upstash Redis**: sign up at upstash.com (GitHub login works), *Create database* → pick the Free plan, any region
   (choose one near your Vercel region, `iad1` by default). Open the database's **REST API** section and copy
   `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`.
   (Alternative: in Vercel, *Storage → Marketplace → Upstash Redis* creates it and fills the variables for you.)
3. **Import the project in Vercel**: vercel.com → *Add New → Project* → pick `DubHack2026`. Leave *Root Directory* as the repo root.
   `vercel.json` defines the two services (Vercel's *Services* feature) and the public routes, so accept the defaults.
4. **Environment Variables** (before the first deploy, or add them and redeploy):
   - `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` — required for accounts and share links
   - `GEMINI_API_KEY` — optional, enables AI picks (free tier works). Without it search still works, ranked by keywords
5. **Deploy.** Open the URL. `https://<your-app>.vercel.app/api/health` should show `"hosted": true, "cutouts": true, "catalog": <n>`.

Every `git push` to `main` redeploys.

## Free-tier limits to know

- Upstash free: ~10,000 commands/day and 1 MB per request. Each login, page-load session check and saved change is 1-3 commands; fine for a demo.
  Saved favorites/hauls are capped at ~900 KB per user.
- Requests are buffered, not streamed (the app still works, results arrive together). Services are a Vercel beta feature; limits are the normal Vercel Functions limits.
- No Upstash variables = the site still loads and searches, but sign-up and share links answer "not available on this deployment yet"
  (an ephemeral per-instance database would silently forget everyone, so it is refused instead).
- Never put keys in the repo; use the Vercel dashboard.

## Troubleshooting

- **Images 404**: images are served by the backend service from `backend/dataset/cutouts/`; check `/cutouts/<name>.png` directly and that the `/cutouts/(.*)` rewrite in `vercel.json` is present.
- **`/api/...` returns the web page or 404**: check the top-level `rewrites` in `vercel.json` were deployed and the `backend` service built (deployment page → Services).
- **Backend crash on start**: the Logs tab shows the import error. The backend installs nothing: `backend/requirements.txt` is intentionally empty (heavy tools live in `requirements-local.txt`), so never import Pillow/numpy on the request path.
- **Accounts error "storage not connected"**: the two Upstash variables are missing or wrong; redeploy after fixing them.
