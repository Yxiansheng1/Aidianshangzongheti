"""端到端检查：已登录的号，_wait_login 应该立刻放行，并把页面停回编辑器。

不扫码、不开窗口（headless），只验证「核对后回跳」这一步没把填稿流程搞坏。
"""
import sys

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

import pipeline.content.headline as h

h.ACCOUNT = "main"
h.headless = True  # 不影响 _open，仅示意

from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = h._launch(p, headless=True)
    ctx = browser.new_context(
        storage_state=str(h.state_file("main")),
        viewport={"width": 1440, "height": 900},
        locale="zh-CN",
    )
    page = ctx.new_page()
    h._wait_login(page, ctx, h.EDITOR_URL)
    url = page.url
    title_box = h._first_visible(page, h.TITLE_SELECTORS, timeout=8000)
    browser.close()

print("停留页面:", url[:80])
print("标题框可用:", title_box is not None)
ok = "publish" in url and title_box is not None
print("结论:", "✅ 登录态可用，填稿流程未被破坏" if ok else "❌ 登录后没回到编辑器或标题框找不到")
sys.exit(0 if ok else 1)
