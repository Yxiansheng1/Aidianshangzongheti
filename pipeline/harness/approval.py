"""审批的解析与提交：把 Deep Agents 的 interrupt 变成界面能用的结构。

实测出来的格式（deepagents 0.7.32 / langgraph 1.2.20）：

    interrupt.value = {
      "action_requests": [
         {"name": "publish_article", "args": {...}, "description": "Tool execution requires approval..."}
      ],
      "review_configs": [
         {"action_name": "publish_article",
          "allowed_decisions": ["approve", "edit", "reject", "respond"]}
      ],
    }

    恢复：Command(resume={"decisions": {0: {"type": "approve"}}})
          —— 键是 action_requests 的**序号**，不是 interrupt id。踩过坑。

这层把上面的细节挡住，界面只需要：拿列表 → 用户点 → build_decisions()。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PendingApproval:
    index: int
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    allowed: list[str] = field(default_factory=lambda: ["approve", "reject"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "tool": self.tool,
            "args": self.args,
            "description": self.description,
            "allowed": self.allowed,
        }


def parse_interrupt(interrupt: Any) -> list[PendingApproval]:
    """把一个 interrupt 拆成"每一条待审批动作"。"""
    value = getattr(interrupt, "value", interrupt) or {}
    requests = value.get("action_requests") or []
    configs = {c.get("action_name"): c for c in (value.get("review_configs") or [])}

    out: list[PendingApproval] = []
    for i, req in enumerate(requests):
        name = req.get("name", "")
        cfg = configs.get(name) or {}
        out.append(
            PendingApproval(
                index=i,
                tool=name,
                args=dict(req.get("args") or {}),
                description=req.get("description", ""),
                allowed=list(cfg.get("allowed_decisions") or ["approve", "reject"]),
            )
        )
    return out


def build_decisions(choices: list[tuple[int, str, str]]) -> dict[str, Any]:
    """把界面上的选择拼成 Command(resume=...) 需要的 payload。

    choices: [(序号, 决策类型, 备注)]
        决策类型：approve / reject / edit / respond
    """
    decisions: dict[int, dict[str, Any]] = {}
    for index, kind, message in choices:
        if kind not in {"approve", "reject", "edit", "respond"}:
            raise ValueError(f"不认识的决策类型：{kind}")
        item: dict[str, Any] = {"type": kind}
        if message:
            item["message"] = message
        decisions[index] = item
    return {"decisions": decisions}


def approve_all(pending: list[PendingApproval], message: str = "") -> dict[str, Any]:
    """全部批准。界面上的"一键同意"。"""
    return build_decisions([(p.index, "approve", message) for p in pending])


def reject_all(pending: list[PendingApproval], reason: str = "") -> dict[str, Any]:
    return build_decisions([(p.index, "reject", reason) for p in pending])
