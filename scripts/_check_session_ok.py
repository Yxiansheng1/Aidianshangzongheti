"""回归测试：新登录判据 _session_ok 会不会再把匿名页当成已登录。

用法（venv 里有 patchright）：
    D:\\social-auto-upload\\.venv\\Scripts\\python.exe scripts\\_check_session_ok.py
"""
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from patchright.sync_api import sync_playwright

from pipeline.content.headline import _session_ok

STATE = Path(r"D:\AIdianshangzongheti\output\_state")

CASES = [
    ("真登录态（main）", STATE / "toutiao-main.json", True),
    ("旧假登录态（second）", STATE / "toutiao-second.fake-20261030.json.bak", False),
    ("空登录态（无 cookie）", None, False),
]

ok = True
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chromium")
    for label, state, expect in CASES:
        kwargs = {"viewport": {"width": 1400, "height": 900}}
        if state is not None:
            kwargs["storage_state"] = str(state)
        ctx = browser.new_context(**kwargs)
        page = ctx.new_page()
        try:
            got = _session_ok(page)
        except Exception as exc:  # noqa: BLE001
            got = f"异常 {exc}"[:60]
        hit = (got is expect)
        ok = ok and hit
        print(f"{'✅' if hit else '❌'} {label}: 判为已登录={got}（期望 {expect}）")
        ctx.close()
    browser.close()

print("全部通过" if ok else "有不符合预期的用例")
sys.exit(0 if ok else 1)
