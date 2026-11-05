"""任务运行时的测试：用假 agent，不调模型、不开浏览器。"""

import time

import pytest

from pipeline.harness.approval import build_decisions
from pipeline.harness.runtime import DONE, FAILED, RUNNING, WAITING, TaskRunner

SAMPLE_INTERRUPT = {
    "action_requests": [
        {"name": "publish_article", "args": {"title": "测试稿"}, "description": "需要审批"}
    ],
    "review_configs": [
        {"action_name": "publish_article", "allowed_decisions": ["approve", "reject"]}
    ],
}


class FakeInterrupt:
    def __init__(self, value, id="i1"):
        self.value = value
        self.id = id


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeAgent:
    """第一次 invoke 停在审批；收到 resume 后返回完成。"""

    def __init__(self):
        self.calls = []

    def invoke(self, payload, config=None):
        self.calls.append((payload, config))
        from langgraph.types import Command

        if isinstance(payload, Command):
            return {"messages": [FakeMessage("已发布完成")]}
        return {"__interrupt__": [FakeInterrupt(SAMPLE_INTERRUPT)]}


def wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_start_lands_in_waiting_approval():
    agent = FakeAgent()
    runner = TaskRunner(lambda: agent)

    state = runner.start("请发布《测试稿》")
    # 不能断言此刻一定是 running：假 agent 瞬间就跑到审批点，状态可能已经变了
    assert state.status in {RUNNING, WAITING}

    assert wait_for(lambda: runner.get(state.id).status == WAITING)
    waiting = runner.get(state.id)
    assert len(waiting.pending) == 1
    assert waiting.pending[0].tool == "publish_article"
    assert waiting.pending[0].args == {"title": "测试稿"}
    assert waiting.pending[0].index == 0
    # thread_id 要写进 config，否则 checkpoint 对不上
    _, config = agent.calls[0]
    assert config["configurable"]["thread_id"] == waiting.thread_id


def test_approve_resumes_and_finishes():
    agent = FakeAgent()
    runner = TaskRunner(lambda: agent)
    state = runner.start("发布")
    assert wait_for(lambda: runner.get(state.id).status == WAITING)

    runner.approve(state.id, build_decisions([(0, "approve", "")]))
    assert wait_for(lambda: runner.get(state.id).status == DONE)
    done = runner.get(state.id)
    assert done.result == "已发布完成"
    assert done.pending == []


def test_approve_requires_waiting_state():
    agent = FakeAgent()
    runner = TaskRunner(lambda: agent)
    state = runner.start("随便")
    assert wait_for(lambda: runner.get(state.id).status == WAITING)

    runner.approve(state.id, build_decisions([(0, "approve", "")]))
    assert wait_for(lambda: runner.get(state.id).status == DONE)

    with pytest.raises(RuntimeError):
        runner.approve(state.id, build_decisions([(0, "approve", "")]))


def test_unknown_task_raises():
    runner = TaskRunner(FakeAgent)
    with pytest.raises(KeyError):
        runner.approve("nope", {})


def test_agent_error_becomes_failed_state():
    class Boom(FakeAgent):
        def invoke(self, payload, config=None):
            raise RuntimeError("模型炸了")

    runner = TaskRunner(Boom)
    state = runner.start("x")
    assert wait_for(lambda: runner.get(state.id).status == FAILED)
    assert "模型炸了" in runner.get(state.id).error


def test_list_is_newest_first():
    runner = TaskRunner(FakeAgent)
    a = runner.start("第一个")
    time.sleep(0.01)
    b = runner.start("第二个")
    ids = [s.id for s in runner.list()]
    assert ids.index(b.id) < ids.index(a.id)


def test_to_dict_is_json_friendly():
    runner = TaskRunner(FakeAgent)
    state = runner.start("x")
    assert wait_for(lambda: runner.get(state.id).status == WAITING)
    data = runner.get(state.id).to_dict()
    assert set(data) >= {"id", "status", "pending", "result", "elapsed_s"}
    assert isinstance(data["pending"], list)
    assert data["pending"][0]["tool"] == "publish_article"
