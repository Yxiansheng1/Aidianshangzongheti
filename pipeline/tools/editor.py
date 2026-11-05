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
    hold: int = 900,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """把标题、正文、图片填进头条编辑器，**不点发布**。

    跑的是 `python -m pipeline.content.headline fill --draft ... --hold N`。

    hold：填完后窗口保留多少秒。**必须给非 0 值**——从 API/子进程调用时没有终端，
    以前 `input()` 会因 stdin EOF 立刻抛异常、把浏览器关掉，填好的稿子全丢。
    默认 900 秒（15 分钟），够人过去改稿、点发布。
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
        "--hold",
        str(max(int(hold), 0)),
    ]
    result = run_cli(argv, timeout=timeout)
    result["draft_path"] = str(path)
    result["hold_s"] = hold
    return result
