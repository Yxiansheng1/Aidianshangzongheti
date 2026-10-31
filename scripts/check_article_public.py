"""匿名打开一篇头条文章，确认外人能看见（标题/配图/正文）。只读。

    ... python scripts/check_article_public.py https://www.toutiao.com/article/xxxx/
"""
import sys

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from patchright.sync_api import sync_playwright

url = sys.argv[1]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chromium")
    ctx = browser.new_context(viewport={"width": 1200, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(5000)
    info = page.evaluate(
        """() => ({
            title: document.title,
            h1: (document.querySelector('h1') && document.querySelector('h1').innerText || '').slice(0, 60),
            imgs: document.querySelectorAll('article img, .article-content img').length,
            topics: Array.from(document.querySelectorAll('.tteditor-forum, a[href*=forum], a[href*=topic]'))
                .map(a => (a.innerText || a.getAttribute('data-name') || '').trim()).filter(Boolean).slice(0, 8),
            hashtags: Array.from(document.body.innerText.matchAll(/#[^#\\s]{2,20}#/g)).map(m => m[0]).slice(0, 8),
            text: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 220),
        })"""
    )
    print("标题:", info["title"][:90])
    print("h1:", info["h1"])
    print("正文图:", info["imgs"])
    print("话题:", info["topics"] or info["hashtags"] or "（页面上没看到话题）")
    print("开头:", info["text"][:180])
    browser.close()
