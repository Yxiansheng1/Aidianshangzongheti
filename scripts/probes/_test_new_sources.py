"""验两个新源：政策 + 历史。"""
import sys

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline import trends
from pipeline.config import load_config

cfg = load_config()
res = trends.collect(categories=["政策", "历史"], proxy=cfg.trends.proxy or None)

print("总数:", len(res.items))
print("错误:", res.errors or "无")
for cat in ("政策", "历史"):
    rows = [i for i in res.items if i.category == cat]
    print(f"\n== {cat}（{len(rows)} 条）")
    for item in rows[:8]:
        has = "有链接" if item.url else "无链接"
        print(f"  [{has}] {item.title[:36]}")
        if item.url:
            print(f"          {item.url[:90]}")
