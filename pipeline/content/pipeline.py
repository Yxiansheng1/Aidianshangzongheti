"""把流水线串起来。

    抓文章 → 改写 → 审核 → 配图 → 落盘

每一步失败都能单独看出来，不会糊成一团。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..article import ArticleError, fetch
from ..review import review
from ..config import ROOT

OUT_DIR = ROOT / "output" / "内容"


def run(
    url: str,
    cfg: Any,
    *,
    platform: str = "小红书",
    images: int = 2,
    draw: bool = True,
    article: dict | None = None,
) -> dict[str, Any]:
    """跑完整流程。

    article 可以直接传 {"title": ..., "text": ...} 跳过抓取（给粘贴内容用）。
    """
    from . import rewrite as rw
    from . import visual as vs

    result: dict[str, Any] = {
        "url": url,
        "platform": platform,
        "started": datetime.now().isoformat(timespec="seconds"),
        "steps": {},
    }

    # ① 抓文章
    if article:
        title = str(article.get("title") or "")
        text = str(article.get("text") or "")
        result["steps"]["fetch"] = {"ok": True, "chars": len(text), "from": "input"}
    else:
        page = fetch(url, proxy=cfg.trends.proxy or None)
        if not page.ok:
            result["steps"]["fetch"] = {"ok": False, "reason": page.note}
            result["ok"] = False
            return result
        title = page.title or url
        text = page.text
        result["steps"]["fetch"] = {"ok": True, "chars": page.chars, "title": page.title}

    if len(text) < 200:
        result["steps"]["fetch"]["note"] = "正文太短，改写时容易编"

    # ② 改写
    try:
        draft = rw.rewrite(title, text, cfg, platform=platform)
        result["steps"]["rewrite"] = {"ok": True, "title": draft["title"], "length": draft["length"]}
    except Exception as exc:  # noqa: BLE001
        result["steps"]["rewrite"] = {"ok": False, "reason": str(exc)}
        result["ok"] = False
        return result

    result["draft"] = draft

    # 统一用同一个时间戳，避免文案和图落到不同目录
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = OUT_DIR / stamp

    # ③ 审核
    try:
        checked = review(f"{draft['title']}\n\n{draft['body']}", platform, cfg)
        result["steps"]["review"] = {
            "ok": True,
            "passed": checked.passed,
            "score": checked.score,
            "issues": [i.as_dict() for i in checked.issues],
        }
    except Exception as exc:  # noqa: BLE001
        result["steps"]["review"] = {"ok": False, "reason": str(exc)}

    # ④ 配图
    if draw:
        try:
            scenes = vs.plan(draft["title"], draft["body"], cfg, n=images)
            files = vs.render(scenes, cfg, folder, prefix="img")
            result["steps"]["visual"] = {
                "ok": True,
                "count": len(files),
                "files": [str(f) for f in files],
                "scenes": scenes,
            }
        except Exception as exc:  # noqa: BLE001
            result["steps"]["visual"] = {"ok": False, "reason": str(exc)}
    else:
        result["steps"]["visual"] = {"ok": True, "skipped": True}

    result["ok"] = True
    result["finished"] = datetime.now().isoformat(timespec="seconds")

    # 落盘
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (folder / "文案.md").write_text(rw.render_markdown(draft), encoding="utf-8")
    result["dir"] = str(folder)

    return result
