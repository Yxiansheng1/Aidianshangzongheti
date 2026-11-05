"""从 L2 读工具清单。

这层只读不写：L2 的注册表长什么样，这里就还原成什么样的 JSON。
L2 还没落地、或者导入了却没给注册表，都不许把 API 拖死——只报缺，不抛。
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any

LOG = logging.getLogger(__name__)

TOOLS_MODULE = "pipeline.tools"

# L2 对外入口还没冻结，按优先级多探几个，比回头改 L2 便宜。
FACTORY_NAMES = ("build_registry", "create_registry", "get_registry", "default_registry")
INSTANCE_NAMES = ("REGISTRY", "registry", "TOOLS")

# 只透出这几个字段：多透一个，界面就多一处耦合。
FIELDS = ("name", "description", "risk", "critical", "tags")


@dataclass
class ToolCatalog:
    """一次读取的结果。error 为 None 才表示工具层真的就绪了。"""

    tools: list[dict[str, Any]] = field(default_factory=list)
    source: str = "unavailable"
    error: str | None = None


def load_tool_catalog(module_name: str | None = None) -> ToolCatalog:
    module_name = module_name or TOOLS_MODULE
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # L2 没写完 / 缺依赖 都走这里
        LOG.warning("工具层不可用：%s", exc)
        return ToolCatalog(
            source="unavailable",
            error=f"导入 {module_name} 失败：{type(exc).__name__}: {exc}",
        )

    registry, source = _find_registry(module)
    if registry is None:
        tried = ", ".join((*FACTORY_NAMES, *INSTANCE_NAMES))
        return ToolCatalog(
            source=module_name,
            error=f"{module_name} 里找不到工具注册表（试过 {tried}）",
        )

    try:
        described = registry.describe()
    except Exception as exc:
        LOG.exception("读注册表失败")
        return ToolCatalog(
            source=source,
            error=f"{source}.describe() 失败：{type(exc).__name__}: {exc}",
        )

    return ToolCatalog(tools=[_normalize(item) for item in described], source=source)


def _find_registry(module: Any) -> tuple[Any | None, str]:
    """返回 (带 describe() 的对象, 来源描述)。"""
    for name in FACTORY_NAMES:
        factory = getattr(module, name, None)
        if not callable(factory):
            continue
        try:
            candidate = factory()
        except Exception as exc:
            LOG.warning("%s.%s() 调用失败：%s", module.__name__, name, exc)
            continue
        if callable(getattr(candidate, "describe", None)):
            return candidate, f"{module.__name__}.{name}()"

    for name in INSTANCE_NAMES:
        candidate = getattr(module, name, None)
        if callable(getattr(candidate, "describe", None)):
            return candidate, f"{module.__name__}.{name}"

    return None, module.__name__


def _normalize(item: Any) -> dict[str, Any]:
    """describe() 给 dict 或 ToolSpec 都接住，输出稳定的五个字段。"""
    raw: dict[str, Any]
    if isinstance(item, dict):
        raw = item
    else:
        raw = {
            "name": getattr(item, "name", None),
            "description": getattr(item, "description", ""),
            "risk": getattr(item, "risk", None),
            "critical": getattr(item, "critical", False),
            "tags": getattr(item, "tags", ()),
        }

    out: dict[str, Any] = {}
    for key in FIELDS:
        out[key] = raw.get(key)

    risk = out["risk"]
    out["risk"] = getattr(risk, "value", risk)  # 兼容 Risk 枚举
    out["description"] = out["description"] or ""
    out["critical"] = bool(out["critical"])
    out["tags"] = list(out["tags"] or ())
    return out
