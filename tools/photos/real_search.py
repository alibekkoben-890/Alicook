#!/usr/bin/env python3
"""Search for real, freely licensed photos for recipes that still have a generated picture.

Input: JSON {recipe_id: [query, ...]}. Wikimedia Commons is asked first (it has the national
dishes), then Pixabay and Openverse. Output in OUT: candidates.json {id: [candidate]} and
pack_NNN.jpg contact sheets (8 recipes per sheet, up to 8 tiles each) for choosing by eye.
Usage: real_search.py queries.json OUT [SHARD NSHARDS]. Runs on GitHub Actions.
"""
import html, io, json, os, re, sys, time, urllib.parse, urllib.request
from PIL import Image, ImageDraw

UA = "AliCookPhotoCollector/1.1 (https://github.com/alibekkoben-890/Alicook)"
FREE = re.compile(r"^(CC0|Public domain|PD|CC BY(-SA)? \d\.\d)", re.I)
queries = json.load(open(sys.argv[1], encoding="utf-8"))
OUT = sys.argv[2]
SHARD, NSH = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (0, 1)
os.makedirs(OUT, exist_ok=True)
TW, TH, PER_Q, PACK = 170, 128, 8, 8
EXCLUDE = set(json.load(open("tools/photos/exclude.json"))) if os.path.exists("tools/photos/exclude.json") else set()
BAD = re.compile(r"\b(map|logo|flag|diagram|icon|coat of arms|stamp|poster|menu|book|label|packag|portrait|building|restaurant exterior)\b", re.I)


def get(url, tries=3):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except Exception:
            if a == tries - 1:
                raise
            time.sleep(5 * (a + 1))


def strip(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", h or ""))).strip()


def commons(q):
    p = dict(action="query", format="json", formatversion="2", generator="search",
             gsrsearch=f"{q} filetype:bitmap", gsrnamespace=6, gsrlimit=12, prop="imageinfo",
             iiprop="url|extmetadata|size|mime|user", iiurlwidth=1280)
    d = json.loads(get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(p)))
    out = []
    for pg in sorted(d.get("query", {}).get("pages", []), key=lambda x: x.get("index", 0)):
        ii = (pg.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata", {})
        lic = md.get("LicenseShortName", {}).get("value", "")
        if ii.get("mime") not in ("image/jpeg", "image/png") or not FREE.match(lic) or ii.get("width", 0) < 500:
            continue
        if BAD.search(pg["title"]) or ii["descriptionurl"] in EXCLUDE:
            continue
        author = strip(md.get("Artist", {}).get("value", ""))
        if not author or author.lower().startswith("no machine-readable"):
            author = (ii.get("user") or "—") + " (Wikimedia Commons)"
        out.append({"url": ii.get("thumburl") or ii["url"], "title": pg["title"][5:], "author": author[:80],
                    "license": lic, "license_url": md.get("LicenseUrl", {}).get("value", ""),
                    "source": ii["descriptionurl"], "provider": "wikimedia"})
    return out


def pixabay(q):
    key = (os.environ.get("PIXABAY_API_KEY") or "").strip()
    if not key:
        return []
    d = json.loads(get("https://pixabay.com/api/?" + urllib.parse.urlencode(
        dict(key=key, q=q[:100], image_type="photo", category="food", per_page=12, safesearch="true"))))
    return [{"url": h["largeImageURL"], "thumb": h["webformatURL"], "title": h.get("tags") or "", "author": h.get("user") or "—",
             "license": "Pixabay Content License", "license_url": "https://pixabay.com/service/license-summary/",
             "source": h["pageURL"], "provider": "pixabay"} for h in d.get("hits", []) if h["pageURL"] not in EXCLUDE]


def openverse(q):
    p = dict(q=q, license="cc0,pdm,by,by-sa", category="photograph", page_size=10, mature="false")
    d = json.loads(get("https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(p)))
    out = []
    for it in d.get("results", []):
        if (it.get("width") or 0) < 500 or it.get("source") == "wikimedia":
            continue
        lic = it["license"].upper()
        lic = {"CC0": "CC0", "PDM": "Public domain"}.get(lic, f"CC {lic} {it.get('license_version') or ''}".strip())
        out.append({"url": it["url"], "title": it.get("title") or "", "author": (it.get("creator") or "—")[:80],
                    "license": lic, "license_url": it.get("license_url") or "",
                    "source": it.get("foreign_landing_url") or "", "provider": it.get("source") or "openverse"})
    return out


def uniq(items, seen):
    out = []
    for c in items:
        if c["source"] and c["source"] not in seen:
            seen.add(c["source"])
            out.append(c)
    return out


keys = [k for i, k in enumerate(sorted(queries, key=lambda x: int(x))) if i % NSH == SHARD]
cands, blocks = {}, []
for key in keys:
    qs = queries[key]
    seen, wiki, other = set(), [], []
    for q in qs:
        if len(wiki) >= 6:
            break
        try:
            wiki += uniq(commons(q), seen)
        except Exception as e:
            print(key, "commons failed", e, flush=True)
        time.sleep(0.4)
    for fn in (pixabay, openverse):
        if len(other) >= 6:
            break
        try:
            other += uniq(fn(qs[0]), seen)
        except Exception as e:
            print(key, fn.__name__, "failed", e, flush=True)
    # half of the tiles for Commons, half for the stock sources; leftovers fill the gaps
    nw = min(len(wiki), max(4, PER_Q - len(other)))
    found = wiki[:nw] + other[:PER_Q - nw] + wiki[nw:]
    keep, tiles = [], []
    for c in found:
        if len(keep) == PER_Q:
            break
        try:
            im = Image.open(io.BytesIO(get(c.get("thumb") or c["url"], 2))).convert("RGB")
        except Exception:
            continue
        im.thumbnail((TW, TH - 14))
        t = Image.new("RGB", (TW, TH), "white")
        t.paste(im, ((TW - im.width) // 2, 0))
        ImageDraw.Draw(t).text((3, TH - 13), f"{len(keep)}{c['provider'][:1].upper()} {c['title'][:26]}", fill="black")
        tiles.append(t)
        keep.append(c)
        time.sleep(0.2)
    cands[key] = keep
    block = Image.new("RGB", (TW * 4, TH * 2 + 18), (235, 235, 235))
    ImageDraw.Draw(block).text((4, 3), f"[{key}] {' | '.join(qs)}"[:110], fill=(180, 0, 0))
    for i, t in enumerate(tiles):
        block.paste(t, ((i % 4) * TW, 18 + (i // 4) * TH))
    blocks.append(block)
    print(key, qs[0], len(keep), flush=True)

BH = TH * 2 + 18
for n in range(0, len(blocks), PACK):
    sheet = Image.new("RGB", (TW * 8 + 10, (BH + 10) * (PACK // 2)), "white")
    for j, b in enumerate(blocks[n:n + PACK]):
        sheet.paste(b, ((j % 2) * (TW * 4 + 10), (j // 2) * (BH + 10)))
    sheet.save(f"{OUT}/pack_{n // PACK:03d}.jpg", quality=72)
json.dump(cands, open(f"{OUT}/candidates.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
