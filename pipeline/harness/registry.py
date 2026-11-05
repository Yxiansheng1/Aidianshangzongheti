"""工具注册表：把业务函数登记成"带风险等级的工具"。

上层（harness / 界面 / CLI）只跟这里打交道，不直接 import 业务函数。
每条工具声明三件事：叫什么、干什么、风险多高。审批由 policy 决定。

为什么单独一层：
    · 换 harness（Deep Agents / Mastra / Dify）时，工具清单不用重写
    · 界面能直接列出"这个 AI 会做哪些事、哪些要审批"
    · 测试不需要模型，也能验证注册和门禁
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .policy import AutonomyController, Risk


class ApprovalRequired(RuntimeError):
    """这一步需要人来点头。携带审批所需的上下文。

    注意：不要用 self.args 存参数——Exception 自带 args 属性，会被覆盖。
    """

    def __init__(self, tool: str, tool_args: dict[str, Any], risk: Risk):
        self.tool = tool
        self.tool_args = tool_args
        self.risk = risk
        super().__init__(f"{tool} 需要审批（风险 {risk.value}）")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    risk: Risk
    func: Callable[..., Any]
    critical: bool = False
    """写类工具里"关键的那几步"，standard 档下只有它会停。"""
    input_schema: type | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"工具重名：{spec.name}")
        self._specs[spec.name] = spec

    def tool(
        self,
        name: str,
        description: str,
        risk: Risk,
        *,
        critical: bool = False,
        input_schema: type | None = None,
        tags: tuple[str, ...] = (),
    ):
        """装饰器写法：@registry.tool("fetch_source", "...", Risk.READ)"""

        def deco(fn: Callable[..., Any]):
            self.register(
                ToolSpec(
                    name=name,
                    description=description,
                    risk=risk,
                    func=fn,
                    critical=critical,
                    input_schema=input_schema,
                    tags=tags,
                )
            )
            return fn

        return deco

    def get(self, name: str) -> ToolSpec:
        if name not in self._specs:
            raise KeyError(f"没有这个工具：{name}；已注册：{sorted(self._specs)}")
        return self._specs[name]

    def all(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def describe(self) -> list[dict[str, Any]]:
        """给界面/文档用的清单。"""
        return [
            {
                "name": s.name,
                "description": s.description,
                "risk": s.risk.value,
                "critical": s.critical,
                "tags": list(s.tags),
            }
            for s in self._specs.values()
        ]

    def call(self, name: str, controller: AutonomyController, **kwargs: Any) -> Any:
        """执行一次工具调用：先过门禁，再执行，最后记成败。"""
        spec = self.get(name)
        if controller.needs_approval(spec.name, spec.risk, critical=spec.critical):
            raise ApprovalRequired(spec.name, kwargs, spec.risk)
        try:
            result = spec.func(**kwargs)
        except Exception:
            controller.record(spec.name, ok=False)
            raise
        controller.record(spec.name, ok=True)
        return result


def to_langchain_tools(registry: ToolRegistry) -> list[Any]:
    """转成 langchain 工具，交给 Deep Agents。

    interrupt_on 在 agent 层配置（见 agent.py），这里只负责把函数包成工具。
    """
    from langchain_core.tools import StructuredTool

    out = []
    for spec in registry.all():
        kwargs: dict[str, Any] = {
            "name": spec.name,
            "description": spec.description,
            "func": spec.func,
        }
        if spec.input_schema is not None:
            kwargs["args_schema"] = spec.input_schema
        out.append(StructuredTool.from_function(**kwargs))
    return out
