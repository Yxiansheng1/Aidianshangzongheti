"""发布适配层。

对外只暴露 build_plan / run。换发布工具只改这个包，上层不动。

注意：social-auto-upload 的真实参数形态，需要在「docs/01-安装清单.md」
第 2 步验证之后，回填到 config.toml 的 [publish.templates] 里。
这里的 DEFAULT_TEMPLATE 只是占位，不保证能跑通。
"""

from .sau import PublishPlan, build_plan, run

__all__ = ["PublishPlan", "build_plan", "run"]
