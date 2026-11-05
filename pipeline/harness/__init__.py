"""harness：智能体运行时。

层次：
    policy.py    自主度策略（三档 + 自动降档），纯逻辑，可单测
    registry.py  工具注册表（名称/描述/风险等级），与框架解耦
    agent.py     装配 Deep Agents（工具 + 技能 + 审批闸门）
"""

from .agent import AgentConfig, build_agent
from .policy import Autonomy, AutonomyController, Risk
from .registry import ApprovalRequired, ToolRegistry, ToolSpec

__all__ = [
    "AgentConfig",
    "ApprovalRequired",
    "Autonomy",
    "AutonomyController",
    "Risk",
    "ToolRegistry",
    "ToolSpec",
    "build_agent",
]
