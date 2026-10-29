"""从热点源里找一个能抓正文的真实文章链接，缓存成测试用原文。"""
import json
import sys

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.config import load_config, ROOT
from pipeline import trends
from pipeline.article import fetch

cfg = load_config()
data = trends.collect(categories=["AI与科技"], proxy=cfg.trends.proxy or None)
items = data.items
print("抓到热点", len(items), "条")

cache = ROOT / "output" / "测试" / "_source.json"
cache.parent.mkdir(parents=True, exist_ok=True)

tried = 0
for item in items:
    url = item.url or ""
    if not url.startswith("http"):
        continue
    tried += 1
    if tried > 8:
        break
    page = fetch(url, proxy=cfg.trends.proxy or None)
    print(f"[{tried}] {page.chars if page.ok else 'FAIL'}  {url[:90]}")
    if page.ok and page.chars > 1200:
        payload = {"url": url, "title": page.title or item.title or url,
                   "text": page.text, "chars": page.chars}
        cache.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print("已缓存 ->", cache)
        print("标题:", payload["title"])
        break
else:
    print("没找到能抓正文的链接")
