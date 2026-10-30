"""验人设接口：列候选 → 套用 → 生成一篇看口吻。"""
import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8899"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return json.loads(r.read().decode())


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


data = get("/api/content/personas")
print("候选:", [(p["key"], len(p["avatars"]), "张头像") for p in data["personas"]])
print("当前:", data["current"] or "（无）")

print("\n套用 A-老周在现场 ...")
print(post("/api/content/persona", {"key": "A-老周在现场"}))

meta = get("/api/content/meta")
print("meta.persona =", meta.get("persona"))

# 生成一篇，看口吻是否跟着人设走
resp = post("/api/content/run", {
    "title": "Intel 一夜跌掉两成，财报里到底哪里出了问题",
    "platform": "头条", "images": 0, "draw": False,
})
if resp.get("error"):
    raise SystemExit("提交失败：" + resp["error"])

job = resp["job"]["id"]
info = {}
for _ in range(40):
    time.sleep(3)
    info = get("/api/job?id=" + job)
    if info.get("status") in ("done", "error"):
        break

if info.get("status") == "error":
    print("失败:", info.get("error"))
else:
    draft = (info.get("result") or {}).get("draft") or {}
    print(f"\n字数 {draft.get('length')}｜标题 {draft.get('title')}")
    print("正文前 260 字：")
    print((draft.get("body") or "")[:260])
