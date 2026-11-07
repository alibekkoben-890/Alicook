#!/usr/bin/env python3
"""Search Wikimedia Commons and Openverse for freely licensed dish photos.

Input: JSON {key: query}. Output in OUT: candidates.json {key: [candidate]},
and pack_NNN.jpg contact sheets with 4 queries per image (3x3 tiles each).
Runs on GitHub Actions.
"""
import html, io, json, os, re, sys, time, urllib.parse, urllib.request
from PIL import Image, ImageDraw

UA = "AliCookPhotoCollector/1.0 (https://github.com/alibekkoben-890/Alicook)"
FREE = re.compile(r"^(CC0|Public domain|PD|CC BY(-SA)? \d\.\d)", re.I)
queries = json.load(open(sys.argv[1], encoding="utf-8"))
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)
TW, TH = 170, 128
PER_Q = int(os.environ.get("PER_Q") or "6")
PACK = int(os.environ.get("PACK") or "6")
PEXELS_OFF = False


def get(url, tries=3):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except Exception:
            if a == tries - 1:
                raise
            time.sleep(4 * (a + 1))


def strip(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", h or ""))).strip()


def commons(q):
    p = dict(action="query", format="json", formatversion="2", generator="search",
             gsrsearch=f"{q} filetype:bitmap", gsrnamespace=6, gsrlimit=15, prop="imageinfo",
             iiprop="url|extmetadata|size|mime|user", iiurlwidth=1280)
    d = json.loads(get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(p)))
    out = []
    for pg in sorted(d.get("query", {}).get("pages", []), key=lambda x: x.get("index", 0)):
        ii = (pg.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata", {})
        lic = md.get("LicenseShortName", {}).get("value", "")
        if ii.get("mime") not in ("image/jpeg", "image/png") or not FREE.match(lic) or ii.get("width", 0) < 500:
            continue
        author = strip(md.get("Artist", {}).get("value", ""))
        if not author or author.lower().startswith("no machine-readable"):
            author = (ii.get("user") or "—") + " (Wikimedia Commons)"
        out.append({"url": ii.get("thumburl") or ii["url"], "title": pg["title"][5:], "author": author[:80],
                    "license": lic, "license_url": md.get("LicenseUrl", {}).get("value", ""),
                    "source": ii["descriptionurl"], "provider": "wikimedia",
                    "desc": strip(md.get("ImageDescription", {}).get("value", ""))[:160]})
    return out


def openverse(q):
    p = dict(q=q, license="cc0,pdm,by,by-sa", category="photograph", page_size=15, mature="false")
    d = json.loads(get("https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(p)))
    out = []
    for it in d.get("results", []):
        if (it.get("width") or 0) < 500 or it.get("source") == "wikimedia":
            continue
        lic = it["license"].upper()
        lic = {"CC0": "CC0", "PDM": "Public domain"}.get(lic, f"CC {lic} {it.get('license_version') or ''}".strip())
        out.append({"url": it["url"], "title": it.get("title") or "", "author": (it.get("creator") or "—")[:80],
                    "license": lic, "license_url": it.get("license_url") or "",
                    "source": it.get("foreign_landing_url") or "", "provider": it.get("source") or "", "desc": ""})
    return out


def pexels(q):
    global PEXELS_OFF
    key = os.environ.get("PEXELS_API_KEY")
    if not key or PEXELS_OFF:
        return []
    req = urllib.request.Request("https://api.pexels.com/v1/search?" + urllib.parse.urlencode(dict(query=q, per_page=15)),
                                 headers={"User-Agent": UA, "Authorization": key})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=40).read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            PEXELS_OFF = True
            print("pexels rate limit reached; continuing without it", flush=True)
        raise
    return [{"url": p["src"]["large"], "thumb": p["src"]["medium"], "title": p.get("alt") or "", "author": p.get("photographer") or "—",
             "license": "Pexels License", "license_url": "https://www.pexels.com/license/",
             "source": p["url"], "provider": "pexels", "desc": p.get("alt") or ""} for p in d.get("photos", [])]


def pixabay(q):
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return []
    d = json.loads(get("https://pixabay.com/api/?" + urllib.parse.urlencode(
        dict(key=key, q=q, image_type="photo", category="food", per_page=15, safesearch="true"))))
    return [{"url": h["largeImageURL"], "thumb": h["webformatURL"], "title": h.get("tags") or "", "author": h.get("user") or "—",
             "license": "Pixabay Content License", "license_url": "https://pixabay.com/service/license-summary/",
             "source": h["pageURL"], "provider": "pixabay", "desc": h.get("tags") or ""} for h in d.get("hits", [])]


SOURCES = [pexels, pixabay, commons, openverse]
import urllib.error
cands, blocks = {}, []
for key, q in queries.items():
    found = []
    for fn in SOURCES:
        if len(found) >= PER_Q and fn in (commons, openverse):
            break
        try:
            found += fn(q)
        except Exception as e:
            print(key, fn.__name__, "failed", e, flush=True)
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
        ImageDraw.Draw(t).text((3, TH - 13), f"{len(keep)}: {c['title'][:30]}", fill="black")
        tiles.append(t)
        keep.append(c)
    cands[key] = keep
    rows = (PER_Q + 2) // 3
    block = Image.new("RGB", (TW * 3, TH * rows + 18), (235, 235, 235))
    ImageDraw.Draw(block).text((4, 3), f"[{key}] {q}", fill=(180, 0, 0))
    for i, t in enumerate(tiles):
        block.paste(t, ((i % 3) * TW, 18 + (i // 3) * TH))
    blocks.append(block)
    print(key, q, len(keep), flush=True)
    time.sleep(19 if os.environ.get("PEXELS_API_KEY") and not PEXELS_OFF else 1)

BH = TH * ((PER_Q + 2) // 3) + 18
for n in range(0, len(blocks), PACK):
    sheet = Image.new("RGB", (TW * 9 + 20, (BH + 10) * ((PACK + 2) // 3)), "white")
    for j, b in enumerate(blocks[n:n + PACK]):
        sheet.paste(b, ((j % 3) * (TW * 3 + 10), (j // 3) * (BH + 10)))
    sheet.save(f"{OUT}/pack_{n // PACK:03d}.jpg", quality=74)
json.dump(cands, open(f"{OUT}/candidates.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
