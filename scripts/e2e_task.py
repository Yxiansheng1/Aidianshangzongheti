"""端到端：起真 API → 交任务 → 轮询 → 看结果（只跑只读任务，不碰发布）。

    .venv\\Scripts\\python.exe scripts\\e2e_task.py
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.load(r)


def main() -> None:
    import uvicorn

    from pipeline.api.app import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()

    for _ in range(50):
        try:
            if get("/api/health")["ok"]:
                break
        except Exception:  # noqa: BLE001
            time.sleep(0.2)
    print("health:", get("/api/health"))

    task = "请调用 fetch_source 抓这个链接的正文：https://www.defensenews.com/ 然后告诉我抓到了多少字。不要做别的。"
    started = post("/api/tasks", {"task": task})
    print("任务已交：", started["id"], started["status"])

    deadline = time.time() + 180
    last = None
    while time.time() < deadline:
        state = get(f"/api/tasks/{started['id']}")
        if state["status"] != last:
            print(f"  [{state['status']}] pending={len(state['pending'])}")
            last = state["status"]
        if state["status"] in {"done", "failed", "waiting_approval"}:
            break
        time.sleep(2)

    print("\n最终状态：", state["status"])
    if state["status"] == "waiting_approval":
        for p in state["pending"]:
            print(f"  待批：{p['tool']}({p['args']})")
        print("  （只读任务不该停在这里；如果停在这里，说明模型想调别的工具）")
    if state["result"]:
        print("结果：", state["result"][:400])
    if state["error"]:
        print("错误：", state["error"][:400])

    server.should_exit = True


if __name__ == "__main__":
    main()
