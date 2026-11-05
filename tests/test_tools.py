"""工具层测试：不联网、不开浏览器、不调模型。

外部依赖全部在边界上打桩：
    · 抓原文 → 换掉 article.fetch
    · 写稿   → 换掉 content.rewrite.rewrite
    · 出图   → 换掉 content.visual.plan / render
    · 填稿/发布 → 换掉 subprocess.run，只验证交给 CLI 的命令
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.article import ArticleError
from pipeline.harness.policy import Autonomy, AutonomyController, Risk
from pipeline.harness.registry import ApprovalRequired
from pipeline.tools import TOOL_NAMES, build_registry
from pipeline.tools import drafts, editor, images, publisher, sources


@pytest.fixture()
def reg():
    return build_registry()


def fake_completed(argv: list[str], returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")


# ---------- 注册与风险等级 ----------


def test_registers_exactly_five_tools_in_order(reg):
    assert [spec.name for spec in reg.all()] == list(TOOL_NAMES)


def test_risk_levels_and_critical_flags(reg):
    by_name = {spec.name: spec for spec in reg.all()}

    assert by_name["fetch_source"].risk is Risk.READ
    assert by_name["fetch_source"].critical is False

    assert by_name["write_draft"].risk is Risk.WRITE
    assert by_name["write_draft"].critical is False

    assert by_name["make_image"].risk is Risk.WRITE
    assert by_name["make_image"].critical is False

    assert by_name["fill_editor"].risk is Risk.WRITE
    assert by_name["fill_editor"].critical is True

    assert by_name["publish"].risk is Risk.IRREVERSIBLE
    assert by_name["publish"].critical is True


def test_describe_exposes_risk_and_critical(reg):
    rows = {row["name"]: row for row in reg.describe()}

    assert rows["fetch_source"]["risk"] == "read"
    assert rows["write_draft"]["risk"] == "write"
    assert rows["make_image"]["risk"] == "write"
    assert rows["fill_editor"]["risk"] == "write"
    assert rows["publish"]["risk"] == "irreversible"

    assert rows["fill_editor"]["critical"] is True
    assert rows["publish"]["critical"] is True
    assert rows["fetch_source"]["critical"] is False


# ---------- 抓原文（读，不审批） ----------


def test_fetch_source_runs_without_approval_even_in_step(reg, monkeypatch):
    def fake_fetch(url, *, proxy=None, timeout=25):
        return SimpleNamespace(
            url=url,
            ok=True,
            title="一篇原文",
            text="正文" * 120,
            chars=240,
            images=["https://example.com/a.png"],
            note="",
        )

    monkeypatch.setattr(sources, "fetch_article", fake_fetch)

    c = AutonomyController(Autonomy.STEP)
    result = reg.call("fetch_source", c, url="https://example.com/a")

    assert result["ok"] is True
    assert result["chars"] == 240
    assert result["images"] == ["https://example.com/a.png"]
    assert c.stats("fetch_source").calls == 1


def test_fetch_source_rejects_non_http_url():
    with pytest.raises(ArticleError):
        sources.fetch_source("ftp://example.com/a")


# ---------- 写稿（写，非 critical） ----------


def test_write_draft_passes_source_text_and_marks_ok(monkeypatch):
    seen: dict = {}

    def fake_rewrite(topic, source_text, cfg, *, platform, mode, extra):
        seen.update(
            topic=topic,
            source_text=source_text,
            platform=platform,
            mode=mode,
            extra=extra,
        )
        return {
            "platform": platform,
            "topic": topic,
            "title": "标题",
            "body": "正文" * 60,
            "tags": ["标签"],
            "gaps": [],
            "length": 120,
        }

    monkeypatch.setattr(drafts, "rewrite", fake_rewrite)

    reg = build_registry()
    result = reg.call(
        "write_draft",
        AutonomyController(Autonomy.STANDARD),
        topic="一个主题",
        source_text="抓到的原文",
        platform="头条",
        mode="政策解读",
    )

    assert result["ok"] is True
    assert result["title"] == "标题"
    assert seen == {
        "topic": "一个主题",
        "source_text": "抓到的原文",
        "platform": "头条",
        "mode": "政策解读",
        "extra": "",
    }


def test_write_draft_stops_in_step(reg):
    with pytest.raises(ApprovalRequired):
        reg.call("write_draft", AutonomyController(Autonomy.STEP), topic="一个主题")


# ---------- 出图（写，非 critical） ----------


def test_make_image_plans_and_renders(reg, monkeypatch, tmp_path):
    scenes = [{"anchor": "正文原话", "prompt": "a desk with papers"}]
    rendered = [tmp_path / "img-1.png"]
    rendered[0].write_text("png", encoding="utf-8")

    monkeypatch.setattr(images.visual, "plan", lambda *a, **k: scenes)
    monkeypatch.setattr(
        images.visual,
        "render",
        lambda scenes_arg, cfg, folder, prefix="img": rendered,
    )

    result = reg.call(
        "make_image",
        AutonomyController(Autonomy.AUTO),
        title="标题",
        body="正文里有这句原话",
        out_dir=str(tmp_path),
        count=1,
    )

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["files"] == [str(rendered[0])]
    assert result["dir"] == str(tmp_path)


def test_make_image_rejects_empty_text():
    with pytest.raises(ValueError):
        images.make_image("", "正文")


def test_make_image_rejects_out_of_range_count():
    with pytest.raises(ValueError):
        images.make_image("标题", "正文", count=9)


# ---------- 填稿（写 + critical） ----------


def test_fill_editor_stops_at_standard(reg):
    with pytest.raises(ApprovalRequired) as exc:
        reg.call(
            "fill_editor",
            AutonomyController(Autonomy.STANDARD),
            draft_path="不存在的草稿.json",
        )

    assert exc.value.risk is Risk.WRITE
    assert exc.value.tool_args == {"draft_path": "不存在的草稿.json"}


def test_fill_editor_calls_headline_cli(reg, monkeypatch):
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return fake_completed(argv, stdout="[填稿] 标题已填\n")

    monkeypatch.setattr("pipeline.tools._common.subprocess.run", fake_run)

    result = reg.call(
        "fill_editor",
        AutonomyController(Autonomy.AUTO),
        draft={
            "title": "标题",
            "body": "正文",
            "images": ["D:/tmp/a.png"],
            "tags": ["话题"],
            "url": "https://example.com/a",
        },
    )

    argv = captured["argv"]
    assert argv[1:4] == ["-m", "pipeline.content.headline", "fill"]
    assert argv[argv.index("--draft") + 1] == result["draft_path"]
    assert argv[argv.index("--account") + 1] == "main"
    assert result["ok"] is True

    draft_file = Path(result["draft_path"])
    assert draft_file.is_file()
    payload = json.loads(draft_file.read_text(encoding="utf-8"))
    assert payload["title"] == "标题"
    assert payload["body"] == "正文"
    assert payload["tags"] == ["话题"]


def test_fill_editor_rejects_draft_without_body():
    with pytest.raises(ValueError):
        editor.fill_editor(draft={"title": "只有标题", "body": ""})


def test_fill_editor_reports_cli_failure(reg, monkeypatch):
    def fake_run(argv, **kwargs):
        return fake_completed(argv, returncode=2, stdout="草稿缺标题或正文")

    monkeypatch.setattr("pipeline.tools._common.subprocess.run", fake_run)

    result = reg.call(
        "fill_editor",
        AutonomyController(Autonomy.AUTO),
        draft={"title": "标题", "body": "正文"},
    )

    assert result["ok"] is False
    assert result["returncode"] == 2
    assert "草稿缺标题" in result["output"]


# ---------- 发布（不可逆，永远停） ----------


def test_publish_always_stops_even_in_auto(reg):
    c = AutonomyController(Autonomy.AUTO)
    with pytest.raises(ApprovalRequired) as exc:
        reg.call("publish", c, draft_path="草稿.json")

    assert exc.value.risk is Risk.IRREVERSIBLE
    assert exc.value.tool_args == {"draft_path": "草稿.json"}
    assert c.stats("publish").calls == 0


def test_publish_calls_existing_cli_with_confirm(monkeypatch, tmp_path):
    draft = tmp_path / "draft.json"
    draft.write_text(
        json.dumps({"title": "标题", "body": "正文"}, ensure_ascii=False),
        encoding="utf-8",
    )
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return fake_completed(argv, stdout="[结果] 已发布\n")

    monkeypatch.setattr("pipeline.tools._common.subprocess.run", fake_run)

    result = publisher.publish(draft_path=str(draft), account="second")

    argv = captured["argv"]
    assert argv[1].endswith("publish_toutiao.py")
    assert argv[argv.index("--draft") + 1] == str(draft)
    assert argv[argv.index("--account") + 1] == "second"
    assert "--confirm" in argv
    assert result["ok"] is True
    assert result["draft_path"] == str(draft)


def test_publish_marks_missing_confirm_button_as_failed(monkeypatch, tmp_path):
    draft = tmp_path / "draft.json"
    draft.write_text(
        json.dumps({"title": "标题", "body": "正文"}, ensure_ascii=False),
        encoding="utf-8",
    )

    def fake_run(argv, **kwargs):
        return fake_completed(argv, stdout="[点击] 确认发布 → 没找到确认按钮\n")

    monkeypatch.setattr("pipeline.tools._common.subprocess.run", fake_run)

    result = publisher.publish(draft_path=str(draft))

    assert result["ok"] is False
    assert "没点到确认发布按钮" in result["note"]


# ---------- 边界：不碰浏览器库 ----------


def test_tools_do_not_import_patchright_or_headline():
    """填稿/发布靠 subprocess，工具层自己不许把浏览器依赖拉进来。"""
    assert editor.CLI_MODULE == "pipeline.content.headline"
    assert "patchright" not in sys.modules
    assert "pipeline.content.headline" not in sys.modules
