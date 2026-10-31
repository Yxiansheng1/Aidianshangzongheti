"""只读：打开某篇文章的编辑页，看它现在挂着哪些话题。"""
import sys

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from patchright.sync_api import sync_playwright

import pipeline.content.headline as h

account, pgc = sys.argv[1], sys.argv[2]
h.ACCOUNT = account
URL = f"https://mp.toutiao.com/profile_v4/graphic/publish?from=edit&pgc_id={pgc}"

with sync_playwright() as p:
    browser, ctx, page = h._open(p, state_file=h.state_file(account))
    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_timeout(9000)
    names = page.evaluate(
        """() => Array.from(document.querySelectorAll('.tteditor-forum')).map(a => a.getAttribute('data-name'))"""
    )
    seen = []
    for n in names:
        if n and n not in seen:
            seen.append(n)
    print(f"[{account}] 文章 {pgc} 现有话题：{seen or '无'}")
    print("正文尾:", page.evaluate(
        """() => { const e = document.querySelector('[contenteditable=true]');
                   return e ? (e.innerText || '').replace(/\\s+/g, ' ').slice(-90) : ''; }"""))
    browser.close()
