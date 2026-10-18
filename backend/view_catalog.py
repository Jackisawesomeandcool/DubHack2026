"""Review the catalog in your browser and remove products whose photo is bad.

    python3 view_catalog.py              # starts http://127.0.0.1:8765 and opens it
    python3 view_catalog.py --port 9000

In the page
  click a tile ........ select it (click again to deselect; shift-click selects a range)
  x on a tile ......... remove that product right away
  Remove selected ..... remove everything selected
  check mark .......... mark as reviewed (so you can filter to "not reviewed yet" and work through a big pull)
  Flag people ......... runs the person detector over everything; flagged tiles get a red border and a filter
  Removed (n) ......... list of removed products with Restore, in case of a misclick

Removing deletes the product from the catalog AND remembers its URL, so scrapers, seed.py and
ingest scripts will not add it back. Restore undoes that. Image files are never deleted.
Runs only on your machine (127.0.0.1). Safe to leave open while the Haul server runs; it edits the
same catalog.sqlite, so changes show up in the shop immediately (search results re-cache).
"""

import argparse
import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import catalog
import config

CUT = Path(config.DATA_DIR) / "cutouts"
_flags: dict = {"running": False, "done": 0, "total": 0, "urls": [], "error": ""}


# ---------------------------------------------------------------- data
def _rows() -> list[dict]:
    with catalog._lock:
        db = catalog._db()
        reviewed = {r[0] for r in db.execute("SELECT url FROM reviewed")}
        out = []
        for r in db.execute("SELECT * FROM products ORDER BY added_at DESC, id DESC"):
            cp = r["cutout_p"] or ""
            out.append({
                "url": r["url"], "name": r["name"], "brand": r["brand"], "price": r["price"], "category": r["category"],
                "tags": r["tags"] or "", "source": r["source"] or "", "stock": r["stock"] or "", "added": r["added_at"] or 0,
                "img": ("/cutouts/" + cp.rsplit("/", 1)[-1]) if cp else "", "reviewed": r["url"] in reviewed,
            })
    return out


def remove(urls: list[str]) -> int:
    n = 0
    with catalog._lock:
        db = catalog._db()
        for u in urls:
            r = db.execute("SELECT * FROM products WHERE url=?", (u,)).fetchone()
            if not r:
                continue
            db.execute("INSERT OR REPLACE INTO blocked (url, removed_at, snapshot) VALUES (?,?,?)",
                       (u, time.time(), json.dumps(dict(r))))
            db.execute("DELETE FROM products WHERE url=?", (u,))
            db.execute("DELETE FROM reviewed WHERE url=?", (u,))
            n += 1
        db.execute("DELETE FROM results")      # cached searches may list removed items
        db.commit()
    return n


def restore(urls: list[str]) -> int:
    cols = ["url", "name", "brand", "price", "category", "tags", "cutout_p", "cutout_m", "stock", "source", "last_checked", "added_at"]
    n = 0
    with catalog._lock:
        db = catalog._db()
        for u in urls:
            r = db.execute("SELECT snapshot FROM blocked WHERE url=?", (u,)).fetchone()
            if r and r["snapshot"]:
                d = json.loads(r["snapshot"])
                db.execute(f"INSERT OR IGNORE INTO products ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", [d.get(c) for c in cols])
                n += 1
            db.execute("DELETE FROM blocked WHERE url=?", (u,))
        db.execute("DELETE FROM results")
        db.commit()
    return n


def set_reviewed(urls: list[str], on: bool) -> None:
    with catalog._lock:
        db = catalog._db()
        for u in urls:
            if on:
                db.execute("INSERT OR REPLACE INTO reviewed (url, at) VALUES (?,?)", (u, time.time()))
            else:
                db.execute("DELETE FROM reviewed WHERE url=?", (u,))
        db.commit()


