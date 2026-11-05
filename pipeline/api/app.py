"""L3：本地 FastAPI 薄壳。

    GET /api/health  进程活着没有；顺带报个工具数（读失败也不影响 200）。
    GET /api/tools   L2 的工具清单（名称 / 说明 / 风险等级 / 是否关键）。

工具层没就绪时 /api/tools 仍然回 200，但 ok=false 且带 error。
这样界面能显示"工具层未就绪"，而不是靠一个 500 去猜。
"""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import FastAPI

from .catalog import load_tool_catalog

SERVICE_NAME = "aidianshang-api"
API_VERSION = "0.1.0"

_STARTED_AT = time.monotonic()


def create_app() -> FastAPI:
    app = FastAPI(title="AI 电商综合体本地 API", version=API_VERSION)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        # 工具数只做展示，读注册表失败不许影响 health 的 200。
        try:
            tools = len(load_tool_catalog().tools)
        except Exception:
            tools = 0
        return {
            "ok": True,
            "status": "ok",
            "service": SERVICE_NAME,
            "version": API_VERSION,
            "tools": tools,
            "pid": os.getpid(),
            "uptime_s": round(time.monotonic() - _STARTED_AT, 3),
        }

    @app.get("/api/tools")
    def tools() -> dict[str, Any]:
        catalog = load_tool_catalog()
        payload: dict[str, Any] = {
            "ok": catalog.error is None,
            "source": catalog.source,
            "count": len(catalog.tools),
            "tools": catalog.tools,
        }
        if catalog.error is not None:
            payload["error"] = catalog.error
        return payload

    return app


app = create_app()
