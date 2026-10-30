"""验两个新源：维基「历史上的今天」+ 中国政府网政策频道。"""
import json
import sys
import time

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.article import _get, fetch
from pipeline.config import load_config

cfg = load_config()
proxy = cfg.trends.proxy or None

# ① 维基「历史上的今天」
api = "https://zh.wikipedia.org/api/rest_v1/feed/onthisday/events/10/30"
t0 = time.time()
try:
    raw = _get(api, proxy, timeout=25).decode("utf-8", "replace")
    data = json.loads(raw)
    events = data.get("events") or []
    print(f"[维基历史上的今天] OK  {len(events)} 条  {time.time() - t0:.1f}s")
    for ev in events[:6]:
        pages = ev.get("pages") or []
        title = pages[0]["titles"]["normalized"] if pages else ""
        text = (ev.get("text") or "")[:60].replace("\n", " ")
        print(f"   {ev.get('year')} | {text} | 词条:{title}")
except Exception as exc:  # noqa: BLE001
    print("[维基历史上的今天] FAIL", str(exc)[:80])

# ② 维基词条能不能抓正文
t0 = time.time()
page = fetch("https://zh.wikipedia.org/wiki/中国工农红军", proxy=proxy)
print(f"\n[维基词条] {page.chars} 字  {time.time() - t0:.1f}s  标题:{page.title[:30]}")
print("   配图数:", len(page.images))

# ③ 中国政府网政策频道：能不能抓到「政策文章」
t0 = time.time()
page = fetch("https://www.gov.cn/zhengce/zuixin/", proxy=proxy)
print(f"\n[政府网 最新政策] {page.chars} 字  {time.time() - t0:.1f}s")
print("   开头:", (page.text or "")[:100].replace("\n", " "))
