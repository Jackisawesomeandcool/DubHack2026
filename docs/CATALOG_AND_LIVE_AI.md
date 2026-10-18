# Catalog-first Haul: demo without a live key, Grok live search kept as the AI layer

Last updated: 2026-10-17. Audience: DubHack2026 teammates (and their agents).

> **Update 2026-10-18:** search is now catalog-only. The live sources described below (`nike.py` Nike API,
> `websearch.py`, `gsearch.py`, the `ingest.py` warm-up and `merge_catalog.py`) were removed; `finder.py` no longer
> calls them. Add products with `ingest_sites.py` / `ingest_sitemap.py`, and share them via `dataset.py` (docs/DATASET.md).

## TL;DR

- **Demo mode (no key needed):** the app serves prompts, swaps and random fits from a local SQLite **catalog** of Nike products scraped once from Nike's public sitemap. Fast, free, and does not depend on any AI key.
- **The AI concept is unchanged:** Grok (or Gemini) with live web search is how Haul finds and adds new listings. That code path is still in the repo (`grok.py`, `llm.py`, `XAI_*` settings) and runs automatically when a working key is in `backend/.env`. We are demoing on given data; the live path is the production story and needs a key that can call the search API.
- The catalog is **not in git** (`backend/data/` is gitignored). Everyone seeds their own copy (about 10 minutes, free) or copies a teammate's `backend/data/` folder.
- Without a live key you lose on-demand discovery of new listings and per-size stock. See "Limitations".

## How the two modes fit together

| | Demo / offline | Production / "higher tier key" |
|---|---|---|
| Source of listings | Catalog seeded from Nike's sitemap | Catalog **plus** live Grok/Gemini web search that writes new finds back into it |
| Key needed | None | A key that can call xAI `/v1/responses` with `web_search` (or a Gemini key) |
| Speed | Database lookup | Catalog first; live search only fills gaps |
| Status | Working today (152 products) | Code present; blocked only by the key (below) |

## Why the demo does not depend on the live key

1. **The key we had could not call the API the app uses.** The only key available on the personal xAI account was a Cursor-type key (`grok_...`, permission `agent:*`). Against `api.x.ai` it returned `Bad credentials` (`/v1/models`) and `Incorrect API key provided` (`/v1/responses`, `/v1/chat/completions`). xAI's docs describe `api-key:endpoint:*` and `api-key:model:*` permissions; we found no documented endpoint that accepts `agent:*` from our backend. Pasting it into `.env` makes every AI call fail, so leave `XAI_API_KEY` blank until you have a key that works.
2. **Cost.** A team xAI account was created by mistake and billed money. Hackathon credits live on a personal account. Web search calls are billed per invocation plus tokens.
3. **Speed.** Every prompt used to trigger a live `web_search` (10 to 40 s), then a page fetch and cutout per product. Serving from a catalog makes a typical prompt a database lookup.

Other options we looked at and why they were not chosen:

| Option | Outcome |
|---|---|
| Gemini free tier | Works for text/vision, but Search grounding is not free on the free tier (paid tier: first 5,000 grounded prompts/month free, then $14 per 1,000, per third-party summaries). Still supported as an optional provider. |
| Claude via API | A Claude Pro subscription does not include API access; the Console is billed separately. |
| Google Custom Search JSON API | Closed to new customers and ends 2027-01-01 per Google's own page. Not viable. |
| Jina Reader + Groq | Possible, but unnecessary once the catalog exists. Not implemented. |

## What the repo already did (teammates' commits)

These landed before this migration and are what makes "no key" work:

- `llm.py`: provider switch. `GEMINI_API_KEY` set means Gemini; else `XAI_API_KEY` set means Grok; else no AI (`llm.configured()` is false).
- `finder.py`: catalog first, then Nike's search API (`nike.py`), then AI/keyless web search as fallback.
- `catalog.py`: SQLite catalog (`products` and `results` tables); out-of-stock rows are never served; `warm()` pre-searches popular terms.
- `websearch.py`: keyless Bing RSS search with DuckDuckGo backup.
- `people.py`: free skin-tone "is there a person in this photo?" check, used when no vision model is configured.
- `bgremove.py` and `cutouts.py`: tiered background removal (free flat-colour keying, optional Photoroom/remove.bg, local rembg).

## What changed in this migration

Three files. None of them touch `grok.py`, `fits.py`, `finder.py`, `catalog.py`, `llm.py`.

### 1. `backend/ingest_sitemap.py` (new)

Seeds the catalog from `https://www.nike.com/sitemap-v2-pdp-en-us.xml` (about 9,900 `/t/<slug>/<id>` product URLs). No API key.

