"""Find catalog items whose cutout still shows a person, and (optionally) crop them to just the clothes.

    python3 audit_catalog.py                 # list suspects (read-only)
    python3 audit_catalog.py --fix           # re-download the original photo and keep ONLY the garment
    python3 audit_catalog.py --fix --remove  # ...and delete the ones that can't be cropped cleanly
    python3 audit_catalog.py --remove        # just delete every flagged item

Detection: quality.py (local person detector + skin check). Cropping: garment.py (local cloth
segmentation; tops, outerwear and bottoms). Neither needs an API key. Bags/shoes/headwear that
show a person can't be cropped; they stay in the list (or are deleted with --remove).
The first --fix run downloads a 170 MB model. Stop the server first. Safe to re-run.
"""

import argparse
import sys
from pathlib import Path

import catalog
import config
import cutouts
import garment
import quality


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="crop flagged clothing down to just the garment")
    ap.add_argument("--remove", action="store_true", help="delete flagged items (with --fix: only those that could not be fixed)")
    ap.add_argument("--recrop", action="store_true", help="re-cut existing tops/outerwear/bottoms that still show neck, hands or legs (no download needed)")
    ap.add_argument("--tidy", action="store_true", help="drop stray logos/specks around the product and trim the empty margin (all categories, no download)")
    ap.add_argument("--limit", type=int, default=0, help="stop after fixing N items (testing)")
    args = ap.parse_args()
    if not quality.available():
        sys.exit("Needs: pip install onnxruntime numpy (and internet once to fetch the 20 MB model).")
    if args.fix and not garment.available():
        sys.exit("Cropping needs: pip install onnxruntime numpy scipy (and internet once for the 170 MB model).")

    if args.recrop:
        return _recrop(args.limit)
    if args.tidy:
        return _tidy(args.limit)
    cache = cutouts._load_cache()
    source_of = {v["file"]: k for k, v in cache.items() if isinstance(v, dict) and v.get("file") and not k.startswith(("pick:", "garment:"))}
    with catalog._lock:
        rows = catalog._db().execute("SELECT url, name, brand, category, cutout_p FROM products").fetchall()

    flagged = []
    for url, name, brand, cat, cp in rows:
        if cp and not quality.check_cutout(Path(config.DATA_DIR) / "cutouts" / Path(cp).name, cat)[0]:
            flagged.append((url, name, brand, cat, cp))
            if not args.fix:
                print(f"  person: {brand:8s} {cat:9s} {name[:60]}")
    print(f"{len(flagged)} of {len(rows)} items show a person.")
    if not args.fix:
        if args.remove and flagged:
            _delete([f[0] for f in flagged])
        return

    fixed, failed = 0, []
    for n, (url, name, brand, cat, cp) in enumerate(flagged, 1):
        if args.limit and fixed >= args.limit:
            break
        src = source_of.get(Path(cp).name)
        out, why = None, "original photo unknown"
        if src and garment.can_handle(cat):
            try:
                raw = cutouts._download(src)
                out, why = cutouts.garment_from_photos([raw], src, cat, name)
            except Exception as err:  # noqa: BLE001
                why = f"download failed: {err}"
        elif src:
            why = "can't crop this kind of item"
        if out:
            with catalog._lock:
                db = catalog._db()
                db.execute("UPDATE products SET cutout_p=? WHERE url=?", (out, url))
                db.commit()
            fixed += 1
            print(f"[{n}/{len(flagged)}] cropped  {cat:9s} {name[:55]}")
        else:
            failed.append(url)
            print(f"[{n}/{len(flagged)}] could not ({why})  {cat:9s} {name[:50]}")
    print(f"cropped {fixed}; {len(failed)} could not be fixed.")
    if args.remove and failed:
        _delete(failed)


