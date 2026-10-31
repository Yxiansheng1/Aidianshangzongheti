"""查某个头条账号的文章列表（只读）。"""
import sys

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from patchright.sync_api import sync_playwright

URL = "https://mp.toutiao.com/profile_v4/graphic/articles"

account = sys.argv[1] if len(sys.argv) > 1 else "second"
STATE = rf"D:\AIdianshangzongheti\output\_state\toutiao-{account}.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chromium")
    ctx = browser.new_context(storage_state=STATE, viewport={"width": 1500, "height": 1000})
    page = ctx.new_page()
    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(7000)
    txt = page.evaluate("() => (document.body.innerText || '').replace(/\\s+/g, ' ')")
    i = txt.find("全部")
    print(f"[{account}]", txt[i: i + 500])
    links = page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href]'))
            .map(a => a.getAttribute('href'))
            .filter(h => h && (h.includes('/article/') || h.includes('toutiao.com/item')))"""
    )
    print("文章链接:", list(dict.fromkeys(links))[:5])
    page.screenshot(path=rf"D:\AIdianshangzongheti\output\_state\list-{account}.png")
    browser.close()
