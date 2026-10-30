"""读头条号后台的图文数据（用已经存下的登录态）。

只读，不改任何东西。跑完自己关窗口。

    D:\\social-auto-upload\\.venv\\Scripts\\python.exe scripts\\read_toutiao_stats.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from patchright.sync_api import sync_playwright

STATE = Path(r"D:\AIdianshangzongheti\output\_state\toutiao.json")
OUT = Path(r"D:\AIdianshangzongheti\output\_state\toutiao-stats.json")

URLS = [
    ("内容管理", "https://mp.toutiao.com/profile_v4/manage/content/all/article"),
    ("数据总览", "https://mp.toutiao.com/profile_v4/data/overview"),
]


def main() -> None:
    if not STATE.is_file():
        raise SystemExit("没有登录态文件，先跑一次 headline login")

    result = {"pages": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chromium")
        ctx = browser.new_context(storage_state=str(STATE), viewport={"width": 1440, "height": 900},
                                  locale="zh-CN")
        page = ctx.new_page()

        for name, url in URLS:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:  # noqa: BLE001
                print(f"[{name}] 打开失败：{exc}")
                continue
            page.wait_for_timeout(4000)
            title = page.title()
            final_url = page.url
            body = ""
            try:
                body = page.inner_text("body")
            except Exception:  # noqa: BLE001
                pass
            logged = "login" not in final_url and "auth" not in final_url
            print(f"\n===== {name} =====")
            print("标题:", title[:40], "| URL:", final_url[:80], "| 登录:", logged)
            print("页面文字前 600 字：")
            print(body[:600])
            result["pages"].append({"name": name, "title": title, "url": final_url,
                                    "logged": logged, "text": body[:8000]})
            # 存一份登录态（万一刷新了 cookie）
            ctx.storage_state(path=str(STATE))

        browser.close()

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n明细：", OUT)


if __name__ == "__main__":
    main()
