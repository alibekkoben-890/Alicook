#!/usr/bin/env python3
"""Make one test request per photo API and print whether its key works (never prints the key)."""
import json, os, urllib.error, urllib.parse, urllib.request

UA = "AliCookPhotoCollector/1.0 (https://github.com/alibekkoben-890/Alicook)"


def check(name, url, headers=None):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read())
        n = len(d.get("hits") or d.get("photos") or [])
        print(f"{name}: OK, test search returned {n} photos")
    except urllib.error.HTTPError as e:
        print(f"{name}: FAILED, HTTP {e.code} {e.reason}")
    except Exception as e:
        print(f"{name}: FAILED, {type(e).__name__}")


for name in ("PIXABAY_API_KEY",):
    v = os.environ.get(name, "")
    print(f"{name}: {'set' if v else 'NOT SET'}, length {len(v)}, has spaces: {v != v.strip()}, "
          f"contains '=': {'=' in v}, contains name: {name in v}")
px = os.environ.get("PIXABAY_API_KEY", "").strip()
if px:
    check("Pixabay", "https://pixabay.com/api/?" + urllib.parse.urlencode(dict(key=px, q="pasta", image_type="photo")))
