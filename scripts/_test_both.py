"""调一次「一稿两版」：会开两个浏览器窗口（账号1 / 账号2）。"""
import json
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

dirs = sorted([p for p in Path(r"D:\AIdianshangzongheti\output\内容").iterdir()
               if p.is_dir() and (p / "文案.md").is_file()],
              key=lambda p: p.stat().st_mtime, reverse=True)
raw = (dirs[0] / "文案.md").read_text(encoding="utf-8")
lines = raw.splitlines()
title = lines[0].lstrip("# ").strip()
body = "\n".join(lines[3:]).split("## 没依据的地方")[0].strip()

payload = {
    "action": "both",
    "platform": "头条",
    "title": title,
    "body": body,
    "images": [],
    "url": "",
}
req = urllib.request.Request("http://127.0.0.1:8899/api/content/headline",
                             data=json.dumps(payload).encode(), method="POST",
                             headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=300) as r:
    print(r.status, r.read().decode())

print("第一版标题:", title)
print("正文:", len(body), "字")
