"""配图：从文案里提取画面，再用 SDXL 文生图。

两条路都支持：
    plan()   让模型从文案里挑最值得配的画面，输出英文 SDXL 提示词
    render() 用 text2img 逐张出图

不抓原文配图（版权风险），只走纯文生图。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..model.client import ModelError, OpenAICompatible
from ..model.comfyui import ComfyClient
from ..text2img import Text2ImgConfig, generate

SYSTEM = "你是视觉策划。只输出 JSON，不要代码围栏，不要解释。"

# 所有配图统一的风格。小红书调性是「生活实拍」，不是商业图库。
STYLE_SUFFIX = (
    ", warm natural light, cozy lived-in interior, everyday objects with texture, "
    "shallow depth of field, 35mm film look, muted warm tones, quiet mood, "
    "no text, no logo, no watermark, no human face"
)

NEGATIVE = (
    "corporate, business suit, skyscraper, city skyline, office building, "
    "neon, cold blue tone, stock photo, studio lighting, plastic look, "
    "text, watermark, logo, signature, human face, portrait, "
    "lowres, blurry, deformed, jpeg artifacts, worst quality"
)

PLAN_PROMPT = """从下面这篇要发**小红书**的文案里，挑 {n} 个最值得配图的画面。

这是小红书配图，不是商业图库、不是新闻配图。调性要求：

- **生活化实拍感**：像一个人在自己家里用手机/相机随手拍的
- **有具体物件**：桌面、书本、杯子、植物、衣物、食物、窗台、地板纹理
- **暖色调**：窗光、台灯、黄昏；不要冷蓝调、不要霓虹
- **不出现人脸**：可以拍手、背影、局部、空镜
- **不要**：西装、办公室、城市天际线、企业形象照、纯色背景产品图
- 画面要能支撑文案的情绪，不是随便的风景

写英文 SDXL 提示词，结构：主体 + 具体物件 + 场景 + 光线 + 镜头
每条 25–50 个英文单词。不要写文字、logo、人脸。

文案标题：{title}

文案正文：
\"\"\"
{body}
\"\"\"

按这个 JSON 输出：
{{"scenes": [{{"scene": "中文一句话说这张画什么", "prompt": "English SDXL prompt"}}]}}
"""


def _strip_fence(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return (fenced.group(1) if fenced else text).strip()


def plan(title: str, body: str, cfg: Any, *, n: int = 2) -> list[dict[str, str]]:
    """让模型给出配图方案。"""
    if not cfg.has_model:
        raise ModelError("没有配置文本模型")

    client = OpenAICompatible(
        base_url=cfg.model.base_url,
        api_key=cfg.model.api_key,
        timeout=max(cfg.model.timeout, 120),
        text_model=cfg.model.text_model,
    )
    raw = client.ask(
        PLAN_PROMPT.format(n=n, title=title, body=body[:3000]),
        system=SYSTEM, max_tokens=1500, temperature=0.7,
    )
    data = json.loads(_strip_fence(raw))

    scenes: list[dict[str, str]] = []
    for item in data.get("scenes") or []:
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt") or "").strip()
        if prompt:
            scenes.append({
                "scene": str(item.get("scene") or ""),
                "prompt": prompt,
            })
    return scenes[:n]


def render(
    scenes: list[dict[str, str]],
    cfg: Any,
    out_dir: Path | str,
    *,
    prefix: str = "content",
    size: tuple[int, int] = (832, 1216),
    steps: int = 20,
) -> list[Path]:
    """按方案逐张出图。ComfyUI 没起来就抛错。"""
    client = ComfyClient()
    if not client.is_up():
        raise RuntimeError("ComfyUI 没在跑，先启动 启动工作台.bat")

    t2i = Text2ImgConfig(
        width=size[0], height=size[1], steps=steps,
    )

    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)

    out: list[Path] = []
    for index, scene in enumerate(scenes, 1):
        target = folder / f"{prefix}-{index}.png"
        # 统一后缀 + 统一负向词，保证多张图风格一致
        prompt = scene["prompt"].rstrip(" .,") + STYLE_SUFFIX
        generate(
            client, prompt, target,
            cfg=t2i, seed=index * 1000,
            negative=NEGATIVE,
        )
        scene["final_prompt"] = prompt
        scene["file"] = str(target)
        out.append(target)
    return out
