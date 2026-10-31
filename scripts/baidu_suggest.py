"""查百度搜索下拉词：验证某个关键词有没有真实的搜索需求。

百家号是搜索驱动，选题要靠"有人真的在搜"来定，不能拍脑袋。
    ... python scripts/baidu_suggest.py 三线建设 成昆铁路 豹2A8
"""
import json
import re
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

PROXY = "http://127.0.0.1:7897"


def suggest(word: str, limit: int = 8) -> list[str]:
    url = "https://suggestion.baidu.com/su?wd=" + urllib.parse.quote(word) + "&json=1"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Referer": "https://www.baidu.com/",
    })
    handlers: list = [urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})]
    try:
        with urllib.request.build_opener(*handlers).open(req, timeout=15) as resp:
            raw = resp.read()
    except Exception:  # noqa: BLE001
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # 不走代理再试一次
                raw = resp.read()
        except Exception as exc:  # noqa: BLE001
            return [f"（取不到：{str(exc)[:40]}）"]

    text = ""
    for enc in ("gbk", "gb18030", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    m = re.search(r'"s"\s*:\s*(\[[^\]]*\])', text)
    if not m:
        return []
    try:
        return json.loads(m.group(1))[:limit]
    except Exception:  # noqa: BLE001
        return []


for word in sys.argv[1:]:
    items = suggest(word)
    print(f"\n【{word}】")
    if not items:
        print("  （没有下拉词，说明搜的人很少）")
    for i, s in enumerate(items, 1):
        print(f"  {i}. {s}")
