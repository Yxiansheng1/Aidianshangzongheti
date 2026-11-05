"""验收检查：不接模型，也能看清"三档自主度下哪些工具会停下来等审批"。

    .venv\\Scripts\\python.exe scripts\\harness_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.harness.agent import _interrupt_on
from pipeline.harness.policy import Autonomy, AutonomyController, Risk
from pipeline.harness.registry import ToolRegistry


def demo_registry() -> ToolRegistry:
    reg = ToolRegistry()

    @reg.tool("fetch_source", "抓原文", Risk.READ)
    def _fetch() -> None: ...

    @reg.tool("write_draft", "写稿（关键步骤）", Risk.WRITE, critical=True)
    def _write() -> None: ...

    @reg.tool("make_image", "出配图", Risk.WRITE)
    def _image() -> None: ...

    @reg.tool("fill_editor", "填进平台编辑器", Risk.WRITE, critical=True)
    def _fill() -> None: ...

    @reg.tool("publish", "点发布", Risk.IRREVERSIBLE)
    def _publish() -> None: ...

    return reg


def main() -> None:
    reg = demo_registry()
    print("工具清单：")
    for item in reg.describe():
        mark = "需审批" if item["risk"] == "irreversible" else item["risk"]
        print(f"  · {item['name']:14s} {mark:12s} {item['description']}")

    print("\n三档自主度下的审批闸门：")
    for level in (Autonomy.AUTO, Autonomy.STANDARD, Autonomy.STEP):
        mapping = _interrupt_on(reg, AutonomyController(level))
        need = [k for k, v in mapping.items() if v]
        print(f"  {level.value:9s} 停：{', '.join(need) if need else '（不停）'}")

    # 降档演示
    c = AutonomyController(Autonomy.AUTO)
    for _ in range(2):
        c.record("make_image", ok=False)
    print("\n自动降档演示（make_image 连续失败 2 次）：")
    print(f"  make_image 现在是 {c.level_for('make_image').value}")
    for note in c.notes:
        print(f"  · {note}")


if __name__ == "__main__":
    main()
