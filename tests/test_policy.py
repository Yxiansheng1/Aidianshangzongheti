"""自主度策略的测试：三档、自动降档、升档提示。

不依赖模型，跑得飞快：
    .venv\\Scripts\\python.exe -m pytest tests/test_policy.py -q
"""

from pipeline.harness.policy import (
    Autonomy,
    AutonomyController,
    Risk,
    downgrade,
)


def test_irreversible_always_needs_approval():
    c = AutonomyController(Autonomy.AUTO)
    assert c.needs_approval("publish", Risk.IRREVERSIBLE) is True


def test_read_never_needs_approval():
    c = AutonomyController(Autonomy.STEP)
    assert c.needs_approval("fetch", Risk.READ) is False


def test_auto_level_only_stops_irreversible():
    c = AutonomyController(Autonomy.AUTO)
    assert c.needs_approval("write_draft", Risk.WRITE) is False
    assert c.needs_approval("write_draft", Risk.WRITE, critical=True) is False


def test_standard_level_stops_critical_writes_only():
    c = AutonomyController(Autonomy.STANDARD)
    assert c.needs_approval("write_draft", Risk.WRITE) is False
    assert c.needs_approval("write_draft", Risk.WRITE, critical=True) is True


def test_step_level_stops_every_write():
    c = AutonomyController(Autonomy.STEP)
    assert c.needs_approval("write_draft", Risk.WRITE) is True


def test_two_consecutive_failures_downgrade_that_tool():
    c = AutonomyController(Autonomy.AUTO)
    c.record("make_image", ok=False)
    assert c.level_for("make_image") is Autonomy.AUTO
    c.record("make_image", ok=False)
    assert c.level_for("make_image") is Autonomy.STANDARD
    # 降档后 write 类关键步骤要审批
    assert c.needs_approval("make_image", Risk.WRITE) is False  # 非 critical
    c.record("make_image", ok=False)
    c.record("make_image", ok=False)
    assert c.level_for("make_image") is Autonomy.STEP


def test_success_resets_consecutive_failures():
    c = AutonomyController(Autonomy.AUTO)
    c.record("fetch", ok=False)
    c.record("fetch", ok=True)
    c.record("fetch", ok=False)
    assert c.level_for("fetch") is Autonomy.AUTO


def test_task_retries_push_whole_task_to_step():
    c = AutonomyController(Autonomy.AUTO)
    for _ in range(3):
        c.note_retry()
    assert c.level is Autonomy.STEP
    assert any("重试" in n for n in c.notes)


def test_downgrade_is_capped_at_step():
    assert downgrade(Autonomy.STEP) is Autonomy.STEP
    assert downgrade(Autonomy.AUTO) is Autonomy.STANDARD
    assert downgrade(Autonomy.STANDARD) is Autonomy.STEP


def test_upgrade_only_suggested_not_auto():
    c = AutonomyController(Autonomy.STANDARD)
    for _ in range(20):
        c.record("write_draft", ok=True)
    assert c.level is Autonomy.STANDARD  # 没自动升
    assert c.upgrade_suggestion() is not None
