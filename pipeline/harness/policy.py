"""自主度策略：决定"这一步要不要停下来等人批准"。

这是整个 harness 的核心开关，不依赖任何模型或框架，纯逻辑、可测试。

三档（用户原话）：
    auto      我忙，你跑完；只有不可逆动作才停
    standard  默认；写类动作里标了 critical 的才停
    step      我盯着；每个写动作都停

自动化规则：
    · 同一个工具连续失败 2 次  → 该工具降一档（auto → standard → step）
    · 单个任务重试超过 3 次    → 整个任务降到 step
    · 某工具近期失败率 > 30%   → 全局降到 standard
    · 升档只提示，不自动执行（"最近 20 次全成功，可以试试全自动"）
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

# 近 7 天的失败率窗口
WINDOW_SECONDS = 7 * 24 * 3600
FAIL_RATE_THRESHOLD = 0.30
MIN_CALLS_FOR_RATE = 5
CONSECUTIVE_FAILURE_LIMIT = 2
TASK_RETRY_LIMIT = 3
UPGRADE_SUGGEST_AFTER = 20


class Risk(str, Enum):
    """工具的风险等级。决定它在各档位下要不要审批。"""

    READ = "read"                   # 读资料、查数据
    WRITE = "write"                 # 写稿、出图、存草稿
    IRREVERSIBLE = "irreversible"   # 发布、删除、花钱


class Autonomy(str, Enum):
    AUTO = "auto"
    STANDARD = "standard"
    STEP = "step"


_ORDER = [Autonomy.AUTO, Autonomy.STANDARD, Autonomy.STEP]


def downgrade(level: Autonomy) -> Autonomy:
    idx = _ORDER.index(level)
    return _ORDER[min(idx + 1, len(_ORDER) - 1)]


@dataclass
class ToolStat:
    calls: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    recent_failures: list[float] = field(default_factory=list)  # 失败时间戳


class AutonomyController:
    """一次任务一个实例（也可以全局一个，按任务建更清晰）。"""

    def __init__(self, level: Autonomy = Autonomy.STANDARD, *, clock=time.time):
        self.level = level
        self._clock = clock
        self._stats: dict[str, ToolStat] = {}
        self._tool_levels: dict[str, Autonomy] = {}
        self._task_retries = 0
        self._notes: list[str] = []

    # ---------- 查询 ----------

    def level_for(self, tool: str) -> Autonomy:
        return self._tool_levels.get(tool, self.level)

    def stats(self, tool: str) -> ToolStat:
        return self._stats.setdefault(tool, ToolStat())

    def needs_approval(self, tool: str, risk: Risk, *, critical: bool = False) -> bool:
        """这一刻要不要停下来等人。"""
        if risk is Risk.IRREVERSIBLE:
            return True
        level = self.level_for(tool)
        if level is Autonomy.AUTO:
            return False
        if level is Autonomy.STEP:
            return risk is Risk.WRITE
        # standard：只有标了关键的写动作才停
        return risk is Risk.WRITE and critical

    # ---------- 记录 ----------

    def record(self, tool: str, ok: bool) -> None:
        stat = self.stats(tool)
        stat.calls += 1
        now = self._clock()
        if ok:
            stat.consecutive_failures = 0
            return

        stat.failures += 1
        stat.consecutive_failures += 1
        stat.recent_failures.append(now)
        self._prune(stat, now)

        if stat.consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
            self._downgrade_tool(tool, f"{tool} 连续失败 {stat.consecutive_failures} 次")

        rate, calls = self._recent_rate(stat, now)
        if calls >= MIN_CALLS_FOR_RATE and rate > FAIL_RATE_THRESHOLD and self.level is Autonomy.AUTO:
            self.level = Autonomy.STANDARD
            self._notes.append(
                f"{tool} 近 7 天失败率 {rate:.0%}（{calls} 次），全局从 auto 降到 standard"
            )

    def note_retry(self) -> None:
        self._task_retries += 1
        if self._task_retries >= TASK_RETRY_LIMIT and self.level is not Autonomy.STEP:
            self.level = Autonomy.STEP
            self._notes.append(f"任务重试 {self._task_retries} 次，整个任务降到 step")

    def reset_task_retries(self) -> None:
        self._task_retries = 0

    # ---------- 升档提示 ----------

    def upgrade_suggestion(self) -> str | None:
        if self.level is Autonomy.STEP:
            return None
        for tool, stat in self._stats.items():
            if stat.calls >= UPGRADE_SUGGEST_AFTER and stat.failures == 0:
                return f"{tool} 最近 {stat.calls} 次全部成功，可以考虑放宽到更自动的档位"
        return None

    @property
    def notes(self) -> list[str]:
        return list(self._notes)

    # ---------- 内部 ----------

    def _downgrade_tool(self, tool: str, reason: str) -> None:
        current = self.level_for(tool)
        if current is Autonomy.STEP:
            return
        self._tool_levels[tool] = downgrade(current)
        self._notes.append(f"{reason}，该工具降到 {self._tool_levels[tool].value}")

    def _prune(self, stat: ToolStat, now: float) -> None:
        cutoff = now - WINDOW_SECONDS
        stat.recent_failures = [t for t in stat.recent_failures if t >= cutoff]

    def _recent_rate(self, stat: ToolStat, now: float) -> tuple[float, int]:
        self._prune(stat, now)
        failures = len(stat.recent_failures)
        # calls 是全量的，失败是窗口内的；这里用窗口失败数 / 窗口内估算调用数
        # 简化：拿全量 calls 当分母（宁可低估失败率，避免误降档）
        if not stat.calls:
            return 0.0, 0
        return failures / max(stat.calls, 1), stat.calls
