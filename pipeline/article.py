"""抓一篇文章的正文。

为什么要这个：改写必须有原文。只拿标题去写，AI 只能编——这就是之前
文案空洞的根本原因。

做法：抓 HTML → 去掉脚本/导航/页眉页脚 → 取所有 <p> 里够长的段落拼起来。
不追求完美，够 AI 读就行。抓不到就退回到 meta description。
"""

from __future__ import annotations

import html as html_mod
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 这些标签里的内容一律不要
DROP_TAGS = ("script", "style", "nav", "header", "footer", "aside", "form",
             "noscript", "iframe", "svg", "figure")

MIN_PARAGRAPH = 30      # 少于这个字数不算正文段落
MAX_CHARS = 6000        # 超过就截断，别把整个页面塞给模型


class ArticleError(RuntimeError):
    pass


@dataclass
class Article:
    url: str
    title: str = ""
    text: str = ""
    chars: int = 0
    ok: bool = False
    note: str = ""


def _get(url: str, proxy: str | None, timeout: int = 25) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    handlers: list = [urllib.request.HTTPSHandler(context=ssl._create_unverified_context())]
    handlers.append(urllib.request.ProxyHandler(
        {"http": proxy, "https": proxy} if proxy else {}
    ))
    opener = urllib.request.build_opener(*handlers)
    with opener.open(request, timeout=timeout) as response:
        return response.read(2 * 1024 * 1024)


def _strip_tags(html: str) -> str:
    for tag in DROP_TAGS:
        html = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", " ", html, flags=re.S | re.I)
    return html


def _paragraphs(html: str) -> list[str]:
    out: list[str] = []
    for match in re.finditer(r"<p[^>]*>(.*?)</p>", html, re.S | re.I):
        raw = re.sub(r"<[^>]+>", "", match.group(1))
        text = html_mod.unescape(raw).strip()
        text = re.sub(r"\s+", " ", text)
        if len(text) >= MIN_PARAGRAPH:
            out.append(text)
    return out


def _meta(html: str, *names: str) -> str:
    for name in names:
        pattern = (
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(name)}["\'][^>]*'
            rf'content=["\']([^"\']*)["\']'
        )
        found = re.search(pattern, html, re.I)
        if found:
            return html_mod.unescape(found.group(1)).strip()
    return ""


def fetch(url: str, *, proxy: str | None = None, timeout: int = 25) -> Article:
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ArticleError("链接必须以 http:// 或 https:// 开头")

    article = Article(url=url)

    try:
        raw = _get(url, proxy, timeout)
    except urllib.error.HTTPError as exc:
        article.note = f"HTTP {exc.code}，可能要登录或有反爬"
        return article
    except (urllib.error.URLError, TimeoutError) as exc:
        article.note = f"连不上：{exc}"
        return article

    for encoding in ("utf-8", "gbk", "gb18030"):
        try:
            page = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        page = raw.decode("utf-8", "replace")

    title_match = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    if title_match:
        article.title = html_mod.unescape(re.sub(r"<[^>]+>", "", title_match.group(1))).strip()

    body = _strip_tags(page)
    paragraphs = _paragraphs(body)

    if paragraphs:
        text = "\n\n".join(paragraphs)
    else:
        text = _meta(page, "og:description", "description")

    article.text = text[:MAX_CHARS]
    article.chars = len(article.text)
    article.ok = article.chars >= 200

    if not article.ok and not article.note:
        article.note = "抓到了页面但没提取出正文（可能需要登录，或内容是 JS 渲染的）"

    return article


def fetch_to_file(url: str, directory: Path | str, *, proxy: str | None = None) -> Path:
    article = fetch(url, proxy=proxy)
    if not article.ok:
        raise ArticleError(article.note or "没抓到正文")

    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", article.title or "article")[:40] or "article"
    target = folder / f"{name}.txt"
    target.write_text(f"{article.title}\n{url}\n\n{article.text}", encoding="utf-8")
    return target