def _flag_worker() -> None:
    try:
        import quality
        from PIL import Image
        if not quality.available():
            _flags["error"] = "person detector unavailable (pip install onnxruntime numpy)"
            return
        rows = [(r["url"], r["category"], r["img"]) for r in _rows() if r["img"]]
        _flags.update(total=len(rows), done=0, urls=[], error="")
        for u, cat, img in rows:
            try:
                if quality.shows_person(Image.open(CUT / img.rsplit("/", 1)[-1]), cat):
                    _flags["urls"].append(u)
            except Exception:  # noqa: BLE001
                pass
            _flags["done"] += 1
    finally:
        _flags["running"] = False


def removed_list() -> list[dict]:
    with catalog._lock:
        out = []
        for r in catalog._db().execute("SELECT url, removed_at, snapshot FROM blocked ORDER BY removed_at DESC"):
            d = json.loads(r["snapshot"]) if r["snapshot"] else {}
            cp = d.get("cutout_p") or ""
            out.append({"url": r["url"], "name": d.get("name", r["url"]), "brand": d.get("brand", ""),
                        "img": ("/cutouts/" + cp.rsplit("/", 1)[-1]) if cp else ""})
    return out


# ---------------------------------------------------------------- http
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/":
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if self.path == "/api/items":
            return self._send(200, json.dumps(_rows()))
        if self.path == "/api/removed":
            return self._send(200, json.dumps(removed_list()))
        if self.path == "/api/flags":
            return self._send(200, json.dumps(_flags))
        if self.path.startswith("/cutouts/"):
            f = CUT / Path(self.path).name
            if f.is_file():
                return self._send(200, f.read_bytes(), "image/png")
        self._send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, "{}")
        urls = [u for u in body.get("urls", []) if isinstance(u, str)]
        if self.path == "/api/remove":
            return self._send(200, json.dumps({"removed": remove(urls)}))
        if self.path == "/api/restore":
            return self._send(200, json.dumps({"restored": restore(urls)}))
        if self.path == "/api/review":
            set_reviewed(urls, bool(body.get("on", True)))
            return self._send(200, "{}")
        if self.path == "/api/flag":
            if not _flags["running"]:
                _flags.update(running=True, done=0, total=0, urls=[], error="")
                threading.Thread(target=_flag_worker, daemon=True).start()
            return self._send(200, "{}")
        self._send(404, "{}")


