"""填进头条编辑器：subprocess 调现有 CLI，本进程不碰浏览器。"""

from __future__ import annotations

from typing import Any

from ._common import DEFAULT_TIMEOUT, prepare_draft, resolve_python, run_cli

CLI_MODULE = "pipeline.content.headline"


def fill_editor(
    draft_path: str = "",
    *,
    draft: dict[str, Any] | None = None,
    account: str = "main",
    python_exe: str = "",
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """把标题、正文、图片填进头条编辑器，**不点发布**。

    跑的是 `python -m pipeline.content.headline fill --draft ...`。
    要扫码登录或补图时窗口会留着，最后由人收尾。
    """
    path = prepare_draft(draft_path, draft)
    argv = [
        resolve_python(python_exe),
        "-m",
        CLI_MODULE,
        "fill",
        "--draft",
        str(path),
        "--account",
        account,
    ]
    result = run_cli(argv, timeout=timeout)
    result["draft_path"] = str(path)
    return result