def _recrop(limit: int) -> None:
    """Second pass for cutouts that passed the person check but still carry a bit of the model
    (neck, hands, legs, hair). Runs the garment segmenter on the cutout we already have, keeps only
    the clothing, and stores the result as a NEW file so teammates get it through the dataset."""
    from PIL import Image
    if not garment.available():
        sys.exit("Cropping needs: pip install onnxruntime numpy scipy (and internet once for the 170 MB model).")
    cache = cutouts._load_cache()
    done = {v["file"] for k, v in cache.items() if k.startswith("garment:recrop:") and isinstance(v, dict)}
    with catalog._lock:
        rows = catalog._db().execute("SELECT url, name, category, cutout_p FROM products WHERE category IN ('top','outerwear','bottom')").fetchall()
    changed = skipped = 0
    for n, (url, name, cat, cp) in enumerate(rows, 1):
        if limit and changed >= limit:
            break
        if not cp or Path(cp).name in done:
            continue
        path = Path(config.DATA_DIR) / "cutouts" / Path(cp).name
        try:
            im = Image.open(path).convert("RGBA")
            score = quality.person_score(im) or 0.0
            whole, top, _ = quality._skin_stats(im)
        except Exception:  # noqa: BLE001
            continue
        if score < 0.5 or not (whole >= 0.005 or top >= 0.015):
            continue                                   # flat-lay or no skin showing: leave it
        out, info = garment.extract(im, cat, tta=False, multi_ok=cutouts._multi_ok(name))
        if out is None:
            skipped += 1
            print(f"[{n}/{len(rows)}] kept as is ({info.get('reason')})  {cat:9s} {name[:50]}")
            continue
        a0 = sum(1 for v in im.getchannel("A").getdata() if v > 127)
        a1 = sum(1 for v in out.getchannel("A").getdata() if v > 127)
        if a1 > 0.985 * a0:
            continue                                   # nothing worth removing
        new = cutouts.save_garment("recrop:" + Path(cp).name, out)
        with cutouts._lock:
            cache["garment:recrop:" + Path(cp).name]["file"] = Path(new).name
        with catalog._lock:
            db = catalog._db()
            db.execute("UPDATE products SET cutout_p=? WHERE url=?", (new, url))
            db.execute("DELETE FROM results")
            db.commit()
        changed += 1
        print(f"[{n}/{len(rows)}] re-cropped  {cat:9s} {name[:55]}  (-{100 - 100 * a1 / max(a0, 1):.0f}%)")
    print(f"re-cropped {changed}; {skipped} kept as they were (segmenter could not do better). Review them in view_catalog.py.")


def _tidy(limit: int) -> None:
    """Remove small stray pieces (a brand logo badge in the corner, specks) and trim the margin.
    Keeps every piece that is at least 8% of the biggest one, so pairs (two shoes, a sock set) survive.
    Saved as a NEW file so teammates get it through the dataset. Safe to re-run."""
    import numpy as np
    from PIL import Image
    from scipy import ndimage as ndi
    cache = cutouts._load_cache()
    done = {v["file"] for k, v in cache.items() if k.startswith("garment:tidy:") and isinstance(v, dict)}
    with catalog._lock:
        rows = catalog._db().execute("SELECT url, name, category, cutout_p FROM products WHERE cutout_p IS NOT NULL").fetchall()
    changed = 0
    for url, name, cat, cp in rows:
        if limit and changed >= limit:
            break
        if Path(cp).name in done:
            continue
        try:
            im = Image.open(Path(config.DATA_DIR) / "cutouts" / Path(cp).name).convert("RGBA")
        except Exception:  # noqa: BLE001
            continue
        alpha = np.asarray(im.getchannel("A"))
        a = alpha > 127
        lab, n = ndi.label(ndi.binary_dilation(a, iterations=3))      # bridge hairline gaps
        if n < 2:
            continue
        sizes = ndi.sum(a, lab, range(1, n + 1))
        keep = [i + 1 for i, s in enumerate(sizes) if s >= 0.08 * sizes.max()]
        if len(keep) == n:
            continue
        al = alpha.copy()
        al[~np.isin(lab, keep)] = 0
        ys, xs = np.where(al > 0)
        box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        if (box[2] - box[0]) * (box[3] - box[1]) > 0.97 * im.size[0] * im.size[1]:
            continue                                                  # nothing visible changed
        out = im.copy()
        out.putalpha(Image.fromarray(al))
        new = cutouts.save_garment("tidy:" + Path(cp).name, out.crop(box))
        with catalog._lock:
            db = catalog._db()
            db.execute("UPDATE products SET cutout_p=? WHERE url=?", (new, url))
            db.execute("DELETE FROM results")
            db.commit()
        changed += 1
        print(f"tidied  {cat:9s} {name[:60]}")
    print(f"tidied {changed} cutouts.")


def _delete(urls: list[str]) -> None:
    with catalog._lock:
        db = catalog._db()
        db.executemany("INSERT OR IGNORE INTO blocked (url, removed_at, snapshot) VALUES (?,strftime('%s','now'),NULL)", [(u,) for u in urls])
        db.executemany("DELETE FROM products WHERE url=?", [(u,) for u in urls])
        db.commit()
    print(f"Removed {len(urls)} from the catalog; {catalog.count()} remain.")


if __name__ == "__main__":
    main()
