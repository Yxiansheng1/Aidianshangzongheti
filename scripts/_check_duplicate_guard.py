"""验证防重复：拿主号的登录态去冒充「号2」，必须被拒绝且不落盘。"""
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

import pipeline.content.headline as h

STATE = Path(r"D:\AIdianshangzongheti\output\_state")

h.ACCOUNT = "second"
target = STATE / "toutiao-second.json"
before = target.exists()

from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = h._launch(p, headless=True)
    ctx = browser.new_context(
        storage_state=str(STATE / "toutiao-main.json"), locale="zh-CN"
    )
    page = ctx.new_page()
    try:
        ok = h._commit_login(page, ctx)
        print("结果:", "没拦住（返回", ok, "）")
        blocked = False
    except SystemExit:
        print("结果: 已拦截")
        blocked = True
    browser.close()

after = target.exists()
print("second 登录态文件:", "被创建了 ❌" if after and not before else "没被创建 ✅")
print("结论:", "✅ 防重复生效" if blocked and not (after and not before) else "❌ 防重复没生效")
sys.exit(0 if blocked else 1)
