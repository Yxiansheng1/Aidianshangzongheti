"""核对头条每个账号到底登的是谁。

判据用后台接口的 user_id（稳定），昵称只作展示。
两个号 user_id 相同 = 同一个头条号，必须重新登录。

    D:\\social-auto-upload\\.venv\\Scripts\\python.exe scripts\\check_toutiao_accounts.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from patchright.sync_api import sync_playwright

from pipeline.content.headline import HOME_URL, identity_of

STATE_DIR = Path(r"D:\AIdianshangzongheti\output\_state")


def check(browser, state: Path) -> dict:
    ctx = browser.new_context(
        storage_state=str(state), viewport={"width": 1400, "height": 900}
    )
    page = ctx.new_page()
    info: dict = {
        "account": state.stem[len("toutiao-"):],
        "state_file": state.name,
        "logged": False,
        "user_id": "",
        "name": "",
        "need_profile": False,
    }
    try:
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=40000)
        page.wait_for_timeout(3500)
        info["logged"] = "auth" not in page.url and "login" not in page.url
        if info["logged"]:
            ident = identity_of(page)
            info["user_id"] = ident.get("user_id", "")
            info["name"] = ident.get("name", "")
            try:
                info["need_profile"] = "请完善账号信息" in page.inner_text("body")
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)[:100]
    finally:
        ctx.close()
    return info


def main() -> None:
    states = sorted(STATE_DIR.glob("toutiao-*.json"))
    states = [p for p in states if "draft" not in p.name and "stats" not in p.name]
    if not states:
        raise SystemExit("没有任何头条登录态")

    out = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chromium")
        for state in states:
            info = check(browser, state)
            out.append(info)
            print(f"\n== 账号 {info['account']} ==")
            print("  登录:", info["logged"])
            print("  昵称:", info["name"] or "（读不到）")
            print("  账号ID:", info["user_id"] or "（读不到）")
            print("  需要完善信息:", info["need_profile"])
            if info.get("error"):
                print("  错误:", info["error"])
        browser.close()

    uids = [i["user_id"] for i in out if i.get("user_id")]
    print("\n" + "=" * 52)
    if len(uids) != len(set(uids)):
        print("⚠ 两个账号的 user_id 相同 —— 是同一个头条号，必须换号重新登录")
    elif len(out) >= 2 and all(i["logged"] for i in out):
        print("✅ 每个账号都是独立的头条号")
    else:
        print("部分账号未登录，见上")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
