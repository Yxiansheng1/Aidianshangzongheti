"""看两个头条号的发布权限：后台提示 + 编辑器里的发布按钮是否可用。

只读：进入编辑器，检查「发布」按钮存在与否、是否 disabled，不做任何提交。
"""
import sys

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from patchright.sync_api import sync_playwright

HOME = "https://mp.toutiao.com/profile_v4/index"
EDITOR = "https://mp.toutiao.com/profile_v4/graphic/publish"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chromium")
    for account in ("main", "second"):
        state = rf"D:\AIdianshangzongheti\output\_state\toutiao-{account}.json"
        ctx = browser.new_context(storage_state=state, viewport={"width": 1500, "height": 950})
        page = ctx.new_page()
        page.goto(HOME, wait_until="domcontentloaded")
        page.wait_for_timeout(4500)
        banner = page.evaluate(
            """() => {
                const t = document.body.innerText || '';
                const i = t.indexOf('请完善账号信息');
                return i >= 0 ? t.slice(i, i + 60).replace(/\\s+/g, ' ') : '';
            }"""
        )
        name = page.evaluate(
            """() => {
                const t = (document.body.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
                const i = t.findIndex(x => /^用户\\d+$/.test(x) || x.length <= 12 && x.includes('报'));
                return i >= 0 ? t[i] : '';
            }"""
        )
        page.goto(EDITOR, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        info = page.evaluate(
            """() => {
                const btns = Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent)
                    .map(b => ({t: (b.innerText || '').trim(), disabled: b.disabled}))
                    .filter(b => b.t && b.t.length <= 6);
                const body = document.body.innerText || '';
                return {
                    url: location.href,
                    publish: btns.filter(b => ['发布', '预览并发布', '定时发布'].includes(b.t)),
                    needProfile: body.includes('请完善账号信息'),
                    loginWall: body.includes('扫码登录') || body.includes('登录后即可'),
                    titleBox: !!document.querySelector('[contenteditable=true], textarea'),
                };
            }"""
        )
        print(f"\n===== 账号 {account} =====")
        print("  后台提示:", banner or "（没有「请完善账号信息」了）")
        print("  发布按钮:", info["publish"] or "（没找到）")
        print("  编辑器需要完善信息:", info["needProfile"])
        print("  登录墙:", info["loginWall"])
        print("  编辑器已加载:", info["titleBox"])
        print("  当前地址:", info["url"][:80])
        ctx.close()
    browser.close()
