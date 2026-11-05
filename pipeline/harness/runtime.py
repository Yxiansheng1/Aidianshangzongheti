"""任务运行时：把"跑 → 停 → 批 → 续"管起来。

客户端只做三件事：交任务、看状态、点同意。所有状态在这里，不在界面里。

设计要点：
    · 一个任务 = 一个 thread_id（LangGraph 的 checkpoint 指针）
    · 跑在后台线程，接口立刻返回，界面轮询/推送都行
    · 停下时把审批拆成 PendingApproval，界面照着渲染按钮
    · 批准/驳回用 approval.build_decisions 拼 payload
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .approval import PendingApproval, parse_interrupt

RUNNING = "running"
WAITING = "waiting_approval"
DONE = "done"
FAILED = "failed"


@dataclass
class TaskState:
    id: str
    task: str
    thread_id: str
    status: str = RUNNING
    pending: list[PendingApproval] = field(default_factory=list)
    result: str = ""
    error: str = ""
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "thread_id": self.thread_id,
            "status": self.status,
            "pending": [p.to_dict() for p in self.pending],
            "result": self.result,
            "error": self.error,
            "elapsed_s": round(self.updated_at - self.started_at, 1),
        }


class TaskRunner:
    """持有 agent 与所有任务状态。

    agent_factory：无参调用，返回一个可 invoke 的对象（Deep Agents 编译后的图）。
    测试里可以塞假 agent，不需要模型。
    """

    def __init__(self, agent_factory: Callable[[], Any]):
        self._factory = agent_factory
        self._agent: Any | None = None
        self._lock = threading.Lock()
        self._tasks: dict[str, TaskState] = {}

    # ---------- 对外 ----------

    def start(self, task: str) -> TaskState:
        tid = uuid.uuid4().hex[:12]
        state = TaskState(id=tid, task=task, thread_id=f"task-{tid}")
        with self._lock:
            self._tasks[tid] = state
        threading.Thread(target=self._run, args=(state, task), daemon=True).start()
        return state

    def get(self, task_id: str) -> TaskState | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list(self) -> list[TaskState]:
        with self._lock:
            return sorted(self._tasks.values(), key=lambda s: s.started_at, reverse=True)

    def approve(self, task_id: str, decisions: dict[str, Any]) -> TaskState:
        state = self.get(task_id)
        if state is None:
            raise KeyError(f"没有这个任务：{task_id}")
        if state.status != WAITING:
            raise RuntimeError(f"任务当前是 {state.status}，没有待审批的动作")
        self._set(state, status=RUNNING, pending=[])
        threading.Thread(target=self._resume, args=(state, decisions), daemon=True).start()
        return state

    # ---------- 内部 ----------

    def _agent_instance(self) -> Any:
        if self._agent is None:
            self._agent = self._factory()
        return self._agent

    def _run(self, state: TaskState, task: str) -> None:
        try:
            from langchain_core.messages import HumanMessage

            agent = self._agent_instance()
            result = agent.invoke(
                {"messages": [HumanMessage(task)]},
                config={"configurable": {"thread_id": state.thread_id}},
            )
            self._absorb(state, result)
        except Exception as exc:  # noqa: BLE001
            self._set(state, status=FAILED, error=f"{type(exc).__name__}: {exc}"[:400])

    def _resume(self, state: TaskState, decisions: dict[str, Any]) -> None:
        try:
            from langgraph.types import Command

            agent = self._agent_instance()
            result = agent.invoke(
                Command(resume=decisions),
                config={"configurable": {"thread_id": state.thread_id}},
            )
            self._absorb(state, result)
        except Exception as exc:  # noqa: BLE001
            self._set(state, status=FAILED, error=f"{type(exc).__name__}: {exc}"[:400])

    def _absorb(self, state: TaskState, result: Any) -> None:
        """把一次 invoke 的结果落成任务状态：要么等审批，要么完成。"""
        interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
        if interrupts:
            pending: list[PendingApproval] = []
            for item in interrupts:
                pending.extend(parse_interrupt(item))
            self._set(state, status=WAITING, pending=pending)
            return

        text = _last_text(result)
        self._set(state, status=DONE, result=text, pending=[])

    def _set(self, state: TaskState, **changes: Any) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(state, key, value)
            state.updated_at = time.time()


def _last_text(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result)[:1000]
    messages = result.get("messages") or []
    if messages:
        content = getattr(messages[-1], "content", "")
        return str(content)[:1000]
    return str(result)[:1000]
