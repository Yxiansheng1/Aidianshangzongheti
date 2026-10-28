"""social-auto-upload 的命令行适配。

不用字符串模板拼命令，直接构造 argv 列表。原因有两条：

1. `--images` 是 nargs="+"（空格分隔多值），不是逗号分隔，拼字符串必错；
2. 标题和正文里常有引号、换行、中文标点，shell 转义是无穷无尽的坑。

argv 列表交给 subprocess 时不会经过 shell，这些问题全部消失。

真实命令形态来自 sau_commands/*.py 源码：

    sau xiaohongshu upload-note --account main --images a.png b.png \\
        --title "..." --note "..." --tags "t1,t2" [--schedule "2026-01-01 10:00"] [--headed]

    sau xiaohongshu upload-video --account main --file v.mp4 \\
        --title "..." --desc "..." --tags "..." [--thumbnail cover.png]
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 各平台支持的动作。没有列出的平台走默认的 note/video 两种。
PLATFORM_ACTIONS: dict[str, dict[str, str]] = {
    "xiaohongshu": {"note": "upload-note", "video": "upload-video"},
    "douyin": {"note": "upload-note", "video": "upload-video"},
    "kuaishou": {"note": "upload-note", "video": "upload-video"},
    "bilibili": {"video": "upload-video"},
    "tencent": {"video": "upload-video"},
    "weibo": {"video": "upload-video"},
    "baijiahao": {"video": "upload-video"},
    "dayu": {"video": "upload-video"},
}

# 小红书的硬限制
MAX_TAGS_XHS = 10


@dataclass
class PublishPlan:
    platform: str
    product_id: str
    product_name: str
    argv: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def command(self) -> str:
        """只用于显示。执行走 argv，不经过 shell，所以这里的引号不影响运行。"""
        parts = []
        for arg in self.argv:
            parts.append(f'"{arg}"' if (not arg or " " in arg or "\t" in arg) else arg)
        return " ".join(parts)


def _clean(text: Any) -> str:
    """压成单行。正文里的换行会让部分平台排版错乱。"""
    return " ".join(str(text or "").split())


def build_plan(
    product: dict,
    platform: str,
    *,
    account: str,
    sau_cmd: str = "sau",
    kind: str = "note",
    schedule: str | None = None,
    headed: bool = False,
    extra: list[str] | None = None,
) -> PublishPlan:
    """构造一条发布命令。

    kind: "note"（图文）或 "video"（视频）
    """
    warnings: list[str] = []
    actions = PLATFORM_ACTIONS.get(platform, {})
    action = actions.get(kind) or {"note": "upload-note", "video": "upload-video"}[kind]

    argv: list[str] = [sau_cmd, platform, action, "--account", account]

    title = _clean(product.get("title") or product.get("name") or "")
    body = _clean(product.get("body") or "")
    tags = [t for t in (product.get("tags") or []) if t]

    if kind == "video":
        video = product.get("video")
        if not video:
            raise ValueError(f"商品 {product.get('name')} 没有 video 字段，无法按视频发布")
        if not Path(video).is_file():
            raise FileNotFoundError(f"视频文件不存在：{video}")
        argv += ["--file", str(Path(video).resolve()), "--title", title, "--desc", body]
    else:
        images = product.get("images") or []
        if not images:
            raise ValueError(f"商品 {product.get('name')} 没有图片，无法发布")
        for img in images:
            if not Path(img).is_file():
                raise FileNotFoundError(f"图片不存在：{img}")
        # nargs="+"：多张图跟在 --images 后面，空格分隔
        argv.append("--images")
        argv += [str(Path(i).resolve()) for i in images]
        argv += ["--title", title, "--note", body]

    if platform == "xiaohongshu" and len(tags) > MAX_TAGS_XHS:
        warnings.append(f"小红书标签最多 {MAX_TAGS_XHS} 个，已截断（原 {len(tags)} 个）")
        tags = tags[:MAX_TAGS_XHS]

    if tags:
        argv += ["--tags", ",".join(tags)]

    if schedule:
        argv += ["--schedule", schedule]

    if headed:
        argv.append("--headed")

    if extra:
        argv += extra

    return PublishPlan(
        platform=platform,
        product_id=str(product.get("id", "")),
        product_name=str(product.get("name", "")),
        argv=argv,
        warnings=warnings,
    )


def run(plan: PublishPlan, *, execute: bool = False, cwd: str | None = None) -> int:
    """执行或只打印。默认不执行。"""
    tag = "执行" if execute else "计划"
    print(f"[{tag}] {plan.platform:<12} {plan.product_name}")
    print("       " + plan.command)
    for warning in plan.warnings:
        print(f"       ⚠ {warning}")

    if not execute:
        return 0

    try:
        # 不经过 shell，所以不需要任何转义
        return subprocess.call(plan.argv, cwd=cwd)
    except FileNotFoundError:
        print(f"       找不到命令 {plan.argv[0]!r}，检查 config.toml 里的 publish.sau_cmd")
        return 127
    except OSError as exc:
        print(f"       启动失败：{exc}")
        return 1
