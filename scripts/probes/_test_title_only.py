"""验「只有主题、没有链接和正文」也能出稿（热点→写 的兜底路径）。"""
import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8899"


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as r:
        return json.loads(r.read().decode())


resp = post("/api/content/run", {
    "title": "二十届五中全会公报", "platform": "小红书", "images": 0, "draw": False,
})
if resp.get("error"):
    raise SystemExit("提交失败：" + resp["error"])

job = resp["job"]["id"]
print("job:", job)
for _ in range(60):
    time.sleep(3)
    info = get("/api/job?id=" + job)
    if info.get("status") in ("done", "error"):
        break
    print("  ", info.get("status"), info.get("message", ""), info.get("elapsed"))

if info.get("status") == "error":
    print("失败：", info.get("error"))
else:
    d = info.get("result") or {}
    draft = d.get("draft") or {}
    print("字数:", draft.get("length"), "| 标题:", draft.get("title"))
    print("审核:", d.get("review", {}).get("passed"), d.get("review", {}).get("score"))
    print("gaps:", len(draft.get("gaps") or []), "条")
    print("开头:", (draft.get("body") or "")[:80].replace("\n", " "))
