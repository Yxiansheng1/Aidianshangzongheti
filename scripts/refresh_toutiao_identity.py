"""把每个已登录头条账号的身份（user_id + 昵称）刷新进身份表。

改过昵称、或手动放了新的登录态文件之后跑一次，让防重复检测认得准。
界面上「登录这个号」成功后会自动记，不用手动跑。

    D:\\social-auto-upload\\.venv\\Scripts\\python.exe scripts\\refresh_toutiao_identity.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from patchright.sync_api import sync_playwright

import pipeline.content.headline as h
from pipeline.content.accounts import is_account_state

STATE_DIR = Path(r"D:\AIdianshangzongheti\output\_state")


def main() -> None:
    states = sorted(STATE_DIR.glob("toutiao-*.json"))
    states = [p for p in states if is_account_state(p)]
    if not states:
        raise SystemExit("没有任何头条登录态")

    found: dict[str, dict[str, str]] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chromium")
        for state in states:
            account = state.stem[len("toutiao-"):]
            ctx = browser.new_context(storage_state=str(state))
            page = ctx.new_page()
            try:
                page.goto(h.HOME_URL, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(3000)
                if "auth" in page.url or "login" in page.url:
                    print(f"跳过 {account}：未登录")
                    continue
                ident = h.identity_of(page)
            except Exception as exc:  # noqa: BLE001
                print(f"跳过 {account}：{str(exc)[:60]}")
                ctx.close()
                continue
            ctx.close()
            if not ident.get("user_id"):
                print(f"跳过 {account}：读不到 user_id")
                continue
            found[account] = ident
            print(f"{account}: {ident.get('name') or '?'}（ID {ident['user_id']}）")
        browser.close()

    if not found:
        raise SystemExit("没有可记录的身份")
    h.IDENTITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    h.IDENTITY_FILE.write_text(
        json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("已写入", h.IDENTITY_FILE)

    uids = [v["user_id"] for v in found.values()]
    if len(uids) != len(set(uids)):
        print("⚠ 有多个账号是同一个头条号，见上")


if __name__ == "__main__":
    main()
