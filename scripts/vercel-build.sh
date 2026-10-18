#!/usr/bin/env bash
# Vercel build: compile the React app, then publish every product image from the dataset as a static file
# (/cutouts/<name>.png) so the API function never has to carry or serve them.
set -euo pipefail
cd "$(dirname "$0")/.."

(cd frontend && npm run build)

mkdir -p frontend/dist/cutouts
cp backend/dataset/cutouts/*.png frontend/dist/cutouts/

# every product in the dataset must have its image, or it would show as a broken picture
python3 - <<'PY'
import json, os, sys
items = json.load(open("backend/dataset/catalog.json"))["items"]
missing = [(i["name"], i[k]) for i in items for k in ("cutout_p", "cutout_m") if i.get(k) and not os.path.exists("frontend/dist/cutouts/" + i[k])]
if missing:
    sys.exit("missing images for: " + ", ".join(n for n, _ in missing[:10]))
print(f"ok: {len(items)} products, {len(os.listdir('frontend/dist/cutouts'))} images")
PY