PAGE = r"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Catalog review</title>
<style>
:root{--bg:#f4f4f2;--card:#fff;--line:#ddd;--mut:#666;--acc:#1a1a1a;--red:#d33}
body{font:14px system-ui;margin:0;background:var(--bg);color:#1a1a1a}
header{position:sticky;top:0;background:#fff;padding:10px 16px;border-bottom:1px solid var(--line);z-index:5;display:flex;flex-direction:column;gap:8px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
input,select,button{font:inherit;padding:6px 10px;border:1px solid #ccc;border-radius:6px;background:#fff}
button{cursor:pointer}button:hover{background:#f0f0f0}
button.danger{background:var(--red);border-color:var(--red);color:#fff}button.danger:hover{background:#b22}
button:disabled{opacity:.4;cursor:default}
#count{margin-left:auto;color:var(--mut)}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;padding:16px}
.t{background:var(--card);border-radius:10px;padding:8px;display:flex;flex-direction:column;gap:3px;position:relative;border:2px solid transparent;cursor:pointer;user-select:none}
.t.sel{border-color:#2563eb;background:#eef4ff}
.t.flag{border-color:var(--red)}.t.sel.flag{border-color:#2563eb}
.t.rev .im{outline:2px solid #3a3;outline-offset:-2px}
.im{height:230px;display:flex;align-items:center;justify-content:center;background:#fafafa;border-radius:6px;overflow:hidden}
.im img{max-width:100%;max-height:100%;object-fit:contain;pointer-events:none}
.t b{font-weight:600;line-height:1.2;font-size:13px}.t small{color:var(--mut)}
.x,.ok{position:absolute;top:6px;width:26px;height:26px;padding:0;border-radius:50%;line-height:1;font-size:15px;opacity:.0;transition:.1s}
.x{right:6px}.ok{left:6px}.t:hover .x,.t:hover .ok,.t.rev .ok{opacity:1}
.ok.on{background:#3a3;color:#fff;border-color:#3a3}
.badge{position:absolute;left:8px;bottom:60px;background:var(--red);color:#fff;font-size:11px;padding:1px 6px;border-radius:9px}
#removed{display:none;padding:16px;background:#fff;border-bottom:1px solid var(--line)}
#removed .r{display:inline-flex;gap:8px;align-items:center;margin:4px 12px 4px 0;font-size:13px}
#removed img{height:40px}
#toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:#222;color:#fff;padding:8px 14px;border-radius:8px;display:none}
</style>
<header>
 <div class=row>
  <input id=q placeholder="search name, brand, tags" size=26>
  <select id=cat><option value="">all categories</option></select>
  <select id=src><option value="">all sources</option></select>
  <select id=rv><option value="">reviewed or not</option><option value=no>not reviewed yet</option><option value=yes>reviewed</option></select>
  <select id=sort><option value=new>newest first</option><option value=name>name</option><option value=brand>brand</option><option value=cat>category</option></select>
  <label><input type=checkbox id=onlyflag> only flagged</label>
  <span id=count></span>
 </div>
 <div class=row>
  <button id=rm class=danger disabled>Remove selected (0)</button>
  <button id=mk disabled>Mark selected reviewed</button>
  <button id=all>Select all shown</button><button id=none>Clear selection</button>
  <button id=flagbtn>Flag people</button><span id=fstat style="color:var(--mut)"></span>
  <button id=rmbtn style="margin-left:auto">Removed (0)</button>
 </div>
</header>
<div id=removed></div>
<main id=g></main><div id=toast></div>
<script>
let D=[],SEL=new Set(),LAST=null,FLAGGED=new Set(),SHOWN=[];
const $=id=>document.getElementById(id);
const api=(p,b)=>fetch(p,b===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(r=>r.json());
function toast(t){const e=$('toast');e.textContent=t;e.style.display='block';clearTimeout(toast.h);toast.h=setTimeout(()=>e.style.display='none',2500)}
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function load(){
  D=await api('/api/items');
  for(const [id,key] of [['cat','category'],['src','source']]){const el=$(id),cur=el.value;el.length=1;[...new Set(D.map(r=>r[key]).filter(Boolean))].sort().forEach(v=>el.add(new Option(v,v)));el.value=cur}
  const rem=await api('/api/removed');$('rmbtn').textContent='Removed ('+rem.length+')';
  draw();
}
function draw(){
  const q=$('q').value.toLowerCase(),c=$('cat').value,s=$('src').value,rv=$('rv').value,of=$('onlyflag').checked;
  SHOWN=D.filter(r=>(!c||r.category==c)&&(!s||r.source==s)&&(!rv||(rv=='yes')==r.reviewed)&&(!of||FLAGGED.has(r.url))&&(!q||(r.name+' '+r.brand+' '+r.tags).toLowerCase().includes(q)));
  const so=$('sort').value;
  if(so=='name')SHOWN.sort((a,b)=>a.name.localeCompare(b.name));else if(so=='brand')SHOWN.sort((a,b)=>a.brand.localeCompare(b.brand)||a.name.localeCompare(b.name));else if(so=='cat')SHOWN.sort((a,b)=>a.category.localeCompare(b.category)||a.name.localeCompare(b.name));
  $('count').textContent=SHOWN.length+' shown of '+D.length;
  $('g').innerHTML=SHOWN.map((r,i)=>`<div class="t ${SEL.has(r.url)?'sel':''} ${FLAGGED.has(r.url)?'flag':''} ${r.reviewed?'rev':''}" data-i="${i}">
   <button class="ok ${r.reviewed?'on':''}" data-a=rev title="mark reviewed">&#10003;</button><button class=x data-a=del title="remove this product">&#10005;</button>
   <div class=im>${r.img?`<img loading=lazy src="${r.img}">`:'no image'}</div>
   ${FLAGGED.has(r.url)?'<span class=badge>person?</span>':''}
   <b>${esc(r.name)}</b><small>${esc(r.brand)} &middot; $${r.price} &middot; ${r.category}</small><small>${esc(r.source)} &middot; ${r.stock} &middot; <a href="${esc(r.url)}" target=_blank onclick="event.stopPropagation()">page</a></small></div>`).join('');
  sync();
}
function sync(){const n=SEL.size;$('rm').textContent='Remove selected ('+n+')';$('rm').disabled=!n;$('mk').disabled=!n}
$('g').addEventListener('click',async e=>{
  const t=e.target.closest('.t');if(!t||e.target.tagName=='A')return;
  const r=SHOWN[+t.dataset.i];const a=e.target.closest('button')?.dataset.a;
  if(a=='del'){await api('/api/remove',{urls:[r.url]});D=D.filter(x=>x.url!=r.url);SEL.delete(r.url);toast('Removed. Undo from "Removed".');const rem=await api('/api/removed');$('rmbtn').textContent='Removed ('+rem.length+')';return draw()}
  if(a=='rev'){r.reviewed=!r.reviewed;await api('/api/review',{urls:[r.url],on:r.reviewed});return draw()}
  if(e.shiftKey&&LAST!=null){const i=+t.dataset.i,[lo,hi]=[Math.min(i,LAST),Math.max(i,LAST)];for(let k=lo;k<=hi;k++)SEL.add(SHOWN[k].url)}
  else{SEL.has(r.url)?SEL.delete(r.url):SEL.add(r.url);LAST=+t.dataset.i}
  draw();
});
$('rm').onclick=async()=>{const u=[...SEL];await api('/api/remove',{urls:u});D=D.filter(x=>!SEL.has(x.url));SEL.clear();toast('Removed '+u.length+'. Undo from "Removed".');load()};
$('mk').onclick=async()=>{const u=[...SEL];await api('/api/review',{urls:u,on:true});D.forEach(r=>{if(SEL.has(r.url))r.reviewed=true});SEL.clear();draw()};
$('all').onclick=()=>{SHOWN.forEach(r=>SEL.add(r.url));draw()};$('none').onclick=()=>{SEL.clear();draw()};
['q','cat','src','rv','sort','onlyflag'].forEach(i=>$(i).addEventListener('input',draw));
$('rmbtn').onclick=async()=>{const el=$('removed');if(el.style.display=='block'){el.style.display='none';return}
  const rem=await api('/api/removed');el.innerHTML=rem.length?rem.map(r=>`<span class=r>${r.img?`<img src="${r.img}">`:''}${esc(r.name)} <button data-u="${esc(r.url)}">Restore</button></span>`).join(''):'Nothing removed yet.';el.style.display='block'};
$('removed').addEventListener('click',async e=>{const u=e.target.dataset.u;if(!u)return;await api('/api/restore',{urls:[u]});toast('Restored');$('removed').style.display='none';load()});
$('flagbtn').onclick=async()=>{await api('/api/flag',{});poll()};
async function poll(){const f=await api('/api/flags');
  if(f.error){$('fstat').textContent=f.error;return}
  FLAGGED=new Set(f.urls);$('fstat').textContent=f.running?('checking '+f.done+'/'+f.total+'...'):(f.total?(f.urls.length+' flagged'):'');draw();
  if(f.running)setTimeout(poll,1500)}
load();poll();
</script>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    catalog._db()                      # make sure the tables exist
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), H)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Catalog review at {url}  (Ctrl+C to stop). {catalog.count()} products.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
