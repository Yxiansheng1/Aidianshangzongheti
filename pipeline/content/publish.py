"""发布：把内容发到各平台。

支持范围受 social-auto-upload 限制：
    小红书  图文（--images）/ 视频（--file）
    百家号  只有视频
    头条    不支持（sau 没有头条模块）

发布永远走 --headed：无头模式容易被平台识别为自动化。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..publish.sau import build_plan, resolve_sau

# 能发什么，写死成表，别让上层猜
TARGETS: dict[str, dict[str, bool]] = {
    "小红书": {"note": True, "video": True},
    "百家号": {"note": False, "video": True},
}

# 项目B 的 skill 名 → sau 的平台标识
SAU_PLATFORM = {
    "小红书": "xiaohongshu",
    "百家号": "baijiahao",
}


@dataclass
class PublishResult:
    platform: str
    command: str
    ok: bool
    returncode: int = 0
    output: str = ""


def can_publish(platform: str, kind: str) -> bool:
    return bool(TARGETS.get(platform, {}).get(kind))


def build(
    platform: str,
    *,
    title: str,
    body: str,
    tags: list[str],
    images: list[str] | None = None,
    video: str = "",
    cfg: Any,
) -> dict[str, Any]:
    """生成发布命令。不执行。"""
    sau_platform = SAU_PLATFORM.get(platform)
    if not sau_platform:
        raise ValueError(f"不支持发布到 {platform}。可选：{', '.join(SAU_PLATFORM)}")

    images = images or []
    kind = "video" if video else "note"

    if not can_publish(platform, kind):
        if kind == "note" and platform == "百家号":
            raise ValueError("百家号只能发视频，先做视频")
        raise ValueError(f"{platform} 不支持{kind}")

    if kind == "note" and not images:
        raise ValueError("图文发布需要至少一张图")
    if kind == "video" and not Path(video).is_file():
        raise ValueError(f"视频文件不存在：{video}")

    account = cfg.accounts.get(sau_platform, "main")
    product = {
        "name": title,
        "title": title,
        "body": body,
        "tags": tags,
        "images": images,
        "video": video,
    }

    plan = build_plan(
        product,
        sau_platform,
        account=account,
        sau_cmd=resolve_sau(cfg.sau_cmd, cfg.sau_cwd),
        kind=kind,
        headed=True,
    )
    return {"platform": platform, "kind": kind, "command": plan.command,
            "argv": plan.argv, "warnings": plan.warnings}


def execute(platform: str, cfg: Any, **kwargs: Any) -> PublishResult:
    """真的发出去。"""
    payload = build(platform, cfg=cfg, **kwargs)
    try:
        result = subprocess.run(
            payload["argv"],
            cwd=cfg.sau_cwd or None,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return PublishResult(platform, payload["command"], False, -1, "超过 600 秒没结束，去 logs 看")

    output = (result.stdout or "") + (result.stderr or "")
    ok = result.returncode == 0 and ("发布成功" in output or "upload submitted" in output)
    return PublishResult(platform, payload["command"], ok, result.returncode, output[-1500:])
