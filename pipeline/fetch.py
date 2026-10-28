"""抓取商品页的公开信息。

**不要期待太高。** 淘宝/1688/小红书对未登录请求基本都拦，能拿到的通常只有
标题和一句描述。拿不到就让用户粘贴，别硬爬——爬虫除了法律风险，还会把
你的 IP 搞脏。

这里只做一件事：发一个普通的 GET，尽可能从 meta 标签里抠出标题/描述/价格。
失败就明确报失败，让上层提示用户手动补充。
"""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlparse

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

MAX_BYTES = 512 * 1024


class FetchError(RuntimeError):
    pass


@dataclass
class PageInfo:
    url: str
    site: str = ""
    title: str = ""
    description: str = ""
    price: str = ""
    ok: bool = False
    note: str = ""
    raw_len: int = 0
    extras: dict = field(default_factory=dict)


def _meta(html_text: str, *names: str) -> str:
    for name in names:
        pattern = (
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(name)}["\'][^>]*'
            rf'content=["\']([^"\']*)["\']'
        )
        match = re.search(pattern, html_text, re.I)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def _tag(html_text: str, tag: str) -> str:
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", html_text, re.I | re.S)
    if not match:
        return ""
    return html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()


def _guess_site(url: str) -> str:
    host = urlparse(url).netloc.lower()
    table = {
        "taobao": "淘宝",
        "tmall": "天猫",
        "1688": "1688",
        "jd.com": "京东",
        "pinduoduo": "拼多多",
        "yangkeduo": "拼多多",
        "xiaohongshu": "小红书",
        "douyin": "抖音",
        "kuaishou": "快手",
    }
    for key, name in table.items():
        if key in host:
            return name
    return host


def fetch(url: str, timeout: int = 15) -> PageInfo:
    if not url.lower().startswith(("http://", "https://")):
        raise FetchError("链接必须以 http:// 或 https:// 开头")

    info = PageInfo(url=url, site=_guess_site(url))

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_BYTES)
    except urllib.error.HTTPError as exc:
        info.note = f"页面返回 HTTP {exc.code}，多半要登录。请手动粘贴商品信息。"
        return info
    except urllib.error.URLError as exc:
        info.note = f"连不上（{exc.reason}）。请手动粘贴商品信息。"
        return info
    except TimeoutError:
        info.note = "请求超时。请手动粘贴商品信息。"
        return info

    info.raw_len = len(raw)
    for encoding in ("utf-8", "gbk", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", "replace")

    info.title = _meta(text, "og:title", "title") or _tag(text, "title")
    info.description = _meta(text, "og:description", "description")

    price_match = re.search(r'"price"\s*:\s*"?([\d.]+)', text)
    if price_match:
        info.price = price_match.group(1)

    info.ok = bool(info.title or info.description)
    if not info.ok:
        info.note = "页面抓到了但没解析出商品信息（内容由 JS 动态渲染）。请手动粘贴。"

    return info
