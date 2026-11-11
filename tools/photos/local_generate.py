#!/usr/bin/env python3
"""Generate dish pictures with an open Stable Diffusion model on the GitHub Actions CPU runner.

No API key and no paid service: the model (LCM Dreamshaper v7, a fast latent-consistency
version of Stable Diffusion 1.5) is downloaded from Hugging Face inside the job.

Reads tools/photos/localgen.json ({"ids": [...], "steps": 6}) and the prompts in
tools/photos/generate.json. SHARD / SHARDS env vars split the ids between parallel jobs.
Writes out/photos/<id>.webp (384 px) and out/meta-<shard>.json.
"""
import json, os, time

import torch
from diffusers import DiffusionPipeline

cfg = json.load(open("tools/photos/localgen.json", encoding="utf-8"))
prompts = json.load(open("tools/photos/generate.json", encoding="utf-8"))
shard, shards = int(os.environ.get("SHARD", "0")), int(os.environ.get("SHARDS", "1"))
ids = [str(i) for i in cfg["ids"]][shard::shards]
steps = int(cfg.get("steps", 6))
size = int(cfg.get("size", 384))
model = cfg.get("model", "SimianLuo/LCM_Dreamshaper_v7")

torch.set_num_threads(os.cpu_count() or 4)
pipe = DiffusionPipeline.from_pretrained(model, torch_dtype=torch.float32, safety_checker=None)
pipe.to("cpu")
pipe.set_progress_bar_config(disable=True)

os.makedirs("out/photos", exist_ok=True)
meta = {}
for rid in ids:
    p = prompts.get(rid)
    if not p:
        continue
    p = p.replace("Realistic appetizing food photograph of", "Professional food photography, close-up of") + " Highly detailed, appetizing, sharp focus."
    t = time.time()
    g = torch.Generator("cpu").manual_seed(int(rid) * 7919)
    im = pipe(prompt=p, num_inference_steps=steps, guidance_scale=8.0, width=512, height=512, generator=g).images[0]
    im = im.convert("RGB")
    im.thumbnail((size, size))
    im.save(f"out/photos/{rid}.webp", "WEBP", quality=74, method=6)
    meta[rid] = {"model": model, "steps": steps, "prompt": p}
    print(rid, "ok", round(time.time() - t, 1), "s", flush=True)
json.dump(meta, open(f"out/meta-{shard}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("generated", len(meta))
