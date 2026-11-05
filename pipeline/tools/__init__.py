"""工具层：把现有 pipeline 能力登记成「带风险等级的工具」。

上层（harness / API / 界面）只认这里的注册表，不直接 import 业务函数。
风险等级和 critical 决定审批闸门，规则在 pipeline.harness.policy：

    fetch_source   read          读原文，任何档位都不停
    write_draft    write         写稿，step 档会停
    make_image     write         出图，step 档会停
    fill_editor    write+critical 填头条编辑器，standard 起就停
    publish        irreversible   真发布，任何档位都停

填稿和发布只通过 subprocess 调现有 CLI，本进程不 import patchright。
"""

from __future__ import annotations

from ..harness.policy import Risk
from ..harness.registry import ToolRegistry, ToolSpec
from . import drafts, editor, images, publisher, sources

TOOL_NAMES = (
    "fetch_source",
    "write_draft",
    "make_image",
    "fill_editor",
    "publish",
)


def register_tools(registry: ToolRegistry) -> ToolRegistry:
    """把五个工具登记进一个已有的注册表，返回同一个实例。"""
    registry.register(
        ToolSpec(
            name="fetch_source",
            description="抓一篇文章的正文和配图链接，给写稿当事实依据",
            risk=Risk.READ,
            func=sources.fetch_source,
            tags=("内容线", "取材"),
        )
    )
    registry.register(
        ToolSpec(
            name="write_draft",
            description="按平台 skill 把主题和原文写成标题、正文、标签",
            risk=Risk.WRITE,
            func=drafts.write_draft,
            tags=("内容线", "写作"),
        )
    )
    registry.register(
        ToolSpec(
            name="make_image",
            description="从正文里挑画面，调本地 ComfyUI 出配图",
            risk=Risk.WRITE,
            func=images.make_image,
            tags=("内容线", "配图"),
        )
    )
    registry.register(
        ToolSpec(
            name="fill_editor",
            description="把草稿填进头条编辑器，不点发布（subprocess 调 CLI）",
            risk=Risk.WRITE,
            critical=True,
            func=editor.fill_editor,
            tags=("内容线", "头条", "半自动"),
        )
    )
    registry.register(
        ToolSpec(
            name="publish",
            description="真的点头条发布，不可逆，必须人工确认（subprocess 调 CLI）",
            risk=Risk.IRREVERSIBLE,
            critical=True,
            func=publisher.publish,
            tags=("内容线", "头条", "发布"),
        )
    )
    return registry


def build_registry() -> ToolRegistry:
    """新建一份只含这五个工具的注册表。"""
    return register_tools(ToolRegistry())


REGISTRY = build_registry()

__all__ = ["TOOL_NAMES", "REGISTRY", "build_registry", "register_tools"]
