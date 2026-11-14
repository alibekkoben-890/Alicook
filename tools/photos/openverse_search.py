#!/usr/bin/env python3
"""Search Openverse for freely licensed dish photos and build contact sheets.

Reads tools/photos/queries.json ({"recipe_id": "query"}), writes
out/candidates.json and out/sheet_<id>.jpg. Runs on GitHub Actions.
"""
import io, json, os, sys, time, urllib.parse, urllib.request
from PIL import Image, ImageDraw

UA = "AliCookPhotoCollector/1.0 (https://github.com/alibekkoben-890/Alicook)"
API = "https://api.openverse.org/v1/images/"
OUT = sys.argv[2] if len(sys.argv) > 2 else "out"
os.makedirs(OUT, exist_ok=True)
queries = json.load(open(sys.argv[1], encoding="utf-8"))


def get(url, tries=4):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except Exception as e:
            if a == tries - 1:
                raise
            time.sleep(5 * (a + 1))


out = {}
for rid, q in queries.items():
    params = dict(q=q, license="cc0,pdm,by,by-sa", category="photograph", page_size=20, mature="false")
    try:
        data = json.loads(get(API + "?" + urllib.parse.urlencode(params)))
    except Exception as e:
        print(rid, q, "search failed", e, flush=True)
        continue
    cands, tiles = [], []
    for it in data.get("results", []):
        if len(cands) == 9:
            break
        if (it.get("width") or 0) < 500:
            continue
        try:
            im = Image.open(io.BytesIO(get(it["url"], 2))).convert("RGB")
        except Exception:
            continue
        lic = it["license"].upper()
        lic = {"CC0": "CC0", "PDM": "Public domain"}.get(lic, f"CC {lic} {it.get('license_version') or ''}".strip())
        cands.append({"url": it["url"], "title": it.get("title") or "", "author": it.get("creator") or "—",
                      "license": lic, "license_url": it.get("license_url") or "",
                      "source": it.get("foreign_landing_url") or "", "provider": it.get("source") or ""})
        im.thumbnail((300, 225))
        t = Image.new("RGB", (300, 245), "white")
        t.paste(im, ((300 - im.width) // 2, 0))
        ImageDraw.Draw(t).text((4, 228), f"{len(cands)-1}: {(it.get('title') or '')[:42]}", fill="black")
        tiles.append(t)
    out[rid] = cands
    if tiles:
        sheet = Image.new("RGB", (900, 245 * ((len(tiles) + 2) // 3)), "white")
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % 3) * 300, (i // 3) * 245))
        sheet.save(f"{OUT}/sheet_{rid}.jpg", quality=75)
    print(rid, q, len(cands), flush=True)
    time.sleep(3)
json.dump(out, open(f"{OUT}/candidates.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
