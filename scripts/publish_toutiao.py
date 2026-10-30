"""把一篇稿子填进头条编辑器，并且（可选）替你点发布。

头条没有发布接口，这套是模拟人的操作：
    fill → 填标题正文配图 → 点「预览并发布」→（--confirm）点确认发布 → 抽查是否发出去

用法：
    # 只填 + 打开预览页，不动发布
    D:\\social-auto-upload\\.venv\\Scripts\\python.exe scripts\\publish_toutiao.py --draft <draft.json>
    # 填 + 预览 + 点确认发布
    ... --draft <draft.json> --confirm
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

import pipeline.content.headline as h

CONFIRM_LABELS = ("确认发布", "确定发布", "发布", "确认", "发布文章")
SKIP_LABELS = ("取消", "预览", "存草稿", "保存草稿")


def log(msg: str) -> None:
    print(msg, flush=True)


def visible_buttons(page) -> list[dict]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('button, [class*=btn], [role=button]'))
            .filter(b => b.offsetParent !== null)
            .map(b => ({t: (b.innerText || '').trim().slice(0, 12),
                        disabled: !!b.disabled,
                        cls: (b.className || '').toString().slice(0, 46)}))
            .filter(b => b.t)"""
    )


def click_by_text(page, labels: tuple[str, ...]) -> str:
    """按可见按钮文字点，返回点到的文字。"""
    return page.evaluate(
        """(labels) => {
            const btns = Array.from(document.querySelectorAll('button, [class*=btn], [role=button]'))
                .filter(b => b.offsetParent !== null && !b.disabled);
            for (const want of labels) {
                const hit = btns.find(b => (b.innerText || '').trim() === want);
                if (hit) { hit.click(); return (hit.innerText || '').trim(); }
            }
            return '';
        }""",
        list(labels),
    )


def insert_images(page, images: list[str]) -> int:
    """把图插进正文：点工具栏图片按钮 → 面板里的本地上传。"""
    if not images:
        return 0
    try:
        page.click(".syl-toolbar-tool.image", timeout=8000)
    except Exception as exc:  # noqa: BLE001
        log(f"[配图] 图片按钮点不开：{str(exc)[:60]}")
        return 0
    page.wait_for_timeout(2500)

    inputs = page.locator('input[type="file"][accept*="image"]')
    done = 0
    for idx, path in enumerate(images):
        if not Path(path).is_file():
            continue
        try:
            target = inputs.nth(min(idx, max(inputs.count() - 1, 0)))
            target.set_input_files(path)
            done += 1
            page.wait_for_timeout(6000)
        except Exception as exc:  # noqa: BLE001
            log(f"[配图] {Path(path).name} 塞不进去：{str(exc)[:60]}")

    hit = click_by_text(page, ("确定", "插入", "完成"))
    if hit:
        log(f"[配图] 面板按钮：{hit}")
        page.wait_for_timeout(3000)
    else:
        page.keyboard.press("Escape")
        page.wait_for_timeout(1500)
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--account", default="main")
    ap.add_argument("--confirm", action="store_true", help="真的点发布")
    ap.add_argument("--wait", type=int, default=25, help="预览页出现后等多少秒")
    args = ap.parse_args()

    data = json.loads(Path(args.draft).read_text(encoding="utf-8"))
    title = str(data.get("title") or "").strip()
    body = str(data.get("body") or "").strip()
    images = [str(i) for i in (data.get("images") or []) if Path(str(i)).is_file()]
    if not title or not body:
        raise SystemExit("草稿缺标题或正文")

    h.ACCOUNT = args.account
    out_dir = Path(args.draft).parent

    with sync_playwright_ctx() as p:
        browser, context, page = h._open(p, state_file=h.state_file(args.account))
        h._wait_login(page, context, h.EDITOR_URL)

        log(f"[填稿] 标题：{title}")
        if not h._fill_title(page, title):
            log("[警告] 标题没填上")
        log(f"[填稿] 正文：{len(body)} 字")
        if not h._fill_body(page, body):
            log("[警告] 正文没填上")
        if images:
            editor = h._first_visible(page, h.BODY_SELECTORS, timeout=5000)
            if editor:
                editor.click()
                page.keyboard.press("Control+Home")
                page.wait_for_timeout(400)
            done = insert_images(page, images)
            log(f"[填稿] 图片：{done} 张已插入")
        page.wait_for_timeout(2500)
        page.screenshot(path=str(out_dir / "pub-1-filled.png"))

        clicked = click_by_text(page, ("预览并发布", "发布"))
        log(f"[点击] {clicked or '没找到预览/发布按钮'}")
        page.wait_for_timeout(args.wait * 1000)
        page.screenshot(path=str(out_dir / "pub-2-preview.png"))

        state = page.evaluate(
            """() => {
                const body = document.body.innerText || '';
                return {
                    url: location.href,
                    text: body.replace(/\\s+/g, ' ').slice(0, 400),
                    drawers: Array.from(document.querySelectorAll('[class*=drawer], [class*=Drawer], [class*=dialog], [class*=modal]'))
                        .filter(d => d.offsetParent !== null)
                        .map(d => (d.innerText || '').replace(/\\s+/g, ' ').slice(0, 200)),
                };
            }"""
        )
        log(f"[页面] {state['url'][:90]}")
        log(f"[按钮] {[b['t'] for b in visible_buttons(page)][:16]}")
        for d in state["drawers"][:3]:
            log(f"[浮层] {d}")
        log(f"[文字] {state['text'][:220]}")

        if not args.confirm:
            log("")
            log("没加 --confirm，停在预览这一步，窗口会留着给你自己看。")
            log("看完关窗口就行；要发，重跑一次加 --confirm。")
            page.wait_for_timeout(45000)
            browser.close()
            return

        hit = click_by_text(page, CONFIRM_LABELS)
        log(f"[点击] 确认发布 → {hit or '没找到确认按钮'}")
        page.wait_for_timeout(6000)
        page.screenshot(path=str(out_dir / "pub-3-confirmed.png"))
        after = page.evaluate(
            """() => ({url: location.href, text: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 300)})"""
        )
        log(f"[结果] {after['url'][:90]}")
        log(f"[结果] {after['text'][:200]}")
        browser.close()


def sync_playwright_ctx():
    return h._require_patchright()()


if __name__ == "__main__":
    main()
