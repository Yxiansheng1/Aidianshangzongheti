"""内容队列。

学 n8n 模板 3442 的做法：内容不是"一次跑完就没了"，而是一条条躺在队列里，
每条带状态，出了问题能重跑，攒够了一起发。

状态流转：

    pending ──写──> written ──审──> approved ──发布──> published
                       │                │
                       └──> needs_fix   └──退回──> rejected
                              │
                              └──改完──> written

存储：output/内容队列/queue.json（人能直接看，坏了好修）
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import ROOT

QUEUE_DIR = ROOT / "output" / "内容队列"
QUEUE_FILE = QUEUE_DIR / "queue.json"

STATUS_FLOW = {
    "pending": "待写",
    "written": "已写待审",
    "needs_fix": "需修改",
    "approved": "已通过待发",
    "rejected": "已退回",
    "published": "已发布",
}


@dataclass
class Item:
    id: str
    topic: str
    platform: str = "xiaohongshu"
    product: str = ""
    extra: str = ""
    tone: str = ""
    source_url: str = ""                # 原文链接
    source_text: str = ""               # 原文正文，改写的依据

    title: str = ""
    body: str = ""
    tags: list[str] = field(default_factory=list)

    source: str = ""                    # 商品原图（AI 出图的输入，必须是人拍的）
    status: str = "pending"
    review: dict[str, Any] = field(default_factory=dict)
    images: list[str] = field(default_factory=list)
    video: str = ""
    note: str = ""

    created: str = ""
    updated: str = ""

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # status_label 是属性，asdict 不会带，手动补上（前端要显示中文）
        data["status_label"] = self.status_label
        return data

    @property
    def status_label(self) -> str:
        return STATUS_FLOW.get(self.status, self.status)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load() -> list[Item]:
    if not QUEUE_FILE.is_file():
        return []
    raw = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    items: list[Item] = []
    known = {f for f in Item.__dataclass_fields__}
    for entry in raw.get("items", []):
        payload = {k: v for k, v in entry.items() if k in known}
        payload.setdefault("id", "")
        payload.setdefault("topic", "")
        items.append(Item(**payload))
    return items


def _save(items: list[Item]) -> None:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"updated": _now(), "count": len(items), "items": [i.as_dict() for i in items]}
    QUEUE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _next_id(items: list[Item]) -> str:
    today = datetime.now().strftime("%Y%m%d")
    used = {i.id for i in items}
    index = 1
    while f"{today}-{index:03d}" in used:
        index += 1
    return f"{today}-{index:03d}"


# --------------------------------------------------------------- 操作


def add(topic: str, platform: str = "xiaohongshu", *, product: str = "",
        extra: str = "", tone: str = "", source_url: str = "",
        source_text: str = "") -> Item:
    if not topic.strip():
        raise ValueError("主题不能为空")
    items = _load()
    item = Item(
        id=_next_id(items),
        topic=topic.strip(),
        platform=platform,
        product=product,
        extra=extra,
        tone=tone,
        source_url=source_url,
        source_text=source_text,
        created=_now(),
        updated=_now(),
    )
    items.append(item)
    _save(items)
    return item


def all_items(status: str | None = None) -> list[Item]:
    items = _load()
    if status:
        items = [i for i in items if i.status == status]
    return sorted(items, key=lambda i: i.created, reverse=True)


def get(item_id: str) -> Item | None:
    for item in _load():
        if item.id == item_id:
            return item
    return None


def update(item_id: str, **changes: Any) -> Item:
    items = _load()
    for item in items:
        if item.id == item_id:
            for key, value in changes.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            item.updated = _now()
            _save(items)
            return item
    raise KeyError(f"没有这条：{item_id}")


def remove(item_id: str) -> bool:
    items = _load()
    kept = [i for i in items if i.id != item_id]
    if len(kept) == len(items):
        return False
    _save(kept)
    return True


# --------------------------------------------------------------- 流水线步骤


def write_item(item_id: str, cfg: Any) -> Item:
    """跑改写，把 pending/needs_fix 推到 written。"""
    from .writer import write

    item = get(item_id)
    if item is None:
        raise KeyError(f"没有这条：{item_id}")

    result = write(
        item.topic,
        item.platform,
        cfg,
        product=item.product,
        extra=item.extra,
        tone=item.tone,
        source_text=item.source_text,
    )
    return update(
        item_id,
        title=result["title"],
        body=result["body"],
        tags=result["tags"],
        status="written",
        review={},
        note=" / ".join(result.get("warnings") or []),
    )


def review_item(item_id: str, cfg: Any) -> Item:
    """跑审核，按结果推到 approved 或 needs_fix。"""
    from .review import review

    item = get(item_id)
    if item is None:
        raise KeyError(f"没有这条：{item_id}")
    if not item.body.strip():
        raise ValueError(f"{item_id} 还没写，先跑改写")

    combined = f"{item.title}\n\n{item.body}"
    outcome = review(combined, item.platform, cfg)

    return update(
        item_id,
        status="approved" if outcome.passed else "needs_fix",
        review=outcome.as_dict(),
    )


def step(item_id: str, cfg: Any) -> Item:
    """写 + 审，一步到位。"""
    write_item(item_id, cfg)
    return review_item(item_id, cfg)


def stats() -> dict[str, int]:
    items = _load()
    counts = {key: 0 for key in STATUS_FLOW}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    counts["total"] = len(items)
    return counts
