"""审批解析/提交的测试。纯逻辑，不需要模型。"""

import pytest

from pipeline.harness.approval import (
    PendingApproval,
    approve_all,
    build_decisions,
    parse_interrupt,
    reject_all,
)

# 真实跑出来的 interrupt 载荷（deepagents 0.7.32）
SAMPLE = {
    "action_requests": [
        {
            "name": "publish_article",
            "args": {"title": "测试稿"},
            "description": "Tool execution requires approval\n\nTool: publish_article",
        }
    ],
    "review_configs": [
        {
            "action_name": "publish_article",
            "allowed_decisions": ["approve", "edit", "reject", "respond"],
        }
    ],
}


class FakeInterrupt:
    def __init__(self, value, id="abc"):
        self.value = value
        self.id = id


def test_parse_single_action():
    items = parse_interrupt(FakeInterrupt(SAMPLE))
    assert len(items) == 1
    item = items[0]
    assert item.index == 0
    assert item.tool == "publish_article"
    assert item.args == {"title": "测试稿"}
    assert item.allowed == ["approve", "edit", "reject", "respond"]


def test_parse_multiple_actions_keeps_order():
    value = {
        "action_requests": [
            {"name": "a", "args": {}, "description": ""},
            {"name": "b", "args": {"x": 1}, "description": ""},
        ],
        "review_configs": [],
    }
    items = parse_interrupt(FakeInterrupt(value))
    assert [i.tool for i in items] == ["a", "b"]
    assert [i.index for i in items] == [0, 1]
    assert items[1].allowed == ["approve", "reject"]  # 没有配置时给默认值


def test_parse_accepts_raw_dict():
    """界面上拿到的可能已经是 dict，不是 Interrupt 对象。"""
    items = parse_interrupt(SAMPLE)
    assert items[0].tool == "publish_article"


def test_build_decisions_uses_index_not_id():
    payload = build_decisions([(0, "approve", "")])
    assert payload == {"decisions": {0: {"type": "approve"}}}


def test_build_decisions_carries_message():
    payload = build_decisions([(0, "reject", "标题要改")])
    assert payload["decisions"][0] == {"type": "reject", "message": "标题要改"}


def test_build_decisions_rejects_unknown_type():
    with pytest.raises(ValueError):
        build_decisions([(0, "maybe", "")])


def test_approve_all_and_reject_all():
    pending = [
        PendingApproval(index=0, tool="a"),
        PendingApproval(index=1, tool="b"),
    ]
    assert approve_all(pending)["decisions"][1]["type"] == "approve"
    assert reject_all(pending, "不要")["decisions"][0]["message"] == "不要"
