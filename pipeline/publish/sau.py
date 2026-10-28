"""social-auto-upload 的命令行适配。

刻意做成「模板驱动」：命令长什么样写在 config.toml 里，
代码不猜 CLI 的参数名。这样对方改版时，你只改配置，不改代码。
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Any

DEFAULT_TEMPLATE = (
    '{sau} {platform} upload --images "{images}" --title "{title}" '
    '--desc "{desc}" --tags "{tags}"'
)


@dataclass
class PublishPlan:
    platform: str
    product_id: str
    product_name: str
    command: str


def _q(value: Any) -> str:
    """把值压成单行并转义双引号。

    正文常带换行，直接塞进命令行会把一条命令拆成好几条，所以必须压平。
    """
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace('"', '\\"')


def build_plan(
    product: dict,
    platform: str,
    *,
    sau_cmd: str = "sau",
    templates: dict[str, str] | None = None,
) -> PublishPlan:
    templates = templates or {}
    template = templates.get(platform) or DEFAULT_TEMPLATE

    images = ",".join(product.get("images", []))
    tags = ",".join(product.get("tags", []) or [])
    title = _q(product.get("title") or product.get("name") or "")
    desc = _q(product.get("body") or "")

    command = template.format(
        sau=sau_cmd,
        platform=platform,
        images=images,
        title=title,
        desc=desc,
        tags=tags,
    )

    return PublishPlan(
        platform=platform,
        product_id=str(product.get("id", "")),
        product_name=str(product.get("name", "")),
        command=command,
    )


def run(plan: PublishPlan, *, execute: bool = False) -> int:
    """执行或只打印。

    默认不执行。即使 --execute，也建议先用小号、单平台、单条试。
    """
    tag = "执行" if execute else "计划"
    print(f"[{tag}] {plan.platform:12s} {plan.product_name}")
    print(f"       {plan.command}")

    if not execute:
        return 0

    try:
        return subprocess.call(plan.command, shell=True)
    except OSError as exc:
        print(f"       启动失败：{exc}")
        return 1
