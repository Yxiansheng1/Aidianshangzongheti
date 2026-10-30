"""逐份登录态直接看：首页地址、页面上显示的名字、user_info 接口原始返回。"""
import json
import sys

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from patchright.sync_api import sync_playwright

STATE = r"D:\AIdianshangzongheti\output\_state"
CASES = [
    ("main", rf"{STATE}\toutiao-main.json"),
    ("second（刚扫的）", rf"{STATE}\toutiao-second.same-as-main.json.bak"),
]
HOME = "https://mp.toutiao.com/profile_v4/index"
API = "https://mp.toutiao.com/mp/agw/creator_center/user_info"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chromium")
    for label, path in CASES:
        ctx = browser.new_context(storage_state=path, viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.goto(HOME, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(4000)
        print(f"\n===== {label} =====")
        print("URL:", page.url[:100])
        try:
            name = page.locator("[class*=name]").first.inner_text(timeout=3000).strip()
            print("页面名字:", repr(name[:30]))
        except Exception as exc:  # noqa: BLE001
            print("页面名字: 读不到", str(exc)[:50])
        try:
            body = page.inner_text("body")
            print("含「请完善账号信息」:", "请完善账号信息" in body)
        except Exception:  # noqa: BLE001
            pass
        r = page.request.get(API, timeout=20000)
        data = r.json() if r.ok else {}
        print("接口 status:", r.status)
        for k in ("user_id", "user_id_str", "name", "media_id", "screen_name"):
            if k in data:
                print(f"  {k} = {data[k]!r}")
        ctx.close()
    browser.close()
