"""验界面接口会返回「原文配图」字段。"""
import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8899"


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return json.loads(r.read().decode())


resp = post("/api/content/run", {
    "url": "https://mistral.ai/news/mistral-large-4-oss/",
    "platform": "头条", "mode": "国际军事", "images": 0, "draw": False,
})
if resp.get("error"):
    raise SystemExit("提交失败：" + resp["error"])

job = resp["job"]["id"]
info = {}
for _ in range(50):
    time.sleep(3)
    info = get("/api/job?id=" + job)
    if info.get("status") in ("done", "error"):
        break

if info.get("status") == "error":
    print("失败:", info.get("error"))
else:
    d = info.get("result") or {}
    print("标题:", (d.get("draft") or {}).get("title"))
    print("正文字数:", (d.get("draft") or {}).get("length"))
    print("原文配图数:", len(d.get("source_images") or []))
    for img in (d.get("source_images") or []):
        print("  ", img["path"].split("\\")[-1], "->", img["url"][:60])
    print("画面描述:", d.get("source_image_note") or "（无）")
    print("审核:", (d.get("review") or {}).get("score"))
