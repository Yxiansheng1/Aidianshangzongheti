"""选品打分。

和 `选品打分表.html` 用同一套口径和权重，两边结果应当一致。
改权重要改两个地方，别只改一个。

这个模块只做判断，不做数据采集——平台没有合法接口，抓取会封号。
数据由你录入，模块负责把它变成可比较的分数。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 权重合计 100。按「兼职 + 零货源 + 零背景」的约束定。
WEIGHTS: dict[str, int] = {
    "competition": 20,   # 竞争度：前 20 名里有几家普通 C 店
    "margin": 15,        # 毛利空间
    "after_sale": 15,    # 售后省心：不易碎、无尺码、无色差
    "low_inquiry": 12,   # 低咨询：看图就能下单
    "supply": 13,        # 供应链稳定：几家能代发
    "visual": 15,        # 视觉可差异化
    "repeat": 10,        # 复购潜力
}

LABELS: dict[str, str] = {
    "competition": "竞争度",
    "margin": "毛利空间",
    "after_sale": "售后省心",
    "low_inquiry": "低咨询",
    "supply": "供应链稳定",
    "visual": "视觉可差异化",
    "repeat": "复购潜力",
}

# 任意一项成立即淘汰，不管分数多高
VETO_LABELS: dict[str, str] = {
    "license": "需资质",
    "brand": "品牌侵权风险",
    "fragile": "易碎易变形",
    "size": "有尺码/规格争议",
    "heavy": "超重超尺寸",
    "custom": "需定制",
    "ban": "平台限售",
}


@dataclass
class Candidate:
    name: str
    url: str = ""
    price: float = 0.0
    cost: float = 0.0
    return_rate: float = 12.0
    scores: dict[str, int] = field(default_factory=dict)
    veto: list[str] = field(default_factory=list)
    note: str = ""

    def __post_init__(self) -> None:
        for key in WEIGHTS:
            self.scores.setdefault(key, 3)

    # ---- 计算 ----

    def margin(self) -> tuple[float, float]:
        """返回 (单件毛利, 毛利率)。扣平台扣点和退货损耗。"""
        price = float(self.price or 0)
        cost = float(self.cost or 0)
        rate = float(self.return_rate or 0) / 100
        fee = price * 0.012
        ret_loss = rate * 10
        profit = price - cost - fee - ret_loss
        ratio = profit / price if price > 0 else 0.0
        return profit, ratio

    def veto_hit(self) -> str | None:
        for key in self.veto:
            if key in VETO_LABELS:
                return VETO_LABELS[key]
        return None

    def total(self) -> float:
        score = 0.0
        for key, weight in WEIGHTS.items():
            value = max(0, min(5, int(self.scores.get(key, 0))))
            score += value / 5 * weight
        return score

    def grade(self) -> str:
        if self.veto_hit():
            return "淘汰"
        t = self.total()
        if t >= 75:
            return "主推"
        if t >= 60:
            return "备选"
        if t >= 45:
            return "观察"
        return "放弃"

    def is_blank(self) -> bool:
        return not str(self.name).strip() and not self.price


def rank(candidates: list[Candidate]) -> list[Candidate]:
    """淘汰的永远排最后，其余按总分降序。"""
    return sorted(
        candidates,
        key=lambda c: (bool(c.veto_hit()), -c.total()),
    )


def from_dict(raw: dict[str, Any]) -> Candidate:
    known = {"name", "url", "price", "cost", "return_rate", "scores", "veto", "note"}
    payload = {k: v for k, v in raw.items() if k in known}
    payload.setdefault("name", "")
    scores = payload.get("scores") or {}
    payload["scores"] = {k: int(v) for k, v in scores.items() if k in WEIGHTS}
    payload["veto"] = list(payload.get("veto") or [])
    return Candidate(**payload)


def to_dict(c: Candidate) -> dict[str, Any]:
    return {
        "name": c.name,
        "url": c.url,
        "price": c.price,
        "cost": c.cost,
        "return_rate": c.return_rate,
        "scores": dict(c.scores),
        "veto": list(c.veto),
        "note": c.note,
    }
