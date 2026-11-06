"""对一篇已生成的稿子跑审核，把每条 issues 打出来（排查审核是否过严）。"""
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.config import load_config
from pipeline.review import review

path = Path(sys.argv[1])
platform = sys.argv[2]
raw = path.read_text(encoding="utf-8")
lines = raw.splitlines()
title = lines[0].lstrip("# ").strip()
body = "\n".join(lines[3:]).split("## 没依据的地方")[0].strip()

src = None
from pipeline.config import ROOT
cache = ROOT / "output" / "测试" / "_source.json"
if cache.is_file():
    import json
    src = json.loads(cache.read_text(encoding="utf-8"))["text"]

cfg = load_config()
checked = review(f"{title}\n\n{body}", platform, cfg, source_text=src)
print(f"{platform}: passed={checked.passed} score={checked.score} issues={len(checked.issues)}")
for i in checked.issues:
    print(f"  [{i.kind}] {i.text[:60]}  →  {i.advice[:70]}")
