#!/usr/bin/env python3
"""Generate dish pictures with an open Stable Diffusion model on GitHub Actions CPU runners.

No API key and no paid service. For every dish the image model (LCM Dreamshaper v7, a fast
latent-consistency version of Stable Diffusion 1.5) draws several candidates; a second open
model, CLIP (openai/clip-vit-large-patch14), scores how well each candidate matches the dish
description and penalises typical failures (a burger, fried eggs, a figurine, text, an empty
plate...). The best candidate is kept; small copies of all candidates are kept for manual review.

Reads tools/photos/localgen.json:
  {"ids": [...], "steps": 6, "candidates": 4, "seed_offset": 0}
and tools/photos/prompts_v2.json: {"<id>": {"prompt": "...", "clip": "...", "avoid": [...]}}.
SHARD / SHARDS env vars split the ids between parallel jobs.
Writes out/photos/<id>.webp (384 px), out/cands/<id>_<k>.webp (192 px) and out/meta-<shard>.json.
"""
import json, os, time

import torch
from diffusers import DiffusionPipeline
from transformers import CLIPModel, CLIPProcessor

cfg = json.load(open("tools/photos/localgen.json", encoding="utf-8"))
prompts = json.load(open("tools/photos/prompts_v2.json", encoding="utf-8"))
shard, shards = int(os.environ.get("SHARD", "0")), int(os.environ.get("SHARDS", "1"))
ids = [str(i) for i in cfg["ids"]][shard::shards]
steps = int(cfg.get("steps", 6))
n_cand = int(cfg.get("candidates", 4))
size = int(cfg.get("size", 384))
model = cfg.get("model", "SimianLuo/LCM_Dreamshaper_v7")

torch.set_num_threads(os.cpu_count() or 4)
pipe = DiffusionPipeline.from_pretrained(model, torch_dtype=torch.float32, safety_checker=None)
pipe.to("cpu")
pipe.set_progress_bar_config(disable=True)
clip = CLIPModel.from_pretrained("openai/clip-vit-large-patch14").eval()
proc = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")

GENERIC_AVOID = ["a hamburger", "fried eggs", "a figurine or statue", "text or letters", "an empty plate",
                 "a person or hands", "raw uncooked ingredients", "a cake"]


@torch.no_grad()
def score(images, good, avoid):
    texts = [good] + avoid
    inp = proc(text=texts, images=images, return_tensors="pt", padding=True, truncation=True)
    out = clip(**inp)
    sims = out.logits_per_image / clip.logit_scale.exp()  # cosine similarity, images x texts
    good_s = sims[:, 0]
    bad_s = sims[:, 1:].max(dim=1).values if avoid else torch.zeros_like(good_s)
    return (good_s - 0.5 * torch.clamp(bad_s - good_s + 0.05, min=0)).tolist(), good_s.tolist(), bad_s.tolist()


os.makedirs("out/photos", exist_ok=True)
os.makedirs("out/cands", exist_ok=True)
meta = {}
for rid in ids:
    d = prompts.get(rid)
    if not d:
        continue
    t = time.time()
    g = torch.Generator("cpu").manual_seed(int(rid) * 7919 + int(cfg.get("seed_offset", 0)))
    ims = pipe(prompt=d["prompt"], num_inference_steps=steps, guidance_scale=8.0, width=512, height=512,
               num_images_per_prompt=n_cand, generator=g).images
    ims = [im.convert("RGB") for im in ims]
    title = d["clip"].lower()
    avoid = [a for a in GENERIC_AVOID + d.get("avoid", []) if a.split()[-1].rstrip("s") not in title]
    total, good, bad = score(ims, d["clip"], avoid)
    best = max(range(len(ims)), key=lambda k: total[k])
    for k, im in enumerate(ims):
        c = im.copy(); c.thumbnail((192, 192)); c.save(f"out/cands/{rid}_{k}.webp", "WEBP", quality=70)
    im = ims[best]; im.thumbnail((size, size))
    im.save(f"out/photos/{rid}.webp", "WEBP", quality=74, method=6)
    meta[rid] = {"model": model, "steps": steps, "prompt": d["prompt"], "best": best,
                 "score": [round(x, 4) for x in total], "match": [round(x, 4) for x in good], "bad": [round(x, 4) for x in bad]}
    print(rid, "best", best, [round(x, 3) for x in total], round(time.time() - t, 1), "s", flush=True)
json.dump(meta, open(f"out/meta-{shard}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("generated", len(meta))
