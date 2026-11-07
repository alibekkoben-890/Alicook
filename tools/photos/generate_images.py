#!/usr/bin/env python3
"""Generate dish images with the OpenAI Images API (runs on GitHub Actions).

Reads tools/photos/generate.json ({"recipe_id": "prompt"}). Skips ids listed in
tools/photos/generated_done.json. Writes out/photos/<id>.jpg and out/generated.json.
Needs the OPENAI_API_KEY secret; without it the job exits without doing anything.
LIMIT (env) caps how many images one run makes, to keep cost predictable.
"""
import base64, io, json, os, sys, time, urllib.request
from PIL import Image

key = os.environ.get("OPENAI_API_KEY")
if not key:
    print("OPENAI_API_KEY is not set; nothing to do.")
    sys.exit(0)
model = os.environ.get("IMAGE_MODEL") or "gpt-image-1"
limit = int(os.environ.get("LIMIT") or "50")
prompts = json.load(open("tools/photos/generate.json", encoding="utf-8"))
done_path = "tools/photos/generated_done.json"
done = set(json.load(open(done_path))) if os.path.exists(done_path) else set()
os.makedirs("out/photos", exist_ok=True)
made = {}
for rid, prompt in prompts.items():
    if rid in done or len(made) >= limit:
        continue
    body = json.dumps({"model": model, "prompt": prompt, "size": "1024x1024", "n": 1}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/images/generations", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read())
    except Exception as e:
        print(rid, "failed", e, flush=True)
        time.sleep(5)
        continue
    item = d["data"][0]
    raw = base64.b64decode(item["b64_json"]) if item.get("b64_json") else urllib.request.urlopen(item["url"]).read()
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((720, 720))
    im.save(f"out/photos/{rid}.jpg", "JPEG", quality=76, optimize=True, progressive=True)
    made[rid] = {"model": model, "prompt": prompt}
    print(rid, "ok", flush=True)
json.dump(made, open("out/generated.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("generated", len(made))
