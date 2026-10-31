"""百家号：登录 + 状态核查。

sau 的百家号只支持视频，图文得自己走一遍浏览器。所以登录也自己管：
登录态存到 D:\\social-auto-upload\\cookies\\baijiahao_<账号>.json（和 sau 同一位置，
项目里的账号列表直接能读到）。

用法：
    # 打开窗口扫码，最多等 20 分钟
    D:\\social-auto-upload\\.venv\\Scripts\\python.exe -m pipeline.content.baijiahao login --account main
    # 只读核查：这个号登的是谁、能不能发
    ... check --account main
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

COOKIE_DIR = Path(r"D:\social-auto-upload\cookies")
STATE_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "_state"
LOGIN_URL = "https://baijiahao.baidu.com/builder/theme/bjh/login"
HOME_URL = "https://baijiahao.baidu.com/builder/rc/home"
EDIT_URL = "https://baijiahao.baidu.com/builder/rc/edit?type=news"


def state_file(account: str = "main") -> Path:
    return COOKIE_DIR / f"baijiahao_{account}.json"


def say(msg: str) -> None:
    print(msg, flush=True)


def _close_promo(page) -> None:
    """首屏那个 AI 助手推广弹窗会挡住编辑器。"""
    for sel in ('button[aria-label="关闭"]', '.cheetah-modal-close'):
        try:
            if page.locator(sel).count():
                page.locator(sel).first.click(timeout=3000)
                page.wait_for_timeout(1000)
                return
        except Exception:  # noqa: BLE001
            continue


def _body_frame(page):
    """正文是 UEditor，装在 iframe 里，body 可编辑、宽度大于 300 的那个。"""
    for fr in page.frames:
        if fr == page.main_frame:
            continue
        try:
            rect = fr.evaluate(
                """() => { const r = document.body ? document.body.getBoundingClientRect() : {width:0};
                           return Math.round(r.width); }"""
            )
        except Exception:  # noqa: BLE001
            continue
        if rect and rect > 300:
            return fr
    return None


def _click_text(page, labels: tuple[str, ...], *, within=None) -> str:
    """按可见文字找一个元素并真实点击（百家号很多"按钮"不是 button，文字也可能带 "(1)"）。"""
    scope = within or page
    for label in labels:
        # 1) 文字完全一致
        try:
            loc = scope.get_by_text(label, exact=True)
            for i in range(min(loc.count(), 4)):
                el = loc.nth(i)
                if el.is_visible():
                    el.click(timeout=4000)
                    return label
        except Exception:  # noqa: BLE001
            pass
        # 2) 按钮文字里含这个词（如「确定 (1)」）
        try:
            loc = scope.locator("button, [role=button]").filter(has_text=label)
            for i in range(loc.count() - 1, -1, -1):
                el = loc.nth(i)
                if el.is_visible():
                    text = (el.inner_text() or label).strip()
                    el.click(timeout=4000)
                    return text[:12]
        except Exception:  # noqa: BLE001
            pass
    return ""


def fill(account: str, title: str, body: str, *, cover: str = "", topics: list[str] | None = None,
         ai_declare: bool = True, publish: bool = False, probe_publish: bool = False,
         headless: bool = False) -> dict:
    """填一篇图文；publish=True 时继续点发布。

    返回 {"ok":..., "url":..., "notes":[...]}，不抛异常给上层难看。
    """
    sync_playwright = _playwright()
    notes: list[str] = []
    state = state_file(account)
    if not state.is_file():
        raise SystemExit(f"没有登录态：{state}，先跑 login --account {account}")

    target = state_file(account)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, channel="chromium")
        ctx = browser.new_context(storage_state=str(target), viewport={"width": 1500, "height": 950}, locale="zh-CN")
        page = ctx.new_page()
        page.goto(EDIT_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(9000)
        _close_promo(page)

        # 标题
        try:
            page.locator("[data-lexical-editor=true]").first.click(timeout=8000)
            page.keyboard.insert_text(title)
            page.wait_for_timeout(800)
            got = page.locator("[data-lexical-editor=true]").first.inner_text().strip()
            notes.append(f"标题回读：{got[:40]}")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"标题没填上：{str(exc)[:60]}")

        # 正文
        fr = _body_frame(page)
        if not fr:
            notes.append("找不到正文编辑器（UEditor iframe）")
        else:
            fr.locator("body").first.click()
            page.wait_for_timeout(400)
            paragraphs = body.replace("\r\n", "\n").split("\n")
            for i, line in enumerate(paragraphs):
                if line.strip():
                    page.keyboard.insert_text(line)
                if i != len(paragraphs) - 1:
                    page.keyboard.press("Enter")
            page.wait_for_timeout(1500)
            text = fr.locator("body").first.inner_text()
            notes.append(f"正文回读：{len(text)} 字")

        # 封面
        if cover and Path(cover).is_file():
            try:
                page.get_by_text("选择封面", exact=True).first.click(timeout=6000)
                page.wait_for_timeout(2500)
                page.locator('input[type="file"][accept*="image"]').first.set_input_files(cover)
                page.wait_for_timeout(6000)
                hit = _click_text(page, ("确定",))
                page.wait_for_timeout(3000)
                notes.append(f"封面：已上传（{hit or '没点到确定'}）")
            except Exception as exc:  # noqa: BLE001
                notes.append(f"封面没设置成功：{str(exc)[:60]}")

        # AI 声明
        if ai_declare:
            try:
                hit = page.evaluate(
                    """() => {
                        const labels = Array.from(document.querySelectorAll('*'))
                            .filter(e => (e.innerText || '').trim() === '采用AI生成内容'
                                         && e.getBoundingClientRect().height > 0);
                        if (!labels.length) return '';
                        let box = labels[0];
                        for (let i = 0; i < 4 && box.parentElement; i++) box = box.parentElement;
                        const input = box.querySelector('input[type=checkbox]');
                        if (input) { if (!input.checked) input.click(); return 'checked'; }
                        return '';
                    }"""
                )
                notes.append(f"AI 声明：{hit or '没找到勾选项'}")
            except Exception as exc:  # noqa: BLE001
                notes.append(f"AI 声明失败：{str(exc)[:50]}")

        page.wait_for_timeout(1500)
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if topics:
            notes.append("话题：这一步还没接（百家号话题在「插入→话题」，下一步补）")
        shot = STATE_DIR / f"bjh-filled-{account}.png"
        page.screenshot(path=str(shot))

        if not publish and not probe_publish:
            browser.close()
            return {"ok": True, "published": False, "notes": notes, "screenshot": str(shot)}

        # 发布
        hit = _click_text(page, ("发布",))
        page.wait_for_timeout(5000)
        dialog = page.evaluate(
            """() => Array.from(document.querySelectorAll('[class*=modal], [role=dialog], [class*=drawer]'))
                .filter(e => e.getBoundingClientRect().height > 100)
                .map(e => (e.innerText || '').replace(/\\s+/g, ' ').slice(0, 500))"""
        )
        page.screenshot(path=str(STATE_DIR / f"bjh-publish-dialog-{account}.png"))
        notes.append(f"发布弹窗：{dialog or '（没弹窗）'}")

        if probe_publish:
            cancelled = _click_text(page, ("取消",))
            notes.append(f"试运行：点了「{cancelled or '没找到取消'}」，没有发布")
            page.wait_for_timeout(1500)
            page.screenshot(path=str(STATE_DIR / f"bjh-probe-cancel-{account}.png"))
            browser.close()
            return {"ok": True, "published": False, "notes": notes, "dialog": dialog}

        confirmed = _click_text(page, ("确认发布", "确定发布", "确定"))
        page.wait_for_timeout(7000)
        after = page.evaluate(
            """() => ({url: location.href, text: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 200)})"""
        )
        page.screenshot(path=str(STATE_DIR / f"bjh-after-publish-{account}.png"))
        notes.append(f"发布后：{after['url'][:90]}")
        browser.close()
        return {
            "ok": bool(confirmed),
            "published": True,
            "confirmed": confirmed,
            "notes": notes,
            "url": after["url"],
        }


def _playwright():
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:  # noqa: BLE001
        raise SystemExit(
            "没有 patchright。用 sau 的 venv 跑：\n"
            r"  D:\social-auto-upload\.venv\Scripts\python.exe -m pipeline.content.baijiahao login --account main"
        )
    return sync_playwright


def has_login_cookie(context) -> bool:
    try:
        names = {c.get("name") for c in context.cookies()}
    except Exception:  # noqa: BLE001
        return False
    return "BDUSS" in names


def login(account: str = "main", minutes: int = 20) -> None:
    sync_playwright = _playwright()
    target = state_file(account)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chromium")
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        # 首页只是宣传页，要先点「登录/注册百家号」才会出二维码
        for label in ("登录/注册百家号", "登录"):
            try:
                btn = page.get_by_text(label, exact=False).first
                if btn.count():
                    btn.click()
                    page.wait_for_timeout(4000)
                    break
            except Exception:  # noqa: BLE001
                continue

        shot = STATE_DIR / f"baijiahao-login-{account}.png"
        page.screenshot(path=str(shot))
        say("=" * 62)
        say(f" 浏览器已打开（百家号账号 {account}）。")
        say(" 手机上：百度 App → 扫一扫 → 扫窗口里那个二维码。")
        say(f" 二维码截图也存了一份：{shot}")
        say(f" 最多等 {minutes} 分钟；扫完窗口会自己关。")
        say("=" * 62)

        deadline = time.time() + minutes * 60
        saved = False
        while time.time() < deadline:
            page.wait_for_timeout(3000)
            if not has_login_cookie(context):
                continue
            # 有 BDUSS 了，再确认已经进到百家号后台（不是停在百度登录页）
            page.wait_for_timeout(4000)
            url = page.url or ""
            if "login" in url or "passport" in url:
                continue
            context.storage_state(path=str(target))
            say(f"[完成] 登录态已保存：{target.name}")
            say(f"[页面] {url[:100]}")
            page.screenshot(path=str(STATE_DIR / f"baijiahao-after-{account}.png"))
            saved = True
            break

        if not saved:
            say("[超时] 没扫上，什么都没保存。重跑一次即可。")
        browser.close()


def identity(account: str = "main") -> dict:
    """当前登录的百家号是谁：/builder/app/appinfo 里的 id + name（稳定，改名也不影响 id）。"""
    sync_playwright = _playwright()
    target = state_file(account)
    if not target.is_file():
        return {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chromium")
        ctx = browser.new_context(storage_state=str(target), viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)
        info: dict = {}
        try:
            resp = page.request.get("https://baijiahao.baidu.com/builder/app/appinfo", timeout=20000)
            if resp.ok:
                data = resp.json() or {}
                user = ((data.get("data") or {}) if isinstance(data.get("data"), dict) else {}).get("user") or {}
                info = {
                    "id": str(user.get("id") or user.get("userid") or ""),
                    "name": str(user.get("name") or ""),
                    "phone": str(user.get("uname") or ""),
                    "app_id": str(user.get("app_id") or ""),
                    "url": page.url,
                }
        except Exception:  # noqa: BLE001
            info = {"url": page.url}
        browser.close()
    return info


def check(account: str = "main") -> int:
    """只读：看一眼这个号的登录态是不是真的、后台显示的是谁。"""
    sync_playwright = _playwright()
    target = state_file(account)
    if not target.is_file():
        say(f"没有登录态：{target}")
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chromium")
        context = browser.new_context(storage_state=str(target), viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(5000)
        info = page.evaluate(
            """() => {
                const t = (document.body.innerText || '').replace(/\\s+/g, ' ');
                return {url: location.href, text: t.slice(0, 300)};
            }"""
        )
        say(f"[{account}] 地址：{info['url'][:100]}")
        say(f"[{account}] 页面：{info['text'][:220]}")
        page.screenshot(path=str(STATE_DIR / f"baijiahao-home-{account}.png"))
        browser.close()

    ok = "login" not in info["url"] and "passport" not in info["url"]
    say("结论：" + ("✅ 登录态有效" if ok else "❌ 登录态无效，要重新登录"))
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["login", "check", "fill"])
    ap.add_argument("--account", default="main")
    ap.add_argument("--minutes", type=int, default=20)
    ap.add_argument("--draft", help="草稿 JSON（title/body/images/tags）")
    ap.add_argument("--cover", default="", help="封面图路径，留空就用草稿第一张图")
    ap.add_argument("--publish", action="store_true", help="填完直接点发布")
    ap.add_argument("--probe-publish", action="store_true", help="只点到发布弹窗看结构，不提交")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    if args.action == "login":
        login(args.account, args.minutes)
        return

    if args.action == "check":
        raise SystemExit(check(args.account))

    if args.action == "fill":
        if not args.draft:
            raise SystemExit("fill 需要 --draft")
        data = json.loads(Path(args.draft).read_text(encoding="utf-8"))
        images = [str(i) for i in (data.get("images") or [])]
        cover = args.cover or (images[0] if images else "")
        result = fill(
            args.account,
            str(data.get("title") or ""),
            str(data.get("body") or ""),
            cover=cover,
            topics=[str(t) for t in (data.get("tags") or [])],
            publish=args.publish,
            probe_publish=args.probe_publish,
            headless=args.headless,
        )
        for note in result["notes"]:
            say("  " + note)
        say(f"结果：已发布={result.get('published')} 确认={result.get('confirmed', '-')}")
        if not result.get("ok"):
            raise SystemExit(1)
        return


if __name__ == "__main__":
    main()
