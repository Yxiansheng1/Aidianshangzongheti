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

PLAN_PROMPT = """从下面这篇要发小红书的文案里，挑 {n} 个最值得配图的画面。

要求：
- 画面要支撑文案的情绪或观点，不是随便的风景照
- 写英文 SDXL 提示词，结构是：主体 + 场景 + 光线 + 镜头/景深 + 风格
- 画面里不要出现文字、logo、可识别的真人脸
- 每条 prompt 30-60 个英文单词
- 风格统一：写实摄影感，柔和自然光，低饱和

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
        generate(client, scene["prompt"], target, cfg=t2i, seed=index * 1000)
        scene["file"] = str(target)
        out.append(target)
    return out
