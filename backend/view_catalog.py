"""Browse the whole catalog in your browser (read-only).

    python3 view_catalog.py            # writes data/catalog_gallery.html and opens it
    python3 view_catalog.py --no-open  # just write the file

Every product is shown as its cutout with name, brand, price, category, source and stock.
Use the search box and the filters at the top. Works offline; stop nothing, it only reads
the database.
"""

import argparse
import html
import json
import sqlite3
import webbrowser

import config

PAGE = """<!doctype html><meta charset=utf-8><title>Catalog</title>
<style>
body{font:14px system-ui;margin:0;background:#f4f4f2;color:#1a1a1a}
header{position:sticky;top:0;background:#fff;padding:10px 16px;border-bottom:1px solid #ddd;display:flex;gap:8px;flex-wrap:wrap;align-items:center;z-index:5}
input,select{font:inherit;padding:6px 8px;border:1px solid #ccc;border-radius:6px}
#n{margin-left:auto;color:#666}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px;padding:16px}
.c{background:#fff;border-radius:10px;padding:8px;display:flex;flex-direction:column;gap:4px}
.c .im{height:200px;display:flex;align-items:center;justify-content:center;background:#fafafa;border-radius:6px}
.c img{max-width:100%;max-height:100%;object-fit:contain}
.c b{font-weight:600;line-height:1.2}.c small{color:#666}
.oos{opacity:.45}
</style>
<header><input id=q placeholder="search name, brand, tags" size=28>
<select id=cat><option value="">all categories</option>%CATS%</select>
<select id=src><option value="">all sources</option>%SRCS%</select>
<select id=stk><option value="">any stock</option><option>in_stock</option><option>out_of_stock</option></select>
<span id=n></span></header><main id=g></main>
<script>
const D=%DATA%;
const g=document.getElementById('g');
function draw(){
 const q=document.getElementById('q').value.toLowerCase(),c=cat.value,s=src.value,k=stk.value;
 const rows=D.filter(r=>(!c||r.category==c)&&(!s||r.source==s)&&(!k||r.stock==k)&&(!q||(r.name+' '+r.brand+' '+r.tags).toLowerCase().includes(q)));
 document.getElementById('n').textContent=rows.length+' of '+D.length+' items';
 g.innerHTML=rows.map(r=>`<a class="c ${r.stock=='in_stock'?'':'oos'}" href="${r.url}" target=_blank style="text-decoration:none;color:inherit"><div class=im>${r.img?`<img loading=lazy src="${r.img}">`:'no image'}</div><b>${r.name}</b><small>${r.brand} · $${r.price} · ${r.category}</small><small>${r.source||''} · ${r.stock||''}</small></a>`).join('');
}
['q','cat','src','stk'].forEach(i=>document.getElementById(i).addEventListener('input',draw));draw();
</script>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    db = sqlite3.connect(f"file:{config.DATA_DIR / 'catalog.sqlite'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    rows = []
    for r in db.execute("SELECT * FROM products ORDER BY category, brand, name"):
        cp = r["cutout_p"] or ""
        rows.append({"name": r["name"], "brand": r["brand"], "price": r["price"], "category": r["category"],
                     "tags": r["tags"] or "", "source": r["source"] or "", "stock": r["stock"] or "", "url": r["url"],
                     "img": "cutouts/" + cp.rsplit("/", 1)[-1] if cp else ""})
    opts = lambda key: "".join(f"<option>{html.escape(v)}</option>" for v in sorted({r[key] for r in rows if r[key]}))
    out = (PAGE.replace("%CATS%", opts("category")).replace("%SRCS%", opts("source"))
           .replace("%DATA%", json.dumps(rows).replace("</", "<\\/")))
    path = config.DATA_DIR / "catalog_gallery.html"
    path.write_text(out, encoding="utf-8")
    print(f"{len(rows)} products -> {path}")
    if not args.no_open:
        webbrowser.open(path.as_uri())


if __name__ == "__main__":
    main()
