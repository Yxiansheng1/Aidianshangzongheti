"""给已经发布（或刚填好）的头条文章补真话题（#话题# 那种带 ID 的节点）。

头条的话题不是正文里打 # 就算：必须用编辑器的 @ 式候选列表里点选，
点进去才会变成 <a class="tteditor-forum" data-id="...">。

用法：
    # 只插入并回读，不发布
    D:\\social-auto-upload\\.venv\\Scripts\\python.exe scripts\\add_toutiao_topics.py --account second --pgc-id 7702514908738372122 --topics 成昆铁路,三线建设,铁路史
    # 插入并发布（覆盖原文）
    ... 同上 --confirm
"""
from __future__ import annotations

import argparse
import re
import sys

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from patchright.sync_api import sync_playwright

import pipeline.content.headline as h


def log(msg: str) -> None:
    print(msg, flush=True)


def existing_topics(page) -> list[str]:
    """编辑器里的话题名。#话题# 会有 templ + mask 两份，去重保留顺序。"""
    raw = page.evaluate(
        """() => Array.from(document.querySelectorAll('.tteditor-forum'))
            .map(a => a.getAttribute('data-name')).filter(Boolean)"""
    )
    seen: list[str] = []
    for name in raw:
        if name not in seen:
            seen.append(name)
    return seen


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--pgc-id", required=True, help="文章ID，列表里链接末尾那串数字")
    ap.add_argument("--topics", required=True, help="逗号分隔，最多 5 个")
    ap.add_argument("--confirm", action="store_true", help="插入后点发布（会覆盖已发文章）")
    args = ap.parse_args()

    topics = [t.strip().lstrip("#").rstrip("#") for t in args.topics.split(",") if t.strip()][:5]
    if not topics:
        raise SystemExit("没有给话题")

    h.ACCOUNT = args.account
    url = f"https://mp.toutiao.com/profile_v4/graphic/publish?from=edit&pgc_id={args.pgc_id}"

    with sync_playwright() as p:
        browser, ctx, page = h._open(p, state_file=h.state_file(args.account))
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)

        before = existing_topics(page)
        log(f"文章 ID {args.pgc_id}　原有话题：{before or '无'}")

        editor = h._first_visible(page, h.BODY_SELECTORS, timeout=15000)
        if not editor:
            raise SystemExit("找不到正文编辑器，可能页面没加载完")
        editor.click()
        page.keyboard.press("Control+End")
        page.keyboard.press("Enter")
        page.wait_for_timeout(500)

        todo = [t for t in topics if t not in before]
        already = [t for t in topics if t in before]
        added, skipped = h.insert_topics(page, todo) if todo else ([], [])
        if already:
            log(f"  已有话题，跳过：{already}")

        page.wait_for_timeout(1500)
        after = existing_topics(page)
        log(f"插入后编辑器里的话题：{after}")

        if not args.confirm:
            log("没加 --confirm，没发布。窗口留 20 秒供你确认。")
            page.screenshot(path=str(h.STATE_DIR / f"topics-{args.pgc_id}.png"))
            page.wait_for_timeout(20000)
            browser.close()
            return

        if not after:
            raise SystemExit("一个话题都没插进去，不发布")

        hit = page.evaluate(
            """() => {
                const btns = Array.from(document.querySelectorAll('button'))
                    .filter(b => b.offsetParent !== null && !b.disabled);
                const b = btns.find(x => ['发布', '预览并发布'].includes((x.innerText || '').trim()));
                if (!b) return '';
                b.click();
                return (b.innerText || '').trim();
            }"""
        )
        log(f"[发布] 点了「{hit or '没找到按钮'}」")
        page.wait_for_timeout(6000)

        # 可能弹确认
        hit2 = page.evaluate(
            """() => {
                const btns = Array.from(document.querySelectorAll('button'))
                    .filter(b => b.offsetParent !== null && !b.disabled);
                const b = btns.find(x => ['确认发布', '确定', '确定发布'].includes((x.innerText || '').trim()));
                if (!b) return '';
                b.click();
                return (b.innerText || '').trim();
            }"""
        )
        if hit2:
            log(f"[发布] 确认：{hit2}")
        page.wait_for_timeout(6000)
        page.screenshot(path=str(h.STATE_DIR / f"topics-{args.pgc_id}-done.png"))
        log(f"[结果] {page.url[:100]}")
        browser.close()


if __name__ == "__main__":
    main()
