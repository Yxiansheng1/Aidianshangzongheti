"""今日头条（头条号）：**半自动**发布——工具把草稿填进编辑器，最后一步人点。

为什么只做到一半：

- sau 的 17 个平台里没有头条模块，头条号也没有对个人开放发布接口
- 全自动模拟点击「发布」是平台风控最敏感的动作，这个账号体系里我们已经因为
  headless + 高频操作吃过两张警告

所以这里只做「把标题、正文、图片填进去」，**点发布这一步留给人**。
浏览器是可见的真实会话，人盯着它干活，出问题随时能接手。

用法（必须用 sau 的 venv 跑，patchright 装在那儿）：

    D:\\social-auto-upload\\.venv\\Scripts\\python.exe -m pipeline.content.headline login
    D:\\social-auto-upload\\.venv\\Scripts\\python.exe -m pipeline.content.headline fill --draft 草稿.json

草稿 JSON 格式：
    {"title": "...", "body": "...", "images": ["D:/.../a.png"], "url": "文章链接（可选）"}
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from ..config import ROOT

STATE_DIR = ROOT / "output" / "_state"
LOG_FILE = STATE_DIR / "headline.log"
EDITOR_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
HOME_URL = "https://mp.toutiao.com/profile_v4/index"


def state_file(account: str = "main") -> Path:
    """每个头条账号一份登录态，互不覆盖。

    账号名只允许字母数字下划线，避免拼出奇怪的路径。
    """
    safe = "".join(ch for ch in (account or "main") if ch.isalnum() or ch in "-_") or "main"
    return STATE_DIR / f"toutiao-{safe}.json"


# 旧版本只存过一份 toutiao.json，第一次跑多账号时把它迁成 main
def _migrate_legacy() -> None:
    legacy = STATE_DIR / "toutiao.json"
    target = state_file("main")
    if legacy.is_file() and not target.is_file():
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        legacy.replace(target)
        _say(f"[迁移] 旧登录态 → {target.name}")


ACCOUNT = "main"

TITLE_SELECTORS = [
    'input[placeholder*="标题"]',
    'textarea[placeholder*="标题"]',
    '.article-title input',
    '.article-title textarea',
    'input.byte-input__input[placeholder*="标题"]',
    'input[placeholder*="请输入文章标题"]',
]

BODY_SELECTORS = [
    'div.ProseMirror',
    '.ProseMirror',
    'div[contenteditable="true"]',
    '[data-contents="true"]',
    '.ql-editor',
]


def _say(msg: str) -> None:
    """同时打到控制台和日志文件。

    控制台是给当场看的人用的；日志是给「事后查为什么没填上」用的
    （窗口一关，控制台就没了）。
    """
    print(msg, flush=True)
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%H:%M:%S')}][{ACCOUNT}] {msg}\n")
    except OSError:
        pass


def _require_patchright():
    try:
        from patchright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "找不到 patchright。这个脚本要用 sau 的虚拟环境跑：\n"
            r"  D:\social-auto-upload\.venv\Scripts\python.exe -m pipeline.content.headline ..."
        ) from exc
    return sync_playwright


def _launch(playwright, headless: bool = False):
    """沿用 sau 的做法：patchright 自带的 chromium。"""
    for kwargs in ({"channel": "chromium"}, {"channel": "chrome"}, {}):
        try:
            return playwright.chromium.launch(headless=headless, **kwargs)
        except Exception:  # noqa: BLE001
            continue
    raise SystemExit("启动浏览器失败：patchright 的 chromium 和本机 chrome 都起不来")


def _first_visible(page, selectors: list[str], timeout: int = 4000):
    for sel in selectors:
        try:
            locator = page.locator(sel).first
            if locator.count() and locator.is_visible(timeout=1500):
                return locator
        except Exception:  # noqa: BLE001
            continue
    return None


def _logged_in(page) -> bool:
    """判断登录态。

    主判据是发布页出现标题输入框；但这套选择器万一变了，别让工具一直以为没登录
    （那样会在登录等待里反复刷新页面）。所以退一步：只要已经进了 profile_v4
    并且页面上有「发布」字样，就算登录了。
    """
    url = page.url or ""
    if "auth" in url or "/login" in url:
        return False
    if _first_visible(page, TITLE_SELECTORS, timeout=2000) is not None:
        return True
    try:
        return "profile_v4" in url and page.get_by_text("发布", exact=False).count() > 0
    except Exception:  # noqa: BLE001
        return False


def _open(playwright, *, state_file: Path | None):
    browser = _launch(playwright)
    context_kwargs: dict[str, Any] = {
        "viewport": {"width": 1440, "height": 900},
        "locale": "zh-CN",
    }
    if state_file and state_file.is_file():
        context_kwargs["storage_state"] = str(state_file)
    context = browser.new_context(**context_kwargs)
    page = context.new_page()
    return browser, context, page


def _save_state(context) -> None:
    target = state_file(ACCOUNT)
    target.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(target))
    _say(f"[状态] 登录态已保存（账号 {ACCOUNT}）：{target.name}")


def _wait_login(page, context, page_url: str, *, minutes: int = 5) -> None:
    """没登录就等用户扫码，登录成功后继续。"""
    page.goto(page_url, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    try:
        _say(f"[页面] {page.title()[:40]} | {page.url[:90]}")
    except Exception:  # noqa: BLE001
        pass
    if _logged_in(page):
        _save_state(context)
        return

    _say("")
    _say("=" * 60)
    _say(" 还没登录头条号。请在打开的浏览器里扫码登录（或用账号密码）。")
    _say(f" 登录成功后我会自动继续，最多等 {minutes} 分钟。")
    _say("=" * 60)

    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        page.wait_for_timeout(3000)
        if _logged_in(page):
            _say("[状态] 登录成功，继续。")
            _save_state(context)
            return
        if "auth" not in page.url and "login" not in page.url:
            page.goto(page_url, wait_until="domcontentloaded")

    raise SystemExit("等登录超时，退出。重新跑一次 login 即可。")


def login(account: str = "main") -> None:
    global ACCOUNT
    ACCOUNT = account
    _migrate_legacy()
    target = state_file(ACCOUNT)
    if target.is_file():
        # 已有登录态时，先备份再重登：扫码的是另一个号时，别把原来那份冲掉
        backup = target.with_suffix(f".{time.strftime('%Y%m%d-%H%M%S')}.bak.json")
        target.replace(backup)
        _say(f"[备份] 旧的登录态 → {backup.name}")

    sync_playwright = _require_patchright()
    with sync_playwright() as p:
        browser, context, page = _open(p, state_file=None)
        page.goto(HOME_URL, wait_until="domcontentloaded")
        _say("=" * 60)
        _say(f" 浏览器已打开（账号 {ACCOUNT}）。请扫码登录这个头条号，")
        _say(" 登录后窗口会自动关掉。想登另一个号，用 --account 换个名字再跑一次。")
        _say("=" * 60)

        deadline = time.time() + 300
        while time.time() < deadline:
            page.wait_for_timeout(3000)
            if "auth" not in page.url and "login" not in page.url:
                page.goto(EDITOR_URL, wait_until="domcontentloaded")
                if _logged_in(page):
                    _save_state(context)
                    _say("[完成] 登录态已保存，下次填稿不用再扫码。")
                    break
        else:
            _say("[超时] 没等到登录，什么都没保存。")
        browser.close()


def _fill_title(page, title: str) -> bool:
    box = _first_visible(page, TITLE_SELECTORS, timeout=15000)
    if not box:
        return False
    box.click()
    box.fill("")
    box.type(title, delay=15)

    # 回读：填进去和「以为填进去了」是两件事
    try:
        got = box.input_value(timeout=3000)
    except Exception:  # noqa: BLE001
        got = ""
    if not got.strip():
        _say("[警告] 标题框回读是空的，可能页面有遮罩或没登录。")
        return False
    _say(f"[核对] 标题回读：{got.strip()[:30]}")
    return True


def _fill_body(page, body: str) -> bool:
    editor = _first_visible(page, BODY_SELECTORS, timeout=8000)
    if not editor:
        return False

    editor.click()
    page.wait_for_timeout(300)

    # ProseMirror 里回车就是新段落。逐段插入，保留原来的空行结构。
    paragraphs = body.replace("\r\n", "\n").split("\n")
    for index, line in enumerate(paragraphs):
        if line.strip():
            page.keyboard.insert_text(line)
        if index != len(paragraphs) - 1:
            page.keyboard.press("Enter")

    # 回读：编辑器里到底有没有字
    try:
        got = editor.evaluate("el => el.innerText || el.textContent || ''")
    except Exception:  # noqa: BLE001
        got = ""
    got = (got or "").strip()
    if len(got) < 20:
        _say("[警告] 正文编辑器回读几乎是空的，可能编辑器还没就绪或被遮罩挡住。")
        return False
    _say(f"[核对] 正文回读：{len(got)} 字")
    return True


def _upload_images(page, images: list[str]) -> tuple[int, str]:
    """尽量把图塞进去。塞不进去不报错，只提示人工补。"""
    files = [str(Path(i)) for i in images if Path(i).is_file()]
    if not files:
        return 0, "没有可上传的图片"

    try:
        inputs = page.locator('input[type="file"]')
        count = inputs.count()
        if count:
            inputs.first.set_input_files(files)
            page.wait_for_timeout(4000)
            return len(files), ""
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)[:80]
    return 0, "页面上没找到上传入口"


def fill(draft_path: str, account: str = "main") -> None:
    global ACCOUNT
    ACCOUNT = account
    _migrate_legacy()

    data = json.loads(Path(draft_path).read_text(encoding="utf-8"))
    title = str(data.get("title") or "").strip()
    body = str(data.get("body") or "").strip()
    images = [str(i) for i in (data.get("images") or [])]
    source_url = str(data.get("url") or "").strip()

    if not title or not body:
        raise SystemExit("草稿缺标题或正文")

    sync_playwright = _require_patchright()
    with sync_playwright() as p:
        browser, context, page = _open(p, state_file=state_file(ACCOUNT))
        _wait_login(page, context, EDITOR_URL)

        # 有的页面不跳登录页，而是在发布页上挂一个登录弹层
        try:
            wall = (page.get_by_text("扫码登录", exact=False).count() > 0
                    or page.get_by_text("登录后即可", exact=False).count() > 0)
        except Exception:  # noqa: BLE001
            wall = False
        if wall:
            _say("[警告] 页面上有「扫码登录 / 登录后」字样，可能登录已过期。先登录再说。")

        _say(f"[填稿] 标题：{title}")
        title_ok = _fill_title(page, title)
        if not title_ok:
            _say("[警告] 标题没填上，需要你自己粘。")

        _say(f"[填稿] 正文：{len(body)} 字")
        body_ok = _fill_body(page, body)
        if not body_ok:
            _say("[警告] 正文没填上，需要你自己粘。")

        if images:
            done, reason = _upload_images(page, images)
            if done:
                _say(f"[填稿] 已选 {done} 张图，等页面处理完再检查封面。")
            else:
                _say(f"[提示] 图片没自动塞进去（{reason}），拖进去就行。")

        if source_url:
            _say(f"[提示] 原文链接（需要标转载时用）：{source_url}")

        _say("")
        _say("=" * 60)
        if title_ok and body_ok:
            _say(" 标题和正文已填好（上面有回读核对），**剩下的事交给你**：")
        else:
            _say(" 有一部分没自动填上（上面标了警告），**剩下的事交给你**：")
        _say("   1. 通读一遍，补上没填的部分，改你不满意的句子")
        _say("   2. 选封面、选分类、加标签")
        _say("   3. 自己点「发布」")
        _say(" 这个窗口先别关——关掉浏览器会一起关。发完再按回车。")
        _say("=" * 60)

        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        browser.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="headline", description="头条号半自动发布（工具填稿，人点发布）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_login = sub.add_parser("login", help="扫码登录并保存登录态")
    p_login.add_argument("--account", default="main", help="账号标识，例如 main / second")

    p_fill = sub.add_parser("fill", help="把草稿填进头条编辑器")
    p_fill.add_argument("--draft", required=True, help="草稿 JSON 路径")
    p_fill.add_argument("--account", default="main", help="账号标识，例如 main / second")

    args = parser.parse_args(argv)
    if args.cmd == "login":
        login(args.account)
    else:
        fill(args.draft, args.account)
    return 0


if __name__ == "__main__":
    sys.exit(main())
