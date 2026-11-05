"""发布：subprocess 调头条发布脚本，本进程不碰浏览器。"""

from __future__ import annotations

from typing import Any

from ..config import ROOT
from ._common import DEFAULT_TIMEOUT, prepare_draft, resolve_python, run_cli

SCRIPT = ROOT / "scripts" / "publish_toutiao.py"


def publish(
    draft_path: str = "",
    *,
    draft: dict[str, Any] | None = None,
    account: str = "main",
    python_exe: str = "",
    wait: int = 25,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """真的点头条发布：填稿 → 预览 → 确认发布。

    跑的是 `scripts/publish_toutiao.py --draft ... --confirm`。
    不可逆，注册表里固定要求人工确认；脚本输出只作参考，
    最终是否发出去以头条后台为准。
    """
    if not SCRIPT.is_file():
        raise FileNotFoundError(f"找不到发布脚本：{SCRIPT}")

    path = prepare_draft(draft_path, draft)
    argv = [
        resolve_python(python_exe),
        str(SCRIPT),
        "--draft",
        str(path),
        "--account",
        account,
        "--confirm",
        "--wait",
        str(int(wait)),
    ]
    result = run_cli(argv, timeout=timeout)
    result["draft_path"] = str(path)

    if result["ok"] and "没找到确认按钮" in result["output"]:
        result["ok"] = False
        result["note"] = "流程跑完了，但没点到确认发布按钮；去头条后台核对"
    else:
        result["note"] = "发布结果以头条后台为准，工具只回报脚本输出"
    return result
