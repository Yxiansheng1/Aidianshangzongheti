"""工具层共用的几件小事：选解释器、把草稿落成 JSON、跑外部 CLI。

这里刻意不 import patchright，也不 import pipeline.content.headline：
填稿和发布都走 subprocess，浏览器依赖只活在子进程里。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from ..config import ROOT

DEFAULT_TIMEOUT = 1800


def resolve_python(explicit: str = "") -> str:
    """选哪个解释器跑 CLI。

    头条的 patchright 装在 social-auto-upload 的虚拟环境里，不在本项目 venv。
    所以允许用环境变量 AIDIANSHANG_PYTHON 指过去；不指定就用当前解释器。
    """
    return (explicit or os.environ.get("AIDIANSHANG_PYTHON") or sys.executable).strip()


def _normalise(draft: dict[str, Any]) -> dict[str, Any]:
    title = str(draft.get("title") or "").strip()
    body = str(draft.get("body") or "").strip()
    if not title or not body:
        raise ValueError("草稿缺标题或正文")

    return {
        "title": title,
        "body": body,
        "images": [str(i) for i in (draft.get("images") or []) if str(i).strip()],
        "tags": [str(t) for t in (draft.get("tags") or []) if str(t).strip()],
        "url": str(draft.get("url") or "").strip(),
    }


def prepare_draft(draft_path: str = "", draft: dict[str, Any] | None = None) -> Path:
    """拿到一份可交给 CLI 的草稿文件。

    两个入口二选一：已经落盘的 draft_path，或者刚生成的内存草稿。
    内存草稿写到系统临时目录，不污染 output/；路径会随结果返回，方便事后查。
    """
    if draft_path:
        path = Path(draft_path)
        if not path.is_file():
            raise FileNotFoundError(f"找不到草稿文件：{path}")
        return path

    if not draft:
        raise ValueError("要么给 draft_path，要么直接给 draft")

    payload = _normalise(draft)
    folder = Path(tempfile.gettempdir()) / "aidianshang-drafts"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"draft-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_cli(argv: list[str], *, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """跑一次外部 CLI，把成败和输出尾巴整理成统一结构。"""
    try:
        result = subprocess.run(
            argv,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "returncode": -1,
            "command": list(argv),
            "output": f"超过 {timeout} 秒没结束，流程可能卡在浏览器里",
        }

    output = (result.stdout or "") + (result.stderr or "")
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "command": list(argv),
        "output": output[-2000:],
    }
