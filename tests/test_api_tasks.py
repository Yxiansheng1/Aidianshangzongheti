"""任务接口的测试：用假 agent，不调模型。"""

import time

from fastapi.testclient import TestClient

from pipeline.api.app import create_app
from pipeline.harness.runtime import TaskRunner

SAMPLE = {
    "action_requests": [
        {"name": "publish_article", "args": {"title": "测试稿"}, "description": "需要审批"}
    ],
    "review_configs": [{"action_name": "publish_article", "allowed_decisions": ["approve", "reject"]}],
}


class FakeInterrupt:
    value = SAMPLE
    id = "i1"


class Msg:
    def __init__(self, content):
        self.content = content


class FakeAgent:
    def invoke(self, payload, config=None):
        from langgraph.types import Command

        if isinstance(payload, Command):
            return {"messages": [Msg("已发布完成")]}
        return {"__interrupt__": [FakeInterrupt()]}


def make_client() -> TestClient:
    return TestClient(create_app(runner_factory=lambda: TaskRunner(FakeAgent)))


def wait_status(client, task_id, want, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/tasks/{task_id}").json()
        if data["status"] == want:
            return data
        time.sleep(0.02)
    raise AssertionError(f"{timeout}s 内没到 {want}，当前 {data}")


def test_task_lifecycle():
    client = make_client()
    started = client.post("/api/tasks", json={"task": "请发布《测试稿》"})
    assert started.status_code == 200
    task_id = started.json()["id"]

    waiting = wait_status(client, task_id, "waiting_approval")
    assert waiting["pending"][0]["tool"] == "publish_article"
    assert waiting["pending"][0]["args"] == {"title": "测试稿"}

    approved = client.post(f"/api/tasks/{task_id}/approve", json={"approve_all": True})
    assert approved.status_code == 200
    assert wait_status(client, task_id, "done")["result"] == "已发布完成"


def test_empty_task_rejected():
    client = make_client()
    assert client.post("/api/tasks", json={"task": "  "}).status_code == 400


def test_unknown_task_404():
    client = make_client()
    assert client.get("/api/tasks/nope").status_code == 404
    assert client.post("/api/tasks/nope/approve", json={}).status_code == 404


def test_approve_when_not_waiting_conflicts():
    client = make_client()
    task_id = client.post("/api/tasks", json={"task": "发布"}).json()["id"]
    wait_status(client, task_id, "waiting_approval")
    client.post(f"/api/tasks/{task_id}/approve", json={"approve_all": True})
    wait_status(client, task_id, "done")
    again = client.post(f"/api/tasks/{task_id}/approve", json={"approve_all": True})
    assert again.status_code == 409


def test_decisions_with_string_keys_are_coerced():
    """JSON 的键一定是字符串，接口要把它转回序号。"""
    client = make_client()
    task_id = client.post("/api/tasks", json={"task": "发布"}).json()["id"]
    wait_status(client, task_id, "waiting_approval")
    r = client.post(f"/api/tasks/{task_id}/approve", json={"decisions": {"0": {"type": "approve"}}})
    assert r.status_code == 200
    assert wait_status(client, task_id, "done")["status"] == "done"


def test_list_tasks():
    client = make_client()
    client.post("/api/tasks", json={"task": "a"})
    client.post("/api/tasks", json={"task": "b"})
    body = client.get("/api/tasks").json()
    assert body["ok"] is True
    assert len(body["tasks"]) == 2
