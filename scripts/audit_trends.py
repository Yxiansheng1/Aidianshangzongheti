"""审计「抓热点」到底能不能持续供稿。

三件事一起量：
1. 每条热点能不能抓到正文（这是发文章的前提）
2. 抓到的正文多长（太短就等于没有）
3. 标题是中文还是英文（三个平台都发中文）
"""
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"D:\AIdianshangzongheti")

from pipeline.article import fetch
from pipeline.config import load_config

cache = Path(r"C:\Users\morel\AppData\Local\Temp\tr.json")
items = json.loads(cache.read_text(encoding="utf-8"))["items"]
cfg = load_config()


def real_link(i):
    u = i.get("url") or ""
    return u.startswith("http") and "baidu.com/s?" not in u and "s.weibo.com" not in u


def zh_ratio(text):
    if not text:
        return 0.0
    zh = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return zh / max(1, len(text))


cands = [i for i in items if real_link(i)]

# 每个来源最多抽 1 条，保证覆盖不同源
picked, seen_src = [], set()
for item in cands:
    key = item.get("source") or "?"
    if key in seen_src:
        continue
    seen_src.add(key)
    picked.append(item)
picked = picked[:16]

print(f"待测 {len(picked)} 条（覆盖 {len(seen_src)} 个源）\n")
print(f"{'来源':<14}{'抓取':<6}{'字数':>6}{'中文占比':>8}{'秒':>6}  标题")

ok = short = 0
rows = []
for item in picked:
    t0 = time.time()
    page = fetch(item["url"], proxy=cfg.trends.proxy or None)
    dt = round(time.time() - t0, 1)
    chars = page.chars if page.ok else 0
    ratio = zh_ratio(item["title"])
    if page.ok and chars >= 800:
        ok += 1
    elif page.ok:
        short += 1
    status = "OK" if (page.ok and chars >= 800) else ("太短" if page.ok else "失败")
    print(f"{str(item.get('source'))[:12]:<14}{status:<6}{chars:>6}{ratio * 100:>7.0f}%{dt:>6}  {item['title'][:34]}")
    rows.append({"source": str(item.get("source")), "status": status, "chars": chars,
                 "zh": round(ratio, 2), "seconds": dt, "title": item["title"],
                 "url": item["url"]})

print(f"\n可写（≥800 字）：{ok}/{len(picked)}　太短：{short}　失败：{len(picked) - ok - short}")

# 中英文分布：全量标题
zh_titles = sum(1 for i in items if zh_ratio(i["title"]) > 0.3)
print(f"全部 {len(items)} 条里，中文标题 {zh_titles} 条（{zh_titles / len(items) * 100:.0f}%），"
      f"其余是英文")

out = Path(r"D:\AIdianshangzongheti\output\测试\热点审计")
out.mkdir(parents=True, exist_ok=True)
(out / "audit.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print("明细：", out / "audit.json")
