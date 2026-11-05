"""抓原文：把一篇文章的正文取下来，给写稿当事实依据。"""

from __future__ import annotations

from typing import Any

from ..article import fetch as fetch_article


def fetch_source(url: str, *, proxy: str = "", timeout: int = 25) -> dict[str, Any]:
    """抓一篇文章的标题、正文和配图链接。

    只读，不改任何东西。抓不到不算异常：ok=False，note 里写原因，
    让上层决定是换链接还是让人手动粘贴。
    """
    page = fetch_article(url, proxy=proxy or None, timeout=timeout)
    return {
        "ok": page.ok,
        "url": url,
        "title": page.title,
        "text": page.text,
        "chars": page.chars,
        "images": list(page.images),
        "note": page.note,
    }
