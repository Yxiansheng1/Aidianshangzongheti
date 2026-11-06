"""试产一篇政策解读：先抓一篇真政策原文，再过完整流水线（含口径审查）。"""
import re
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.article import _get, fetch
from pipeline.config import load_config, ROOT
from pipeline.content import pipeline as content_pipeline

cfg = load_config()

# ① 找一篇真政策原文（索引页要拿原始 HTML，提取器会把链接都过滤掉）
raw_html = _get("https://www.gov.cn/zhengce/", cfg.trends.proxy or None,
                timeout=25).decode("utf-8", "replace")
print("政策频道页原始 HTML:", len(raw_html), "字节")

links = re.findall(r'href="([^"]+\.htm)"', raw_html)
print("候选链接:", len(links))

candidates = []
for href in links[:40]:
    url = urllib.parse.urljoin("https://www.gov.cn/zhengce/", href)
    if url in candidates:
        continue
    candidates.append(url)

src = None
for url in candidates[:8]:
    page = fetch(url, proxy=cfg.trends.proxy or None)
    print(f"  {page.chars if page.ok else 'FAIL':>5}  {url[:80]}")
    if page.ok and page.chars >= 800:
        src = {"url": url, "title": page.title or "政策", "text": page.text}
        break

if not src:
    raise SystemExit("没抓到可用政策原文")

print("\n选中:", src["title"])
print("字数:", len(src["text"]))
print("开头:", src["text"][:120].replace("\n", " "))

# ② 存一份，方便复跑
cache = ROOT / "output" / "测试" / "_policy_source.json"
cache.parent.mkdir(parents=True, exist_ok=True)
import json  # noqa: E402
cache.write_text(json.dumps(src, ensure_ascii=False, indent=1), encoding="utf-8")

# ③ 跑流水线
t0 = time.time()
result = content_pipeline.run(
    "", cfg, platform="头条", mode="政策解读", images=0, draw=False,
    article={"title": src["title"], "text": src["text"]},
)
print(f"\n用时 {time.time() - t0:.0f}s  ok={result.get('ok')}")

draft = result.get("draft") or {}
print("标题:", draft.get("title"), f"（{len(draft.get('title') or '')} 字）")
print("正文:", draft.get("length"), "字")
print("开头:", (draft.get("body") or "")[:120].replace("\n", " "))

review = (result.get("steps") or {}).get("review") or {}
print(f"\n审核: passed={review.get('passed')} score={review.get('score')} issues={len(review.get('issues') or [])}")
for item in (review.get("issues") or [])[:8]:
    print(f"  [{item.get('level')}/{item.get('kind')}] {str(item.get('text'))[:40]} → {str(item.get('advice'))[:60]}")

print("\n产物:", result.get("dir"))