How it works:
1. Downloads the sitemap and keeps `/t/` URLs. (It uses its own download because `images._fetch_html` caps pages at 2 MB, which silently truncated the sitemap to 298 URLs.)
2. Infers a category from words in the URL slug (shoes, top, bottom, outerwear, bag, headwear, accessory) and samples round-robin so small runs still cover every category. Kids/baby items are skipped unless `--kids`.
3. For each product, fetches the page and reads name and price from the JSON-LD `Product`/`ProductGroup`.
4. Picks a product-only photo with `cutouts.resolve()` (free skin-tone check), removes the background, and saves with `catalog.upsert(..., source="sitemap")`.
5. Resumable: URLs already in the catalog are skipped. Default 1.5 s delay between products.

By default it **blanks `XAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`** for the run so a bad or missing key cannot break photo choice. Pass `--ai` to use configured keys instead.

```
cd backend
python3 ingest_sitemap.py --dry-run                 # counts only, fetches nothing else
python3 ingest_sitemap.py --limit 10                # smoke test
python3 ingest_sitemap.py --per-category 25         # about 175 products, ~10-15 min
python3 ingest_sitemap.py --per-category 100        # bigger catalog
python3 ingest_sitemap.py --models                  # also on-model cutouts (doubles the work)
```

### 2. `backend/stock.py` (fixed)

Bug: Nike product pages have no JSON-LD `availability` field, so the old code hit "page unreadable" and set the product **in stock**. Nike items could never leave stock.

Now `availability_from_page(url)` returns:
- `out_of_stock` for HTTP 404/410, or when the URL redirects away from a `/t/` product page, or when JSON-LD `availability` says anything other than in stock.
- `in_stock` when JSON-LD says in stock, or when the page has a **priced** product offer (the Nike case).
- `None` (unknown) on network errors, blocked pages, or pages with no usable data.

On `None` the product's stock state is **left unchanged** and only `last_checked` is updated (so the background sweep moves on). Before, unknown meant "set in stock", which could resurrect sold-out items.

Verified on real Nike pages: a live product returned `in_stock`; a made-up `/t/` URL returned `out_of_stock`.

### 3. `backend/ingest.py` (one fix)

`ingest.py` called `cutouts.ensure_installed()`, which no longer exists after the bgremove refactor, so it crashed. Replaced with a check that `cutouts.available()` is true, then `cutouts.warm()`. That is the whole change.

Note: `ingest.py` seeds through `finder.find(...)` (Nike API, then AI search). With Nike's search endpoint returning 404 and no AI key it will add nothing. Use `ingest_sitemap.py` for seeding.

## Result of the first seeding run (2026-10-17)

- Sitemap: 9,912 product URLs.
- Run: `--per-category 25`, 145 of 175 added (about 83%). The rest had no photo without a person in it, so they were skipped by design.
- Catalog: 152 products, all in stock: accessory 17, bag 22, bottom 25, headwear 19, outerwear 25, shoes 25, top 19.
- `backend/data/` is about 20 MB (194 files in `cutouts/`).
- First 10-product test: 7 of 10 added.

## Turning the Grok live path back on

`llm.provider()` picks Gemini if `GEMINI_API_KEY` is set, otherwise xAI if `XAI_API_KEY` is set. `grok.py` calls `POST {XAI_BASE_URL}/responses` with the `web_search` tool (restricted to `ALLOWED_DOMAINS`), and falls back to `/chat/completions`. Once a working key is in `.env`, restart the server and live search plus vision photo-picking resume with no code changes.

**What is blocked:** the key we hold is a Cursor-type key with `agent:*`. We have not found any documented xAI endpoint that accepts it from our backend, and `grok.py` calls the standard `/v1/responses` endpoint, which rejects it. Two ways forward:

