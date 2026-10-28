"""social-auto-upload 的命令行适配。

不用字符串模板拼命令，直接构造 argv 列表。原因：

1. `--images` 是 nargs="+"（空格分隔多值），不是逗号分隔，拼字符串必错；
2. 标题和正文里常有引号、换行、中文标点，shell 转义是无穷无尽的坑。

argv 列表交给 subprocess 时不会经过 shell，这些问题全部消失。

**各平台参数形态不一样**，这是最容易踩的坑：

    小红书   upload-note  --images a.png b.png --title T --note B --tags t1,t2
    抖音     upload-note  --images ...        --title T --note B --tags t1,t2
    知乎     upload-article --title T --content-file a.md      ← 正文走文件，不是参数
    知乎视频 upload-video  --file v.mp4 --title T --desc B --category C --originality original

所以下面用 PlatformSpec 描述每个平台的差异，而不是假设它们长一样。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import ROOT

CONTENT_DIR = ROOT / "output" / "_content"


@dataclass(frozen=True)
class PlatformSpec:
    """一个平台的发布形态约束。None 表示不支持这种形态。"""

    note_action: str | None
    video_action: str | None
    # 图文的正文怎么传
    note_style: str = "images"      # images = --note 内联；article = --content-file 外部文件
    # 视频的额外必填项
    video_style: str = "simple"     # simple = 只要 file/title/desc；zhihu = 还要 category/originality
    tag_limit: int | None = None
    title_max: int | None = None
    video_title_min: int | None = None
    video_title_max: int | None = None
    video_desc_max: int | None = None


PLATFORMS: dict[str, PlatformSpec] = {
    "xiaohongshu": PlatformSpec("upload-note", "upload-video", tag_limit=10),
    "douyin": PlatformSpec("upload-note", "upload-video"),
    "kuaishou": PlatformSpec("upload-note", "upload-video"),
    "zhihu": PlatformSpec(
        "upload-article",
        "upload-video",
        note_style="article",
        video_style="zhihu",
        title_max=100,
        video_title_min=5,
        video_title_max=50,
        video_desc_max=300,
    ),
    "bilibili": PlatformSpec(None, "upload-video"),
    "tencent": PlatformSpec(None, "upload-video"),
    "weibo": PlatformSpec(None, "upload-video"),
    "baijiahao": PlatformSpec(None, "upload-video"),
    "dayu": PlatformSpec(None, "upload-video"),
    "hupu": PlatformSpec(None, "upload-video"),
}


@dataclass
class PublishPlan:
    platform: str
    product_id: str
    product_name: str
    argv: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)

    @property
    def command(self) -> str:
        """只用于显示。执行走 argv，不经过 shell，引号不影响运行。"""
        parts = []
        for arg in self.argv:
            parts.append(f'"{arg}"' if (not arg or " " in arg or "\t" in arg) else arg)
        return " ".join(parts)


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def resolve_sau(sau_cmd: str = "sau", sau_cwd: str = "") -> str:
    """把 sau 解析成可执行文件路径。

    sau 装在工作目录的 .venv 里，通常不在 PATH 上。裸名字时先看那里面，
    找不到再交给系统 PATH。
    """
    if not sau_cmd:
        return "sau"

    candidate = Path(sau_cmd)
    if candidate.is_absolute() or candidate.parent != Path("."):
        return str(candidate)

    if sau_cwd:
        base = Path(sau_cwd) / ".venv" / "Scripts"
        for name in (f"{sau_cmd}.exe", sau_cmd):
            exe = base / name
            if exe.is_file():
                return str(exe)

    return sau_cmd


def _fit_title(title: str, spec: PlatformSpec, warnings: list[str]) -> str:
    if spec.title_max and len(title) > spec.title_max:
        warnings.append(f"标题超过 {spec.title_max} 字，已截断")
        title = title[: spec.title_max]
    return title


def _fit_video_title(title: str, spec: PlatformSpec, warnings: list[str]) -> str:
    if spec.video_title_max and len(title) > spec.video_title_max:
        warnings.append(f"视频标题超过 {spec.video_title_max} 字，已截断")
        title = title[: spec.video_title_max]
    if spec.video_title_min and len(title) < spec.video_title_min:
        warnings.append(f"视频标题少于 {spec.video_title_min} 字，已补足")
        title = (title + "商品实拍分享")[: max(spec.video_title_min, len(title))]
    return title


def _write_article(product: dict, images: list[str], body: str) -> tuple[Path, str]:
    """知乎长文要一个正文文件，图片路径按 Markdown 插在原稿里。"""
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"zhihu-{product.get('id') or 'item'}.md"
    target = CONTENT_DIR / name

    lines: list[str] = []
    if images:
        lines.append(f"![封面]({images[0]})")
        lines.append("")
    if body:
        lines.append(body)
        lines.append("")
    for index, image in enumerate(images[1:], 1):
        lines.append(f"![图{index}]({image})")
        lines.append("")

    target.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return target, str(target)


def build_plan(
    product: dict,
    platform: str,
    *,
    account: str,
    sau_cmd: str = "sau",
    kind: str = "note",
    schedule: str | None = None,
    headed: bool = False,
    zhihu_category: str = "家居生活",
    extra: list[str] | None = None,
) -> PublishPlan:
    """构造一条发布命令。kind: "note"（图文/长文）或 "video"。"""
    if platform not in PLATFORMS:
        raise ValueError(f"不支持的平台：{platform}。可选：{', '.join(sorted(PLATFORMS))}")

    spec = PLATFORMS[platform]
    action = spec.note_action if kind == "note" else spec.video_action
    if not action:
        raise ValueError(f"{platform} 不支持{kind}发布")

    warnings: list[str] = []
    artifacts: list[str] = []
    argv: list[str] = [sau_cmd, platform, action, "--account", account]

    title = _clean(product.get("title") or product.get("name") or "")
    body = _clean(product.get("body") or "")
    tags = [t for t in (product.get("tags") or []) if t]
    images = [str(Path(i).resolve()) for i in (product.get("images") or [])]

    if kind == "note":
        if not images:
            raise ValueError(f"{product.get('name')} 没有图片")
        for image in images:
            if not Path(image).is_file():
                raise FileNotFoundError(f"图片不存在：{image}")

        if spec.note_style == "article":
            content_file, _ = _write_article(product, images, body)
            argv += [
                "--title", _fit_title(title, spec, warnings),
                "--content-file", str(content_file),
            ]
            artifacts.append(str(content_file))
        else:
            argv.append("--images")
            argv += images
            argv += ["--title", title, "--note", body]
    else:
        video = product.get("video")
        if not video:
            raise ValueError(f"{product.get('name')} 没有 video 字段，无法按视频发布")
        video_path = Path(video).resolve()
        if not video_path.is_file():
            raise FileNotFoundError(f"视频不存在：{video}")
        if spec.video_style == "zhihu" and video_path.stat().st_size < 100 * 1024:
            warnings.append("知乎要求视频大于 100KB，当前文件可能被拒")

        argv += ["--file", str(video_path)]
        if spec.video_style == "zhihu":
            argv += [
                "--title", _fit_video_title(title, spec, warnings),
                "--desc", body[: spec.video_desc_max] if spec.video_desc_max else body,
                "--category", zhihu_category,
                "--originality", "original",
            ]
        else:
            argv += ["--title", title, "--desc", body]

    if tags:
        if spec.tag_limit and len(tags) > spec.tag_limit:
            warnings.append(f"{platform} 标签最多 {spec.tag_limit} 个，已截断")
            tags = tags[: spec.tag_limit]
        # 知乎不接受 --tags（话题走页面选择），跳过
        if platform != "zhihu":
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
        artifacts=artifacts,
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
        return subprocess.call(plan.argv, cwd=cwd)
    except FileNotFoundError:
        print(f"       找不到命令 {plan.argv[0]!r}，检查 config.toml 里的 publish.sau_cmd")
        return 127
    except OSError as exc:
        print(f"       启动失败：{exc}")
        return 1
