#!/usr/bin/env python3
"""Generate dish pictures with SDXL-Lightning (open model, free) on GitHub Actions CPU runners.

Stronger than the LCM Dreamshaper v7 (Stable Diffusion 1.5) pipeline in local_generate.py:
SDXL base 1.0 with the ByteDance SDXL-Lightning 4-step UNet. No API key, no paid service.

Memory plan for a 16 GB runner (everything runs in float32 on CPU):
  1. load the SDXL pipeline, encode all prompts of this shard, drop both text encoders;
  2. draw the candidates with the UNet + VAE and save them, then drop the pipeline;
  3. load CLIP (openai/clip-vit-large-patch14) and pick the best candidate per dish.

Reads tools/photos/sdxl.json:
  {"ids": [...], "candidates": 2, "size": 768, "steps": 4, "seed_offset": 0, "pick": {"<id>": k}}
and tools/photos/prompts_v2.json: {"<id>": {"prompt": "...", "clip": "...", "avoid": [...]}}.
SHARD / SHARDS env vars split the ids between parallel jobs.
Writes out/photos/<id>.webp (512 px), out/cands/<id>_<k>.webp (256 px) and out/meta-<shard>.json.
"""
import gc, json, os, time

import torch
from PIL import Image

cfg = json.load(open("tools/photos/sdxl.json", encoding="utf-8"))
prompts = json.load(open("tools/photos/prompts_v2.json", encoding="utf-8"))
shard, shards = int(os.environ.get("SHARD", "0")), int(os.environ.get("SHARDS", "1"))
ids = [str(i) for i in cfg["ids"]][shard::shards]
ids = [i for i in ids if i in prompts]
n_cand = int(cfg.get("candidates", 2))
size = int(cfg.get("size", 768))
steps = int(cfg.get("steps", 4))
BASE = "stabilityai/stable-diffusion-xl-base-1.0"
LIGHTNING = ("ByteDance/SDXL-Lightning", f"sdxl_lightning_{steps}step_unet.safetensors")
MODEL = f"{BASE} + {LIGHTNING[0]} ({steps}-step UNet)"
torch.set_num_threads(os.cpu_count() or 4)
os.makedirs("out/photos", exist_ok=True)
os.makedirs("out/cands", exist_ok=True)
os.makedirs("work", exist_ok=True)
if not ids:
    print("nothing to do"); raise SystemExit(0)

# 1-2. Draw the candidates.
from diffusers import EulerDiscreteScheduler, StableDiffusionXLPipeline, UNet2DConditionModel
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file

t0 = time.time()
unet = UNet2DConditionModel.from_config(BASE, subfolder="unet")
unet.load_state_dict(load_file(hf_hub_download(*LIGHTNING)))
pipe = StableDiffusionXLPipeline.from_pretrained(BASE, unet=unet, torch_dtype=torch.float32, variant="fp16")
pipe.scheduler = EulerDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing="trailing")
pipe.set_progress_bar_config(disable=True)
print("loaded in", round(time.time() - t0), "s", flush=True)

emb = {}
with torch.no_grad():
    for rid in ids:
        pe, _, pp, _ = pipe.encode_prompt(prompts[rid]["prompt"], device="cpu", num_images_per_prompt=1,
                                          do_classifier_free_guidance=False)
        emb[rid] = (pe, pp)
pipe.text_encoder = pipe.text_encoder_2 = None
gc.collect()
init_imgs = cfg.get("init", {})  # optional colour/layout sketch per dish (img2img)
strength = float(cfg.get("strength", 0.75))
i2i = None
if any(rid in init_imgs for rid in ids):
    from diffusers import StableDiffusionXLImg2ImgPipeline
    i2i = StableDiffusionXLImg2ImgPipeline(**pipe.components)
    i2i.set_progress_bar_config(disable=True)

for rid in ids:
    t = time.time()
    pe, pp = emb[rid]
    for k in range(n_cand):
        g = torch.Generator("cpu").manual_seed(int(rid) * 7919 + int(cfg.get("seed_offset", 0)) + k)
        with torch.no_grad():
            if rid in init_imgs:
                init = Image.open(init_imgs[rid]).convert("RGB").resize((size, size))
                im = i2i(prompt_embeds=pe, pooled_prompt_embeds=pp, image=init, strength=strength,
                         num_inference_steps=int(round(steps / strength)), guidance_scale=0.0, generator=g).images[0]
            else:
                im = pipe(prompt_embeds=pe, pooled_prompt_embeds=pp, num_inference_steps=steps, guidance_scale=0.0,
                          width=size, height=size, generator=g).images[0]
        im.convert("RGB").save(f"work/{rid}_{k}.png")
    print(rid, "drawn", n_cand, "in", round(time.time() - t, 1), "s", flush=True)
del pipe, unet, emb, i2i
gc.collect()

# 3. Pick the best candidate with CLIP.
from transformers import CLIPModel, CLIPProcessor

clip = CLIPModel.from_pretrained("openai/clip-vit-large-patch14").eval()
proc = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")
GENERIC_AVOID = ["a hamburger", "fried eggs", "a figurine or statue", "text or letters", "an empty plate",
                 "a person or hands", "raw uncooked ingredients", "a cake", "a watermark or signature"]


@torch.no_grad()
def score(images, good, avoid):
    inp = proc(text=[good] + avoid, images=images, return_tensors="pt", padding=True, truncation=True)
    out = clip(**inp)
    sims = out.logits_per_image / clip.logit_scale.exp()
    good_s = sims[:, 0]
    bad_s = sims[:, 1:].max(dim=1).values if avoid else torch.zeros_like(good_s)
    return (good_s - 0.5 * torch.clamp(bad_s - good_s + 0.05, min=0)).tolist(), good_s.tolist(), bad_s.tolist()


meta = {}
for rid in ids:
    d = prompts[rid]
    ims = [Image.open(f"work/{rid}_{k}.png").convert("RGB") for k in range(n_cand)]
    title = d["clip"].lower()
    avoid = [a for a in GENERIC_AVOID + d.get("avoid", []) if a.split()[-1].rstrip("s") not in title]
    total, good, bad = score(ims, d["clip"], avoid)
    best = max(range(n_cand), key=lambda k: total[k])
    if rid in cfg.get("pick", {}):  # manual choice after review
        best = int(cfg["pick"][rid])
    for k, im in enumerate(ims):
        c = im.copy(); c.thumbnail((256, 256)); c.save(f"out/cands/{rid}_{k}.webp", "WEBP", quality=72)
    im = ims[best].copy(); im.thumbnail((512, 512))
    im.save(f"out/photos/{rid}.webp", "WEBP", quality=76, method=6)
    meta[rid] = {"model": MODEL, "steps": steps, "size": size, "prompt": d["prompt"], "best": best,
                 "score": [round(x, 4) for x in total], "match": [round(x, 4) for x in good], "bad": [round(x, 4) for x in bad]}
json.dump(meta, open(f"out/meta-{shard}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("generated", len(meta), "total", round(time.time() - t0), "s")
