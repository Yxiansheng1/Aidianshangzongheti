"""调一次头条半自动填稿（会弹浏览器，需要人扫码/点发布）。"""
import json
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

src = Path(r"D:\AIdianshangzongheti\output\测试\多平台-20261030-050357\头条.md")
raw = src.read_text(encoding="utf-8")
lines = raw.splitlines()
title = lines[0].lstrip("# ").strip()
body = "\n".join(lines[3:]).split("## 没依据的地方")[0].strip()

payload = {"action": "fill", "title": title, "body": body, "images": [], "url": ""}
req = urllib.request.Request(
    "http://127.0.0.1:8899/api/content/headline",
    data=json.dumps(payload).encode(), method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=60) as r:
    print(r.status, r.read().decode())
print("标题:", title)
print("正文字数:", len(body))
