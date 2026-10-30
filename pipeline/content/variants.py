"""一稿两版：同一篇内容，给两个账号各出一版。

为什么需要：头条明确打压「同一篇内容多号发布」（重复内容 / 批量发布）。
两个号要同步发，就必须是两版：事实完全一致，标题、开头、结构不同。

它不重新取材，只在已有稿子上换说法：
- 事实、数字、公司名、结论 —— 一个都不许变，也不许加新的
- 标题、开头、段落顺序、论证方式 —— 必须换
"""

from __future__ import annotations

import json
from typing import Any

from ..model.client import ModelError, OpenAICompatible
from .rewrite import SHARED_RULES, _loads_loose, load_skill, persona_block

SYSTEM = "你是同一个账号的另一个编辑。只输出 JSON，不要代码围栏，不要解释。"

VARIANT_PROMPT = """下面是已经写好的一版 {platform} 文案，请写**第二版**，给另一个账号发。

硬要求：
1. **事实完全不变**：数字、公司名、人名、结论，一个字都不许改，也不许新增任何事实
2. **换标题**：另一个说法，不要同义复述原标题，也不要标题党
3. **换开头**：不要复用第一版的第一句；换成另一种切入（数据前置 / 场景 / 反问 / 结论直给）
4. **换结构**：段落顺序或论证方式要不同（先结论后论证 ↔ 先现象后结论）
5. 字数、禁词、人称、emoji 仍然遵守这个平台原来的要求

第一版标题：{title}

第一版正文：
\"\"\"
{body}
\"\"\"

按这个 JSON 输出：
{{"title": "第二版标题", "body": "第二版正文"}}
"""


def make_variant(title: str, body: str, cfg: Any, *, platform: str = "小红书") -> dict[str, str]:
    """基于已有稿子写第二版。失败就抛错，不做兜底降级——发重复内容比报错更糟。"""
    if not cfg.has_model:
        raise ModelError("没有配置文本模型")

    client = OpenAICompatible(
        base_url=cfg.model.base_url,
        api_key=cfg.model.api_key,
        timeout=max(cfg.model.timeout, 240),
        text_model=cfg.model.text_model,
    )

    system = load_skill(platform) + persona_block() + SHARED_RULES
    raw = client.ask(
        VARIANT_PROMPT.format(platform=platform, title=title, body=body),
        system=system, max_tokens=8000, temperature=0.85,
    )
    data, _ = _loads_loose(raw)

    new_title = str(data.get("title") or "").strip()
    new_body = str(data.get("body") or "").strip()
    if not new_title or not new_body:
        raise ModelError(f"第二版没产出标题或正文：{raw[:200]}")

    # 同一句开头 = 不叫两版，等于复制
    if new_body[:20] == body[:20]:
        raise ModelError("第二版开头和第一版一样，等于重复内容，已放弃")

    return {"title": new_title, "body": new_body}


def to_json(variant: dict[str, str]) -> str:
    return json.dumps(variant, ensure_ascii=False, indent=1)
