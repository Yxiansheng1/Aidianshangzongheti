"""python -m pipeline.api：起本地服务。

只认 127.0.0.1，不对外开端口——这层是给本机 Electron 壳用的，不是服务器。
"""

from __future__ import annotations

import argparse
import os

import uvicorn

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def main(argv: list[str] | None = None) -> int:
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
