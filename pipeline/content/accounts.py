"""账号管理：每个平台的账号清单 + 登录态是否在。

现在的事实：
- 小红书 / 抖音 / 快手 / 知乎 / B站 … 走 sau，账号文件是 cookies/<平台>_<账号>.json
- 头条没有 sau 模块，是我们自己的 output/_state/toutiao-<账号>.json

所以统一成一张表：平台 → 账号列表 → 每个账号是否已登录。
界面据此渲染下拉，避免"发了半天发错号"。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import ROOT

SAU_COOKIES = Path(r"D:\social-auto-upload\cookies")
STATE_DIR = ROOT / "output" / "_state"

# 账号名 → 给人看的名字。账号名是 sau 的 --account 参数，别改。
ACCOUNT_LABELS = {
    "main": "主号",
    "second": "二号",
    "third": "三号",
}

# 平台 → (显示名, sau 平台标识)
PLATFORMS: dict[str, str] = {
    "小红书": "xiaohongshu",
    "抖音": "douyin",
    "快手": "kuaishou",
    "知乎": "zhihu",
    "B站": "bilibili",
    "视频号": "tencent",
    "微博": "weibo",
    "百家号": "baijiahao",
}


def _sau_cookie(platform: str, account: str) -> Path:
    return SAU_COOKIES / f"{platform}_{account}.json"


def _toutiao_state(account: str) -> Path:
    return STATE_DIR / f"toutiao-{account}.json"


def accounts_of(display_name: str) -> list[dict[str, Any]]:
    """列出某个平台下所有账号，标明是否已登录。

    账号清单有两个来源：
    1. 磁盘上已存在的账号文件（登录过的）
    2. config.toml 里配的（还没登录的，显示"未登录"）
    """
    sau_platform = PLATFORMS.get(display_name)
    if not sau_platform:
        return []

    found: dict[str, bool] = {}

    if SAU_COOKIES.is_dir():
        prefix = f"{sau_platform}_"
        for path in SAU_COOKIES.glob(f"{prefix}*.json"):
            name = path.stem[len(prefix):]
            if name:
                found[name] = path.stat().st_size > 200

    # 常见名兜底：至少把 main 露出来
    if not found:
        found["main"] = False

    out = []
    for name in sorted(found):
        out.append({
            "name": name,
            "label": f"{ACCOUNT_LABELS.get(name, name)}（{name}）",
            "logged": bool(found[name]),
        })
    return out


def headline_accounts() -> list[dict[str, Any]]:
    """头条账号（我们自己存登录态）。"""
    found: dict[str, bool] = {}
    if STATE_DIR.is_dir():
        for path in STATE_DIR.glob("toutiao-*.json"):
            name = path.stem[len("toutiao-"):]
            if name and "draft" not in name and "stats" not in name:
                found[name] = path.stat().st_size > 200
    if not found:
        found["main"] = False
    return [
        {"name": name, "label": f"{ACCOUNT_LABELS.get(name, name)}（{name}）",
         "logged": bool(found[name])}
        for name in sorted(found)
    ]


def login_state() -> dict[str, Any]:
    """一次拿全所有平台的账号情况，界面一次渲染完。"""
    data: dict[str, Any] = {"platforms": {}, "headline": headline_accounts()}
    for display in PLATFORMS:
        data["platforms"][display] = accounts_of(display)
    return data
