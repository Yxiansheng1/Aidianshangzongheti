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


def create_app(runner_factory=None) -> FastAPI:
    """runner_factory：返回 TaskRunner 的工厂。

    默认实现第一次用到时才装配真 agent（要模型、要工具层）；
    没配置好就回 503 并说清楚原因，而不是让整个服务起不来。
    测试传入假工厂即可，不需要模型。
    """
    app = FastAPI(title="AI 电商综合体本地 API", version=API_VERSION)
    app.state.runner = None
    app.state.runner_factory = runner_factory

    def get_runner():
        if app.state.runner is not None:
            return app.state.runner
        if app.state.runner_factory is not None:
            app.state.runner = app.state.runner_factory()
            return app.state.runner
        # 默认：真 agent
        from fastapi import HTTPException

        try:
            app.state.runner = _build_default_runner()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"任务运行时没就绪：{exc}") from exc
        return app.state.runner


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

    # ---------- 任务：跑 → 停 → 批 → 续 ----------

    @app.post("/api/tasks")
    def start_task(body: dict[str, Any]) -> dict[str, Any]:
        from fastapi import HTTPException

        task = str((body or {}).get("task") or "").strip()
        if not task:
            raise HTTPException(status_code=400, detail="task 不能为空")
        state = get_runner().start(task)
        return state.to_dict()

    @app.get("/api/tasks")
    def list_tasks() -> dict[str, Any]:
        runner = get_runner()
        return {"ok": True, "tasks": [s.to_dict() for s in runner.list()]}

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        from fastapi import HTTPException

        state = get_runner().get(task_id)
        if state is None:
            raise HTTPException(status_code=404, detail="没有这个任务")
        return state.to_dict()

    @app.post("/api/tasks/{task_id}/approve")
    def approve_task(task_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """两种用法：
        {"decisions": {0: {"type": "approve"}}}      精确控制
        {"approve_all": true}                        一键同意全部待批
        """
        from fastapi import HTTPException

        from ..harness.approval import approve_all, reject_all

        runner = get_runner()
        state = runner.get(task_id)
        if state is None:
            raise HTTPException(status_code=404, detail="没有这个任务")
        if state.status != "waiting_approval":
            raise HTTPException(status_code=409, detail=f"任务当前是 {state.status}，没有待审批动作")

        body = body or {}
        if body.get("decisions"):
            decisions = body["decisions"]
            # JSON 的键是字符串，这里转回序号
            if isinstance(decisions, dict):
                decisions = {int(k): v for k, v in decisions.items()}
                decisions = {"decisions": decisions}
        elif body.get("reject_all"):
            decisions = reject_all(state.pending, str(body.get("message") or ""))
        else:
            decisions = approve_all(state.pending, str(body.get("message") or ""))

        try:
            runner.approve(task_id, decisions)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return runner.get(task_id).to_dict()

    return app


def _build_default_runner():
    """默认任务运行时：真模型 + L2 的工具层 + 我们的自主度策略。"""
    import tomllib
    from pathlib import Path

    from ..harness.agent import AgentConfig, build_agent
    from ..harness.policy import Autonomy, AutonomyController
    from ..harness.runtime import TaskRunner

    root = Path(__file__).resolve().parent.parent.parent
    cfg = tomllib.loads((root / "config.toml").read_text(encoding="utf-8"))["model"]
    if not cfg.get("base_url") or not cfg.get("text_model"):
        raise RuntimeError("config.toml 里没有可用的模型配置")

    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=cfg["text_model"],
        base_url=cfg["base_url"],
        api_key=cfg.get("api_key", ""),
        temperature=0,
        timeout=90,
        max_retries=1,
    )

    def factory():
        from pipeline.tools import build_registry

        registry = build_registry()
        return build_agent(
            registry,
            AutonomyController(Autonomy.STANDARD),
            AgentConfig(model=llm, name="workbench"),
        )

    return TaskRunner(factory)


app = create_app()
