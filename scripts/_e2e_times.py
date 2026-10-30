"""看几条端到端跑的真实耗时（从 result.json 的 started/finished 算）。"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

base = Path(r"D:\AIdianshangzongheti\output\内容")
rows = []
for folder in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
    f = folder / "result.json"
    if not f.is_file():
        continue
    d = json.loads(f.read_text(encoding="utf-8"))
    try:
        t0 = datetime.fromisoformat(d["started"])
        t1 = datetime.fromisoformat(d["finished"])
    except Exception:
        continue
    visual = (d.get("steps") or {}).get("visual") or {}
    review = (d.get("steps") or {}).get("review") or {}
    rows.append((
        folder.name, d.get("platform"), (d.get("draft") or {}).get("length"),
        visual.get("count"), visual.get("retried"), review.get("score"),
        round((t1 - t0).total_seconds()),
    ))

print(f"{'目录':<16}{'平台':<6}{'字数':>5}{'图':>3}{'重出':>5}{'审核':>5}{'秒':>6}")
for r in rows[:10]:
    print(f"{r[0]:<16}{str(r[1]):<6}{str(r[2]):>5}{str(r[3]):>3}{str(r[4]):>5}{str(r[5]):>5}{r[6]:>6}")
