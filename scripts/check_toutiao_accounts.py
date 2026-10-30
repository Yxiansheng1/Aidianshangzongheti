"""核对头条每个账号到底登的是谁。

只读后台首页，把「账号名 / 是否完善信息」打出来。
两个号如果显示同一个名字，说明登录态是同一份，必须重新登录。

    D:\\social-auto-upload\\.venv\\Scripts\\python.exe scripts\\check_toutiao_accounts.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from patchright.sync_api import sync_playwright

STATE_DIR = Path(r"D:\AIdianshangzongheti\output\_state")
HOME = "https://mp.toutiao.com/profile_v4/index"


def check(page, state: Path) -> dict:
    page.goto(HOME, wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(4000)
    body = ""
    try:
        body = page.inner_text("body")
    except Exception:  # noqa: BLE001
        pass

    lines = [x.strip() for x in body.splitlines() if x.strip()]
    name = ""
    for line in lines[:40]:
        if line.startswith("用户") and line[2:].isdigit():
            name = line
            break
    if not name:
        for line in lines[:40]:
            if 2 <= len(line) <= 20 and not any(k in line for k in
                    ("头条号", "消息", "主页", "创作", "管理", "数据", "工具", "设置", "收益")):
                name = line
                break

    return {
        "url": page.url,
        "logged": "auth" not in page.url and "login" not in page.url,
        "name": name,
        "need_profile": "请完善账号信息" in body,
    }


def main() -> None:
    states = sorted(STATE_DIR.glob("toutiao-*.json"))
    states = [p for p in states if "draft" not in p.name and "stats" not in p.name]
    if not states:
        raise SystemExit("没有任何头条登录态")

    out = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chromium")
        for state in states:
            account = state.stem[len("toutiao-"):]
            ctx = browser.new_context(storage_state=str(state), viewport={"width": 1400, "height": 900})
            page = ctx.new_page()
            try:
                info = check(page, state)
            except Exception as exc:  # noqa: BLE001
                info = {"error": str(exc)[:100]}
            info["account"] = account
            info["state_file"] = state.name
            out.append(info)
            print(f"\n== 账号 {account} ==")
            print("  登录:", info.get("logged"))
            print("  账号名:", info.get("name") or "（读不到）")
            print("  需要完善信息:", info.get("need_profile"))
            if info.get("error"):
                print("  错误:", info["error"])
            ctx.close()
        browser.close()

    names = [i.get("name") for i in out if i.get("name")]
    print("\n" + "=" * 50)
    if len(names) >= 2 and len(set(names)) == 1:
        print("⚠ 两个号显示的是同一个账号名 —— 登录态重复了，必须重新登录其中一个")
    elif len(set(names)) == len(names):
        print("✅ 每个号对应不同账号")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
