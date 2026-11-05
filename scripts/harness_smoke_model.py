"""接真模型验证：工具调用会停在审批闸门上，批准后才继续。

    .venv\\Scripts\\python.exe scripts\\harness_smoke_model.py

工具都是假的，不做任何真实发布。
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.harness.agent import AgentConfig, build_agent
from pipeline.harness.policy import Autonomy, AutonomyController, Risk
from pipeline.harness.registry import ToolRegistry

ROOT = Path(__file__).resolve().parent.parent


def load_model():
    cfg = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))["model"]
    from langchain_openai import ChatOpenAI

    print(f"模型：{cfg['text_model']} @ {cfg['base_url']}")
    return ChatOpenAI(
        model=cfg["text_model"],
        base_url=cfg["base_url"],
        api_key=cfg["api_key"],
        temperature=0,
        timeout=90,
        max_retries=1,
    )


def build_registry() -> ToolRegistry:
    reg = ToolRegistry()

    @reg.tool("check_status", "查当前草稿状态，只读", Risk.READ)
    def check_status() -> str:
        return "草稿已写好：标题《测试稿》，正文 800 字，等待发布。"

    @reg.tool("publish_article", "把文章发布出去（不可逆）", Risk.IRREVERSIBLE)
    def publish_article(title: str = "") -> str:
        return f"已发布：{title}"

    return reg


def main() -> None:
    from langchain_core.messages import HumanMessage
    from langgraph.types import Command

    reg = build_registry()
    controller = AutonomyController(Autonomy.STANDARD)
    agent = build_agent(
        reg,
        controller,
        AgentConfig(
            model=load_model(),
            system_prompt=(
                "你是内容工作台里的助手。用户让你发布时，先调 check_status 看状态，"
                "然后必须调 publish_article，参数 title 用《测试稿》。不要只说不做。"
            ),
            name="smoke",
        ),
    )

    config = {"configurable": {"thread_id": "smoke-1"}}
    print("\n--- 第一次调用（应停在 publish_article 前）---")
    result = agent.invoke({"messages": [HumanMessage("请现在发布《测试稿》。")]}, config=config)

    interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
    if not interrupts:
        print("⚠ 没有停下来，闸门没生效")
        print(str(result)[:400])
        return

    first = interrupts[0]
    print("interrupt id:", getattr(first, "id", None))
    print("审批载荷：", str(getattr(first, "value", first))[:400])

    print("\n--- 批准后继续（试几种恢复格式）---")
    iid = getattr(first, "id", None)
    candidates = [
        ("decisions 用序号 0", {"decisions": {0: {"type": "approve"}}}),
        ("decisions 序号 + message", {"decisions": {0: {"type": "approve", "message": "同意发布"}}}),
        ("decisions + id", {"decisions": {iid: {"type": "approve"}}}),
    ]
    for label, payload in candidates:
        try:
            final = agent.invoke(
                Command(resume=payload), config={"configurable": {"thread_id": "smoke-1"}}
            )
            msgs = final.get("messages") if isinstance(final, dict) else None
            tail = msgs[-1].content if msgs else str(final)[:200]
            print(f"✅ 恢复格式「{label}」有效")
            print("最终回复：", str(tail)[:200])
            return
        except Exception as exc:  # noqa: BLE001
            print(f"✗ 「{label}」失败：{type(exc).__name__}: {str(exc)[:140]}")


if __name__ == "__main__":
    main()
