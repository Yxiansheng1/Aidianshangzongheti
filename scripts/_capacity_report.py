"""把最近一次多平台横评的耗时/通过率汇总出来，回答「产出稳不稳」。"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

p = Path(r"D:\AIdianshangzongheti\output\测试\多平台-20261030-050357\summary.json")
d = json.loads(p.read_text(encoding="utf-8"))
rows = d["rows"]

total = 0.0
ok = 0
print(f"{'平台':<6}{'字数':>6}{'审核':>6}{'耗时':>8}")
for r in rows:
    if not r.get("ok"):
        print(f"{r['platform']:<6}   失败")
        continue
    total += r["seconds"]
    passed = (r.get("review") or {}).get("passed")
    ok += 1 if passed else 0
    print(f"{r['platform']:<6}{r['body_len']:>6}{(r.get('review') or {}).get('score', '?'):>6}{r['seconds']:>7}s")

n = len(rows)
print(f"\n合计 {total:.0f}s｜平均 {total / n:.0f}s/篇｜审核通过 {ok}/{n}")
