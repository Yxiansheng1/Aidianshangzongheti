"""把工具 + 技能 + 审批策略拼成一个可跑的 Deep Agents 智能体。

这一层只做装配，不写业务。业务在 pipeline/tools/，策略在 policy.py。

用法（还没接模型时也能构造，失败会给出人话错误）：

    from pipeline.harness import build_agent, AutonomyController, Autonomy
    agent = build_agent(registry, AutonomyController(Autonomy.STANDARD), model="openai:gpt-4o-mini")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .policy import Autonomy, AutonomyController, Risk
from .registry import ToolRegistry, to_langchain_tools

REPO = Path(__file__).resolve().parent.parent.parent

DEFAULT_SKILL_DIRS = (
    REPO / "pipeline" / "content" / "skills",   # 9 个平台写作规则
    REPO / "pipeline" / "content" / "modes",    # 3 个题材硬规则
)


@dataclass
class AgentConfig:
    model: Any = ""
    """模型名字符串（openai:xxx / ollama:xxx），或直接给一个 LangChain ChatModel 实例。"""
    system_prompt: str = ""
    skill_dirs: tuple[Path, ...] = field(default_factory=lambda: DEFAULT_SKILL_DIRS)
    memory_files: tuple[Path, ...] = ()
    name: str = "workbench"
    checkpointer: Any = None
    """None → 内存级 InMemorySaver（进程退出即丢）。要跨重启请传 SqliteSaver 等。"""


def _interrupt_on(registry: ToolRegistry, controller: AutonomyController) -> dict[str, Any]:
    """把自主度档位翻译成 Deep Agents 的 interrupt_on。

    规则和 policy.py 一致：
        不可逆  永远 True
        read    永远 False
        write   看档位（auto=False / standard=仅 critical / step=True）
    """
    mapping: dict[str, Any] = {}
    for spec in registry.all():
        if spec.risk is Risk.READ:
            mapping[spec.name] = False
            continue
        if spec.risk is Risk.IRREVERSIBLE:
            mapping[spec.name] = True
            continue
        level = controller.level_for(spec.name)
        if level is Autonomy.STEP:
            mapping[spec.name] = True
        elif level is Autonomy.AUTO:
            mapping[spec.name] = False
        else:
            mapping[spec.name] = bool(spec.critical)
    return mapping


def _skill_paths(dirs: tuple[Path, ...]) -> list[str]:
    return [str(d) for d in dirs if d.is_dir()]


def build_agent(registry: ToolRegistry, controller: AutonomyController, config: AgentConfig | None = None):
    """装配智能体。返回 LangGraph 编译后的图。

    需要模型。没配模型时抛 RuntimeError，并说清楚怎么配。
    """
    cfg = config or AgentConfig()
    if not cfg.model or (isinstance(cfg.model, str) and not cfg.model.strip()):
        raise RuntimeError(
            "没有配置模型。可以：\n"
            "  1) 设置环境变量（如 OPENAI_API_KEY）并用 model='openai:gpt-4o-mini'\n"
            "  2) 用本地 Ollama：model='ollama:qwen3'\n"
            "  3) 直接传一个 langchain ChatModel 实例"
        )

    try:
        from deepagents import create_deep_agent
    except ImportError as exc:  # noqa: BLE001
        raise RuntimeError(
            "没装 deepagents。装它：\n"
            r"  .venv\Scripts\python.exe -m pip install -e .[harness]"
        ) from exc

    from langchain_core.tools import BaseTool

    tools: list[BaseTool] = to_langchain_tools(registry)
    prompt = cfg.system_prompt or _default_prompt(registry, controller)

    # langgraph 1.2 起，根图不接受 checkpointer=True，必须给真实的 saver
    if cfg.checkpointer is None:
        from langgraph.checkpoint.memory import InMemorySaver

        saver: Any = InMemorySaver()
    else:
        saver = cfg.checkpointer

    return create_deep_agent(
        model=cfg.model,
        tools=tools,
        system_prompt=prompt,
        skills=_skill_paths(cfg.skill_dirs) or None,
        memory=[str(p) for p in cfg.memory_files if p.is_file()] or None,
        interrupt_on=_interrupt_on(registry, controller),
        checkpointer=saver,
        name=cfg.name,
    )


def _default_prompt(registry: ToolRegistry, controller: AutonomyController) -> str:
    lines = [
        "你在一个中文内容与电商的本地工作台里干活。",
        "先规划，再动手；每一步都要能说出依据。",
        "",
        "可用工具：",
    ]
    for s in registry.all():
        flag = "不可逆，必须审批" if s.risk is Risk.IRREVERSIBLE else s.risk.value
        lines.append(f"- {s.name}（{flag}）：{s.description}")
    lines += [
        "",
        "硬规则：",
        "- 发布类动作一定先停下来等人工确认，不要自己猜着发。",
        "- 正文里的每个数字都必须能在素材里找到出处；找不到就写“查不到”，不要补。",
        "- 平台格式按 skills 目录里的对应文件来，不要自己发明排版。",
        "",
        f"当前自主度：{controller.level.value}",
    ]
    return "\n".join(lines)
