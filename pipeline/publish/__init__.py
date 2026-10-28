"""发布适配层。

对外只暴露 build_plan / resolve_sau / run。换发布工具只改这个包，上层不动。
"""

from .sau import PLATFORMS, PlatformSpec, PublishPlan, build_plan, resolve_sau, run

__all__ = [
    "PublishPlan",
    "PlatformSpec",
    "PLATFORMS",
    "build_plan",
    "resolve_sau",
    "run",
]
