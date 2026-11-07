#!/usr/bin/env python3
"""Download chosen photos and resize them to 800 px for the APK.

Reads tools/photos/selection.json ({"recipe_id": {"url": ..., ...credit}}),
writes out/photos/<id>.jpg and out/credits.json. Runs on GitHub Actions.
"""
import io, json, os, sys, time, urllib.request
from PIL import Image, ImageOps

UA = "AliCookPhotoCollector/1.0 (https://github.com/alibekkoben-890/Alicook)"
OUT = sys.argv[2] if len(sys.argv) > 2 else "out"
os.makedirs(f"{OUT}/photos", exist_ok=True)
sel = json.load(open(sys.argv[1], encoding="utf-8"))
done = {}
for rid, c in sel.items():
    for a in range(4):
        try:
            req = urllib.request.Request(c["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            break
        except Exception as e:
            print(rid, "retry", e, flush=True)
            time.sleep(10 * (a + 1))
    else:
        continue
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    im.thumbnail((800, 800))
    im.save(f"{OUT}/photos/{rid}.jpg", "JPEG", quality=78, optimize=True, progressive=True)
    done[rid] = c
    print(rid, "ok", im.size, flush=True)
    time.sleep(2)
json.dump(done, open(f"{OUT}/credits.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
