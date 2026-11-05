"""python -m pipeline.api：起本地服务。

只认 127.0.0.1，不对外开端口——这层是给本机 Electron 壳用的，不是服务器。
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time

import uvicorn

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

WATCHDOG_ENV = "AID_API_WATCHDOG"


def _parent_alive(parent_pid: int) -> bool:
    """父进程还活着吗。Windows 上 os.getppid() 返回的是创建时的父 PID，
    父进程死了也照旧返回，所以得真的去问系统。"""
    if parent_pid <= 0:
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, parent_pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                # STILL_ACTIVE = 259
                return exit_code.value == 259
            return True
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return True


def start_parent_watchdog() -> threading.Thread:
    """父进程没了就自杀。

    场景：Electron 被强杀（任务管理器结束任务、断电、崩溃），
    Windows 不会连带杀掉子进程，python 会变成孤儿霸着 8765 端口，
    下次启动客户端就会撞端口。这个看门狗是给这种场景兜底的。

    注意 Windows 上 .venv\\Scripts\\python.exe 还会再开一个系统 python，
    真正 listen 端口的是那个孙进程。好在每个 python 进程都会启动自己的看门狗，
    所以父进程一死，子进程几秒内也会跟着退——不需要在自尽时按树杀。
    """

    parent_pid = os.getppid()

    def suicide() -> None:
        # 只杀自己：树里每个 python 进程都有自己的看门狗，
        # 父进程一死它们就跟着死。用 taskkill /T 会误伤正在执行 taskkill 的 cmd.exe。
        os._exit(0)

    def loop() -> None:
        while True:
            time.sleep(2)
            if not _parent_alive(parent_pid):
                suicide()

    t = threading.Thread(target=loop, name="parent-watchdog", daemon=True)
    t.start()
    return t


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 cp1252，中文 print 会直接 UnicodeEncodeError 把服务打死。
    # 这里统一按 UTF-8 输出，编不出来的字用 ? 代替，宁可掉字不许掉进程。
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="python -m pipeline.api", description="本地 API 服务")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"监听地址（默认 {DEFAULT_HOST}）")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("AID_API_PORT", DEFAULT_PORT)),
        help=f"监听端口（默认 {DEFAULT_PORT}，可用环境变量 AID_API_PORT 覆盖）",
    )
    parser.add_argument("--reload", action="store_true", help="改代码自动重启（开发用）")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args(argv)

    if os.environ.get(WATCHDOG_ENV) == "1":
        start_parent_watchdog()

    print(f"API 监听 http://{args.host}:{args.port}", flush=True)
    if args.reload:
        uvicorn.run(
            "pipeline.api.app:app",
            host=args.host,
            port=args.port,
            reload=True,
            log_level=args.log_level,
        )
    else:
        # 传对象而不是字符串：不给 reload/多进程留隐患，进程只有一个，杀得干净。
        from .app import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port, log_level=args.log_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