1. Get a standard API key (the Console's create-key option, with `api-key:endpoint:*` and `api-key:model:*`) on the personal account that holds the hackathon credits, and confirm the credits apply to Responses/web_search usage. Test it with `curl -s https://api.x.ai/v1/models -H "Authorization: Bearer $KEY"`.
2. If the `agent:*` runtime is what the hackathon intends, someone needs its endpoint and request format from xAI's documentation or the hackathon organizers, and `grok.py` would need a new function for it. We have not verified how that API works, so do not assume it behaves like `/responses`.

Either way the demo is unaffected, because the catalog answers first.

## Setup for a teammate

### Option A: seed your own copy (free, ~10 to 15 min)

```
git pull
cd backend
pip install -r requirements.txt
cp .env.example .env            # leave GEMINI_API_KEY and XAI_API_KEY blank
python3 ingest_sitemap.py --per-category 25
python3 server.py               # http://127.0.0.1:8000
# second terminal:
cd frontend && npm install && npm run dev
```

### Option B: copy a teammate's catalog

`backend/data/` is gitignored, so send it by AirDrop, shared drive or zip. Copy the **whole folder**, not only `catalog.sqlite`: the catalog stores cutout paths like `/cutouts/<id>.png`, so the images in `data/cutouts/` and the lookup in `data/cutouts.json` must come with it.

```
cd backend && zip -r haul-data.zip data     # sender
unzip haul-data.zip -d backend              # receiver, from the repo root; stop the server first
```

### `.env`

```
GEMINI_API_KEY=          # optional
XAI_API_KEY=             # blank for the catalog demo; a working xAI API key turns on live Grok search
ALLOWED_DOMAINS=nike.com
```

Do not put the Cursor-type `grok_...` key here (it makes AI calls fail). Never commit `.env`.

## How a prompt is served now

1. `catalog.search` over tags, name and category: instant, in-stock only.
2. If the catalog is thin for that prompt: Nike search API (`nike.py`). Currently returns HTTP 404, so the code disables it for 10 minutes after two failures.
3. If that fails: AI web search (Grok or Gemini, when a key works) or, with no key, keyless web search (`websearch.py`), then the page fetch and cutout. Slow (seconds), and results are written back to the catalog.
4. Anything found live is saved, so the catalog grows from use.

If the keyless path is rate-limited, prompts that the catalog cannot answer will come back thin. Growing the catalog is the fix.

## Limitations (be honest with judges and users)

- **No on-demand discovery of new products.** The app shows what is in the catalog. A product that is not in it only appears if the keyless fallback finds it.
- **Stock is page-level, not per-size.** Nike pages expose no per-size stock. `stock.py` detects retired or removed products, not "size M sold out".
- **Category is guessed from the URL slug.** A few items are misfiled (for example, one "shoe bag" T-shirt was filed under bag before a later fix; the fix only applies to new runs).
- **Photos are chosen by a skin-tone heuristic**, not a vision model. About 17% of products are skipped because no clean product-only photo was found. Some on-model photos may slip through, and some good ones are rejected.
- **Sitemap is US English only** and only includes what Nike lists there.
- **Scraping.** `robots.txt` has no rule against `/t/` and no crawl delay; it disallows `*/p/`. The script is rate limited. Treat this as hackathon-scale use; do not point it at a high rate or run it in parallel.
- **Prices are as of scrape time.** Re-run the script to refresh; existing URLs are skipped unless you remove them.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Incorrect API key provided` / `Bad credentials` | A Cursor-type or invalid key is in `.env`. Blank `XAI_API_KEY`. |
| `[nike] search failed (HTTP Error 404)` | Nike's unofficial search endpoint is gone or changed. Expected; use the sitemap seeding. |
| `AttributeError: module 'cutouts' has no attribute 'ensure_installed'` | Old `ingest.py`; pull the fixed version. |
| `Cutouts unavailable` | Install Pillow: `pip install -r requirements.txt`. |
| `no suitable photo among N for ...` | Normal; the product had no photo without a person. It is skipped. |
| Sitemap shows about 298 URLs | Old copy of the script with the 2 MB page cap; pull the fixed one. |
| `ModuleNotFoundError: No module named 'stock'` | Run from `backend/`, not the repo root. |
| Server cannot see new products | Restart the server after seeding, or confirm you copied `data/cutouts/` and `cutouts.json` too. |

## Open items

- Use the `inStock` flag from Nike's search API in `nike.py` / `catalog.py` if that endpoint ever works again.
- Schedule `stock.py` sweeps and periodic re-seeding (cron or on server start).
- Update `README.md`: it still describes Grok-based live search in places (the "Grok finds them" streaming note and the 10 to 40 s search time) and does not mention `ingest_sitemap.py`.
- Get a working xAI key (or the `agent:*` request format) so the live Grok path can be demonstrated, and add a "live refresh" step that writes new finds into the catalog.
- Consider adding on-model cutouts (`--models`) once the product-only catalog is large enough.
- Optionally commit a small seed bundle, or host `haul-data.zip`, so new teammates skip seeding.

## Files touched

| File | Change |
|---|---|
| `backend/ingest_sitemap.py` | New: sitemap seeding script |
| `backend/stock.py` | Fixed: out-of-stock detection for Nike, no false "in stock" |
| `backend/ingest.py` | Fixed: removed call to missing `cutouts.ensure_installed()` |
| `frontend/package-lock.json` | Changed by `npm install` only; not part of this work |
