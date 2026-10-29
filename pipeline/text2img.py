"""文生图（SDXL）。

和 pipeline/model/comfyui.py 的区别：
    comfyui.py   Qwen-Image-Edit，图生图，必须给参考图 → 给电商做商品图
    text2img.py  SDXL 纯文生图，给一句话就出图 → 给内容流水线做配图

两个项目互不依赖，别混用。
"""

from __future__ import annotations

import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model.comfyui import ComfyClient, ComfyError

# SDXL 通用负向词
DEFAULT_NEGATIVE = (
    "lowres, blurry, watermark, text, signature, logo, username, "
    "bad anatomy, extra limbs, deformed, jpeg artifacts, worst quality, "
    "low quality, oversaturated, ugly"
)


@dataclass
class Text2ImgConfig:
    checkpoint: str = "animegodxl_v5.safetensors"
    width: int = 1024
    height: int = 1024
    steps: int = 25
    cfg: float = 7.0
    sampler: str = "dpmpp_2m"
    scheduler: str = "karras"
    wait_timeout: int = 600


def build_workflow(
    prompt: str,
    *,
    negative: str = DEFAULT_NEGATIVE,
    cfg: Text2ImgConfig | None = None,
    seed: int = 0,
    filename_prefix: str = "content",
) -> dict[str, Any]:
    """最简单的 SDXL 文生图接线。

    CheckpointLoaderSimple → 两个 CLIPTextEncode → EmptyLatentImage
    → KSampler → VAEDecode → SaveImage
    """
    cfg = cfg or Text2ImgConfig()

    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": cfg.checkpoint}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": cfg.width, "height": cfg.height, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {
                  "model": ["1", 0],
                  "seed": seed,
                  "steps": cfg.steps,
                  "cfg": cfg.cfg,
                  "sampler_name": cfg.sampler,
                  "scheduler": cfg.scheduler,
                  "positive": ["2", 0],
                  "negative": ["3", 0],
                  "latent_image": ["4", 0],
                  "denoise": 1.0,
              }},
        "6": {"class_type": "VAEDecode",
              "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage",
              "inputs": {"images": ["6", 0], "filename_prefix": filename_prefix}},
    }


def generate(
    client: ComfyClient,
    prompt: str,
    out_path: Path | str,
    *,
    cfg: Text2ImgConfig | None = None,
    **kwargs: Any,
) -> Path:
    """一句话 → 一张图。"""
    cfg = cfg or Text2ImgConfig()
    wait_timeout = int(kwargs.pop("wait_timeout", cfg.wait_timeout))

    workflow = build_workflow(prompt, cfg=cfg, **kwargs)
    prompt_id = client.queue(workflow)
    entry = client.wait(prompt_id, timeout=wait_timeout)

    images = client.output_images(entry)
    if not images:
        raise ComfyError("文生图没有产出")

    data = client.download(images[0])
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out


def check(model: str | None = None) -> dict[str, Any]:
    """检查 SDXL 能不能用。"""
    client = ComfyClient()
    if not client.is_up():
        return {"ok": False, "reason": "ComfyUI 没在跑"}

    try:
        options = client.node_options("CheckpointLoaderSimple", "ckpt_name")
    except ComfyError as exc:
        return {"ok": False, "reason": str(exc)}

    want = model or Text2ImgConfig().checkpoint
    return {
        "ok": want in options,
        "checkpoint": want,
        "available": options,
        "reason": "" if want in options else f"{want} 不在 checkpoint 列表里",
    }
