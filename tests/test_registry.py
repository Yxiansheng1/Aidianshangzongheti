"""工具注册表 + 门禁的测试。不需要模型。"""

import pytest

from pipeline.harness.policy import Autonomy, AutonomyController, Risk
from pipeline.harness.registry import ApprovalRequired, ToolRegistry


def make_registry() -> ToolRegistry:
    reg = ToolRegistry()

    @reg.tool("fetch_source", "抓一篇文章的正文", Risk.READ)
    def fetch_source(url: str = "") -> dict:
        return {"url": url, "text": "hello"}

    @reg.tool("write_draft", "按平台规则写稿", Risk.WRITE, critical=True)
    def write_draft(topic: str = "") -> dict:
        return {"title": topic, "body": "x" * 30}

    @reg.tool("publish", "发布到平台", Risk.IRREVERSIBLE)
    def publish(post_id: str = "p1") -> dict:
        return {"published": post_id}

    return reg


def test_register_and_describe():
    reg = make_registry()
    names = [d["name"] for d in reg.describe()]
    assert names == ["fetch_source", "write_draft", "publish"]
    assert reg.get("publish").risk is Risk.IRREVERSIBLE


def test_duplicate_name_rejected():
    reg = make_registry()
    with pytest.raises(ValueError):
        reg.register(reg.get("publish"))


def test_irreversible_raises_approval_required():
    reg = make_registry()
    c = AutonomyController(Autonomy.AUTO)
    with pytest.raises(ApprovalRequired) as exc:
        reg.call("publish", c, post_id="p9")
    assert exc.value.tool == "publish"
    assert exc.value.tool_args == {"post_id": "p9"}


def test_read_tool_runs_without_approval():
    reg = make_registry()
    c = AutonomyController(Autonomy.STEP)
    assert reg.call("fetch_source", c, url="http://x")["text"] == "hello"


def test_standard_stops_critical_write():
    reg = make_registry()
    c = AutonomyController(Autonomy.STANDARD)
    with pytest.raises(ApprovalRequired):
        reg.call("write_draft", c, topic="t")


def test_failure_is_recorded_and_downgrades():
    reg = ToolRegistry()

    @reg.tool("flaky", "总失败的工具", Risk.WRITE)
    def flaky() -> None:
        raise RuntimeError("boom")

    c = AutonomyController(Autonomy.AUTO)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            reg.call("flaky", c)
    assert c.level_for("flaky") is Autonomy.STANDARD
