"""写稿：按平台 skill 把主题和原文写成可直接发的稿子。"""

from __future__ import annotations

from typing import Any

from ..config import load_config
from ..content.rewrite import rewrite


def write_draft(
    topic: str,
    *,
    platform: str = "头条",
    mode: str = "",
    source_text: str = "",
    extra: str = "",
    config_path: str = "",
) -> dict[str, Any]:
    """写一篇稿：标题、正文、标签，外加「哪些地方没依据」的 gaps。

    source_text 通常来自 fetch_source。有原文时模型只能改写事实，
    没原文才允许纯主题写作，但 gaps 会更多，发布前要人看。
    """
    if not str(topic or "").strip():
        raise ValueError("主题不能为空")

    cfg = load_config(config_path or None)
    result = rewrite(
        topic,
        source_text,
        cfg,
        platform=platform,
        mode=mode,
        extra=extra,
    )
    draft = dict(result)
    draft["ok"] = True
    return draft
