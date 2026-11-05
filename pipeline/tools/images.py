"""出图：从写好的稿子里挑画面，再用本地 ComfyUI 生成配图。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import ROOT, load_config
from ..content import visual


def make_image(
    title: str,
    body: str,
    *,
    platform: str = "头条",
    count: int = 2,
    out_dir: str = "",
    config_path: str = "",
) -> dict[str, Any]:
    """按正文排画面并出图，返回落盘路径。

    画面必须挂到正文里的原话上，对不上的会被 visual.plan 丢掉；
    一张都排不出来就报错，不拿氛围图硬凑。
    """
    if not str(title or "").strip() or not str(body or "").strip():
        raise ValueError("出图需要标题和正文")
    if not 1 <= int(count) <= 6:
        raise ValueError("出图张数要在 1 到 6 之间")

    cfg = load_config(config_path or None)

    if out_dir:
        folder = Path(out_dir)
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        folder = ROOT / "output" / "内容" / f"{stamp}-工具出图"

    scenes = visual.plan(title, body, cfg, n=count, platform=platform)
    if not scenes:
        raise RuntimeError("没有排出可用画面（提示词没落到正文上），这次没出图")

    files = visual.render(scenes, cfg, folder, prefix="img")
    return {
        "ok": True,
        "count": len(files),
        "files": [str(path) for path in files],
        "dir": str(folder),
        "scenes": scenes,
    }
