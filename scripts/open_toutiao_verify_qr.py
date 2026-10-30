"""把号2 的「完善账号信息」页面点到出二维码那一步，窗口留着给你扫。

    ... python scripts/open_toutiao_verify_qr.py            # 有窗口，留着扫
    ... python scripts/open_toutiao_verify_qr.py --headless # 只看结构，不弹窗

扫码只能在手机上做：今日头条 App → 我的 → 右上角设置 → 扫一扫。
"""
from __future__ import annotations

import argparse
import sys
import time

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from patchright.sync_api import sync_playwright

LANDING = "https://mp.toutiao.com/profile_v4/personal/landing-type"


def log(msg: str) -> None:
    print(msg, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default="second")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--minutes", type=int, default=15)
    args = ap.parse_args()

    state = rf"D:\AIdianshangzongheti\output\_state\toutiao-{args.account}.json"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, channel="chromium")
        ctx = browser.new_context(storage_state=state, viewport={"width": 1500, "height": 950})
        page = ctx.new_page()
        page.goto(LANDING, wait_until="domcontentloaded")
        page.wait_for_timeout(4500)

        # 个人账号那块的「选择」——按卡片文字定位，不按顺序猜
        clicked = page.evaluate(
            """() => {
                const cards = Array.from(document.querySelectorAll('div'))
                    .filter(d => (d.innerText || '').includes('个人账号')
                                 && (d.innerText || '').includes('大陆作者')
                                 && (d.innerText || '').length < 300);
                if (!cards.length) return 'no-card';
                const card = cards[cards.length - 1];
                const btn = Array.from(card.querySelectorAll('button, [class*=btn]'))
                    .find(b => (b.innerText || '').trim() === '选择');
                if (!btn) return 'no-btn';
                btn.click();
                return 'clicked';
            }"""
        )
        log(f"点「个人账号 · 大陆作者」的选择：{clicked}")
        page.wait_for_timeout(3500)

        text = page.evaluate("() => (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 500)")
        has_qr = page.evaluate(
            """() => !!document.querySelector('canvas, img[src*=qr], img[src*=QR], [class*=qrcode], [class*=Qrcode], [class*=qr-code]')"""
        )
        log(f"页面出现二维码元素：{has_qr}")
        log(f"页面文字：{text[:260]}")
        page.screenshot(path=rf"D:\AIdianshangzongheti\output\_state\qr-{args.account}.png")
        log("截图：output/_state/qr-%s.png" % args.account)

        if args.headless:
            browser.close()
            return

        log("")
        log("=" * 62)
        log(" 窗口已留在这一步。扫码路径：")
        log("   手机打开【今日头条 App】→ 右下角「我的」→ 右上角齿轮【设置】")
        log("   → 【扫一扫】→ 扫电脑屏幕上这个码")
        log(" 扫完电脑上会自己跳到下一步（要补身份证/人脸）。")
        log(f" 这个窗口会留 {args.minutes} 分钟，别关它。")
        log("=" * 62)

        deadline = time.time() + args.minutes * 60
        last = ""
        while time.time() < deadline:
            page.wait_for_timeout(4000)
            try:
                cur = page.evaluate(
                    "() => (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 120)"
                )
            except Exception:  # noqa: BLE001
                break
            if cur != last and "扫一扫" not in cur:
                last = cur
                log(f"[页面变化] {cur[:100]}")
        browser.close()


if __name__ == "__main__":
    main()
