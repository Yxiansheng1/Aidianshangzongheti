"""发布：把内容发到各平台。

支持范围完全由 social-auto-upload 决定，这里如实照抄，不假装支持：

    小红书   图文 upload-note / 视频 upload-video
    抖音     图文 upload-note / 视频 upload-video
    快手     图文 upload-note / 视频 upload-video
    知乎     长文 upload-article / 视频 upload-video（需 --originality）
    B站      只有视频（还要 --tid 分区）
    视频号   只有视频
    微博     只有视频（标题 ≤30 字）
    百家号   只有视频
    头条     **不支持** —— sau 里没有头条模块

skill 是「怎么写」，这里是「怎么发」。两回事，别混。

发布永远走 --headed（B站除外，它的 upload-video 没有这个参数）：
无头模式容易被平台识别为自动化。
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
    "抖音": {"note": True, "video": True},
    "快手": {"note": True, "video": True},
    "知乎": {"note": True, "video": True},
    "B站": {"note": False, "video": True},
    "视频号": {"note": False, "video": True},
    "微博": {"note": False, "video": True},
    "百家号": {"note": False, "video": True},
}

# 项目B 的 skill 名 → sau 的平台标识
SAU_PLATFORM = {
    "小红书": "xiaohongshu",
    "抖音": "douyin",
    "快手": "kuaishou",
    "知乎": "zhihu",
    "B站": "bilibili",
    "视频号": "tencent",
    "微博": "weibo",
    "百家号": "baijiahao",
}

# 有 skill 但发不了的平台，给出人话理由
NO_PUBLISH_REASON = {
    "头条": "头条号没有发布接口，不能自动发；点「填进头条编辑器」，"
            "工具把标题正文图片填好，发布那一下你自己点",
}

# 各平台发不同形态时的额外必填参数
ZHIHU_CATEGORY = "科技互联网"
BILIBILI_TID = "188"  # 188 科技 / 208 财经 / 201 生活


@dataclass
class PublishResult:
    platform: str
    command: str
    ok: bool
    returncode: int = 0
    output: str = ""


def can_publish(platform: str, kind: str) -> bool:
    return bool(TARGETS.get(platform, {}).get(kind))


def kinds(platform: str) -> list[str]:
    """这个平台能发什么形态。给界面用。"""
    row = TARGETS.get(platform) or {}
    return [k for k in ("note", "video") if row.get(k)]


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
    if platform in NO_PUBLISH_REASON:
        raise ValueError(f"不支持发布到{platform}：{NO_PUBLISH_REASON[platform]}")

    sau_platform = SAU_PLATFORM.get(platform)
    if not sau_platform:
        raise ValueError(f"没有这个平台的发布映射：{platform}。可选：{', '.join(SAU_PLATFORM)}")

    images = images or []
    kind = "video" if video else "note"

    if not can_publish(platform, kind):
        if kind == "note":
            raise ValueError(f"{platform} 只能发视频，先做视频（或改发小红书/抖音/快手/知乎）")
        raise ValueError(f"{platform} 不支持{kind}")

    if kind == "note" and not images:
        raise ValueError("图文发布需要至少一张图")
    if kind == "video" and not Path(video).is_file():
        raise ValueError(f"视频文件不存在：{video}")

    account = cfg.accounts.get(sau_platform, "main")
    product = {
        "id": platform,
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
        zhihu_category=ZHIHU_CATEGORY,
        bilibili_tid=BILIBILI_TID,
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
