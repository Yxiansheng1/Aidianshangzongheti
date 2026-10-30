"""把账号资料填进头条后台设置页（昵称 / 简介 / 头像 / 内容类别）。

资料出处：output/账号资料/账号1-老韩读报.md、账号2-档案室.md
能自动填的就自动填；「头条号类型（实名）」必须你在 App 里扫脸，做不了。

用法：
    D:\\social-auto-upload\\.venv\\Scripts\\python.exe scripts\\set_toutiao_profile.py --account main
    ... --account second
    ... --account main --dry-run     # 只打开看，不保存

注意：头条的「用户名」每月只能改 1 次，脚本会在保存前把新旧值打出来。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from patchright.sync_api import sync_playwright

STATE_DIR = Path(r"D:\AIdianshangzongheti\output\_state")
PROFILE_URL = "https://mp.toutiao.com/profile_v4/personal/info"

# 与 output/账号资料/*.md 一致。简介先用长版，超长就自动退回短版。
PROFILES = {
    "main": {
        "nick": "老韩读报",
        "bio": "读外媒和公报，只讲查得到出处的事；说不清的就说说不清。国际时事与政策解读，讲清楚发生了什么、跟你有什么关系。",
        "bio_short": "读外媒和公报，只讲查得到出处的事。",
        "avatar": r"D:\AIdianshangzongheti\output\账号资料\头像-账号1-512.png",
        "category": "国际",
        "category_alt": "军事",
    },
    "second": {
        "nick": "档案室",
        "bio": "翻旧文件、老照片、地方志，讲被忘掉的那部分历史。只写查得到的细节，查不到的就不写。",
        "bio_short": "翻旧文件、老照片，讲被忘掉的那部分。",
        "avatar": r"D:\AIdianshangzongheti\output\账号资料\头像-账号2-512.png",
        "category": "历史",
        "category_alt": "文化",
    },
}


def log(msg: str) -> None:
    print(msg, flush=True)


def row_text(page, label: str) -> str:
    return page.evaluate(
        """(label) => {
            const el = Array.from(document.querySelectorAll('div.label'))
                .find(e => (e.innerText || '').trim() === label);
            if (!el) return '';
            const c = el.parentElement.querySelector('.content');
            return c ? (c.innerText || '').replace(/\\s+/g, ' ').trim() : '';
        }""",
        label,
    )


def open_edit(page, label: str) -> bool:
    ok = page.evaluate(
        """(label) => {
            const el = Array.from(document.querySelectorAll('div.label'))
                .find(e => (e.innerText || '').trim() === label);
            if (!el) return false;
            const btn = el.parentElement.querySelector('button.edit-button');
            if (!btn) return false;
            btn.click();
            return true;
        }""",
        label,
    )
    page.wait_for_timeout(1800)
    return bool(ok)


def modal_visible(page) -> bool:
    return page.evaluate(
        """() => {
            const m = document.querySelector('.byte-modal');
            return !!m && m.offsetParent !== null;
        }"""
    )


def modal_text(page) -> str:
    return page.evaluate(
        """() => {
            const m = document.querySelector('.byte-modal');
            return m ? (m.innerText || '').replace(/\\s+/g, ' ').trim() : '';
        }"""
    )


def save_modal(page) -> bool:
    """点弹窗里的保存/确定，返回是否点到。"""
    res = page.evaluate(
        """() => {
            const m = document.querySelector('.byte-modal');
            if (!m) return 'no-modal';
            const btns = Array.from(m.querySelectorAll('button'))
                .filter(b => ['保存', '确定', '提交'].includes((b.innerText || '').trim()));
            if (!btns.length) return 'no-save-btn';
            const b = btns[btns.length - 1];
            if (b.disabled) return 'disabled';
            b.click();
            return 'ok';
        }"""
    )
    page.wait_for_timeout(2500)
    return res == 'ok'


def close_modal(page) -> None:
    """把弹窗关干净，别让它挡住下一项。"""
    for _ in range(3):
        if not modal_visible(page):
            return
        page.evaluate(
            """() => {
                const m = document.querySelector('.byte-modal');
                if (!m) return;
                const cancel = Array.from(m.querySelectorAll('button'))
                    .filter(b => ['取消', '关闭'].includes((b.innerText || '').trim()));
                if (cancel.length) { cancel[cancel.length - 1].click(); return; }
                const x = m.querySelector('.byte-modal-close-icon');
                if (x) x.click();
            }"""
        )
        page.wait_for_timeout(700)
        if not modal_visible(page):
            return
        page.keyboard.press("Escape")
        page.wait_for_timeout(700)


def set_text_field(page, label: str, value: str, *, dry: bool) -> bool:
    close_modal(page)
    before = row_text(page, label)
    if not open_edit(page, label):
        log(f"  ✗ {label}：找不到「编辑」")
        return False
    if not modal_visible(page):
        log(f"  ✗ {label}：没弹出编辑窗")
        return False
    if dry:
        log(f"  · {label}：当前「{before}」→ 将填「{value}」（试运行未保存）")
        close_modal(page)
        return True

    # 头条的输入框没写 type 属性，不能用 input[type=text] 选
    box = page.locator(
        ".byte-modal input:not([type=file]):not([type=hidden]), .byte-modal textarea"
    ).first
    try:
        box.wait_for(state="visible", timeout=8000)
    except Exception:  # noqa: BLE001
        log(f"  ✗ {label}：输入框一直没出现")
        close_modal(page)
        return False

    box.click()
    box.fill("")
    box.type(value, delay=12)
    page.wait_for_timeout(800)

    hint = modal_text(page)
    limit = re.search(r"(\d+)/(\d+)", hint)
    if limit and int(limit.group(1)) > int(limit.group(2)):
        log(f"  ! {label}：字数超限（{limit.group(0)}），保存会被禁用")
    log(f"  · {label}：准备写入「{value}」（{len(value)} 字）")

    if not save_modal(page):
        log(f"  ✗ {label}：保存按钮点不动（可能超长或校验没过）")
        close_modal(page)
        return False

    page.wait_for_timeout(1500)
    close_modal(page)
    after = wait_row(page, label, value)
    ok = (value[:4] in after) or ("审核中" in after)
    log(f"  {'✓' if ok else '?'} {label}：「{before}」→「{after}」")
    return ok


def set_avatar(page, path: str, *, dry: bool) -> bool:
    before = row_text(page, "用户头像")
    if dry:
        log(f"  · 用户头像：将上传 {Path(path).name}（当前「{before or '默认头像'}」，试运行未上传）")
        return True
    try:
        page.locator(".m-avataruploader input[type=file]").first.set_input_files(path)
    except Exception as exc:  # noqa: BLE001
        log(f"  ✗ 用户头像：上传入口没找到（{str(exc)[:60]}）")
        return False
    page.wait_for_timeout(3500)

    if modal_visible(page):
        log(f"  · 头像弹窗：{modal_text(page)[:120]}")
        if not save_modal(page):
            log("  ! 头像弹窗里没点到保存，请看截图人工确认")
            page.screenshot(path=str(STATE_DIR / "profile-avatar.png"))
            close_modal(page)
            return False
        page.wait_for_timeout(1500)
        close_modal(page)

    page.wait_for_timeout(1500)
    log("  ✓ 用户头像：已上传（页面没报错）")
    return True


def wait_row(page, label: str, needle: str, tries: int = 4) -> str:
    """保存之后页面不会自动刷新，重新加载再读；「审核中」也算写成功。"""
    txt = row_text(page, label)
    for _ in range(tries):
        txt = row_text(page, label)
        if (needle and needle[:4] in txt) or "审核中" in txt:
            return txt
        page.wait_for_timeout(1500)
    # 页面内可能还是旧值，整页重载再看一次
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(4500)
    try:
        page.get_by_text("我知道了", exact=True).first.click()
        page.wait_for_timeout(500)
    except Exception:  # noqa: BLE001
        pass
    return row_text(page, label)


def set_category(page, want: str, alt: str, *, dry: bool) -> bool:
    close_modal(page)
    before = row_text(page, "内容类别")
    if not open_edit(page, "内容类别"):
        log("  ✗ 内容类别：找不到「编辑」")
        return False
    if not modal_visible(page):
        log("  ✗ 内容类别：没弹出编辑窗")
        return False

    # 级联选择器要用真实鼠标事件，JS 的 click() 不算数（实测点了没反应）
    try:
        page.locator(".byte-modal .byte-cascader").first.click()
    except Exception as exc:  # noqa: BLE001
        log(f"  ✗ 内容类别：下拉打不开（{str(exc)[:50]}）")
        close_modal(page)
        return False
    page.wait_for_timeout(1500)

    options = page.evaluate(
        """() => Array.from(document.querySelectorAll('.byte-cascader-list-item'))
            .map(i => (i.innerText || '').trim()).filter(Boolean)"""
    )
    target = want if want in options else (alt if alt in options else "")

    if dry:
        log(f"  · 内容类别：当前「{before or '暂无'}」→ 将选「{target or want}」（试运行未保存）")
        close_modal(page)
        return True
    if not target:
        log(f"  ✗ 内容类别：列表里既没有「{want}」也没有「{alt}」")
        close_modal(page)
        return False

    try:
        page.locator(".byte-cascader-list-item").filter(has_text=target).first.click()
    except Exception as exc:  # noqa: BLE001
        log(f"  ✗ 内容类别：点不到「{target}」（{str(exc)[:50]}）")
        close_modal(page)
        return False
    page.wait_for_timeout(1200)

    picked = page.evaluate(
        """() => {
            const v = document.querySelector('.byte-cascader-view-inner');
            return v ? (v.innerText || '').replace(/\\s+/g, '') : '';
        }"""
    )
    if target not in picked:
        log(f"  ✗ 内容类别：选了但没生效（显示「{picked or '空'}」）")
        close_modal(page)
        return False

    if not save_modal(page):
        log("  ✗ 内容类别：保存按钮点不动")
        close_modal(page)
        return False
    close_modal(page)
    after = wait_row(page, "内容类别", target)
    ok = target in after
    log(f"  {'✓' if ok else '?'} 内容类别：「{before or '暂无'}」→「{after}」")
    return ok


def fresh(page) -> None:
    """每项都从干净的页面开始：头像弹窗关掉后遮罩还在，会挡住后面的点击。"""
    page.goto(PROFILE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    try:
        page.get_by_text("我知道了", exact=True).first.click()
        page.wait_for_timeout(500)
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True, choices=sorted(PROFILES))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default="", help="只做某一项：nick/bio/avatar/category，逗号分隔")
    args = ap.parse_args()

    prof = PROFILES[args.account]
    state = STATE_DIR / f"toutiao-{args.account}.json"
    if not state.is_file():
        raise SystemExit(f"没有 {state.name}，先登录这个号")

    only = {x.strip() for x in args.only.split(",") if x.strip()} or {"nick", "bio", "avatar", "category"}

    log(f"=== 账号 {args.account} → {prof['nick']}（{'试运行' if args.dry_run else '真写'}）===")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not sys.stdout.isatty(), channel="chromium")
        ctx = browser.new_context(storage_state=str(state), viewport={"width": 1500, "height": 950})
        page = ctx.new_page()
        page.goto(PROFILE_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(4500)
        if "auth" in page.url or "login" in page.url:
            raise SystemExit("登录态失效了，先重新登录")

        try:
            page.get_by_text("我知道了", exact=True).first.click()
            page.wait_for_timeout(600)
        except Exception:  # noqa: BLE001
            pass

        log("当前状态：")
        for label in ("用户名", "用户简介", "用户头像", "内容类别", "头条号类型"):
            log(f"  {label}: {row_text(page, label) or '暂无'}")

        results = {}
        if "avatar" in only:
            log("\n[头像]")
            fresh(page)
            results["avatar"] = set_avatar(page, prof["avatar"], dry=args.dry_run)
        if "bio" in only:
            log("\n[简介]")
            fresh(page)
            ok = set_text_field(page, "用户简介", prof["bio"], dry=args.dry_run)
            if not ok and not args.dry_run:
                log("  长版没成功，试短版")
                fresh(page)
                ok = set_text_field(page, "用户简介", prof["bio_short"], dry=args.dry_run)
            results["bio"] = ok
        if "category" in only:
            log("\n[内容类别]")
            fresh(page)
            results["category"] = set_category(page, prof["category"], prof["category_alt"], dry=args.dry_run)
        if "nick" in only:
            log("\n[用户名]（每月只能改 1 次）")
            fresh(page)
            if prof["nick"] in row_text(page, "用户名"):
                log(f"  = 已经是「{prof['nick']}」，跳过")
                results["nick"] = True
            else:
                results["nick"] = set_text_field(page, "用户名", prof["nick"], dry=args.dry_run)

        page.wait_for_timeout(1000)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(4500)
        page.screenshot(path=str(STATE_DIR / f"profile-{args.account}.png"), full_page=True)
        log("\n最终状态：")
        for label in ("用户名", "用户简介", "用户头像", "内容类别", "头条号类型"):
            log(f"  {label}: {row_text(page, label) or '暂无'}")

        log("\n各项结果：" + "  ".join(f"{k}={'✓' if v else '✗'}" for k, v in results.items()))
        browser.close()

    if not args.dry_run and not all(results.values()):
        raise SystemExit("有项目没成功，看上面的日志和 output/_state/profile-*.png")


if __name__ == "__main__":
    main()
