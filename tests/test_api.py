"""L3 的测试：不需要模型、不需要 Electron、不需要 L2 真的写完。

两个关键点：
    · /api/tools 透出的字段与风险等级正确
    · L2 缺失时 /api/health 照样 200，/api/tools 明确报缺而不是 500
"""

import sys
import types

import pytest
from fastapi.testclient import TestClient

from pipeline.api.__main__ import DEFAULT_HOST, DEFAULT_PORT
from pipeline.api.app import create_app
from pipeline.harness.policy import Risk
from pipeline.harness.registry import ToolRegistry


def make_registry() -> ToolRegistry:
    reg = ToolRegistry()

    @reg.tool("fetch_source", "抓一篇文章的正文", Risk.READ)
    def fetch_source(url: str = "") -> dict:
        return {"url": url}

    @reg.tool("publish", "发布到平台", Risk.IRREVERSIBLE, critical=True, tags=("slow",))
    def publish(post_id: str = "p1") -> dict:
        return {"published": post_id}

    return reg


def test_health_ok():
    client = TestClient(create_app())
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "aidianshang-api"
    assert body["pid"] > 0


def test_defaults_are_local_only():
    assert DEFAULT_HOST == "127.0.0.1"
    assert DEFAULT_PORT == 8765


def test_tools_lists_l2_registry(monkeypatch):
    fake = types.ModuleType("pipeline.tools")
    fake.build_registry = make_registry  # 工厂入口
    monkeypatch.setitem(sys.modules, "pipeline.tools", fake)

    r = TestClient(create_app()).get("/api/tools")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["source"] == "pipeline.tools.build_registry()"
    assert body["count"] == 2

    by_name = {t["name"]: t for t in body["tools"]}
    assert by_name["fetch_source"]["risk"] == "read"
    assert by_name["fetch_source"]["critical"] is False
    assert by_name["publish"]["risk"] == "irreversible"
    assert by_name["publish"]["critical"] is True
    assert by_name["publish"]["tags"] == ["slow"]


@pytest.mark.parametrize("attr", ["REGISTRY", "registry"])
def test_tools_accepts_module_level_registry(monkeypatch, attr):
    fake = types.ModuleType("pipeline.tools")
    setattr(fake, attr, make_registry())
    monkeypatch.setitem(sys.modules, "pipeline.tools", fake)

    body = TestClient(create_app()).get("/api/tools").json()
    assert body["ok"] is True
    assert body["source"] == f"pipeline.tools.{attr}"


def test_tools_missing_layer_reports_reason(monkeypatch):
    monkeypatch.setattr("pipeline.api.catalog.TOOLS_MODULE", "pipeline.absent_tools_for_test")

    r = TestClient(create_app()).get("/api/tools")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["count"] == 0
    assert body["tools"] == []
    assert "pipeline.absent_tools_for_test" in body["error"]


def test_health_survives_broken_tools(monkeypatch):
    # 导入工具层会炸，health 也不许跟着炸
    monkeypatch.setitem(sys.modules, "pipeline.tools", None)

    client = TestClient(create_app())
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/tools").json()["ok"] is False


def test_module_entrypoint_parses_port(monkeypatch):
    captured = {}

    def fake_run(app, **kwargs):
        captured.update(kwargs)
        captured["app"] = app

    monkeypatch.setattr("pipeline.api.__main__.uvicorn.run", fake_run)

    from pipeline.api.__main__ import main

    assert main([]) == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8765
    assert callable(getattr(captured["app"], "openapi", None))
