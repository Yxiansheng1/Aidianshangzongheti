"""上架资料包。

**「一键上货」做不到，得先说清楚为什么。**

淘宝 / 拼多多 / 抖音小店的商品发布接口不对个人开发者开放：
- 淘宝开放平台要企业资质 + 应用审核 + 类目权限，个人拿不到
- 市面上店小秘、芒果店长能批量上架，因为它们是持牌服务商
- 模拟浏览器批量上架 = 违反平台规则，风险比发内容高得多

**能做的是**：把上架要填的东西全部准备好——主图按顺序命名、标题、卖点、
详情文案、属性表。你在千牛后台复制粘贴，5 分钟一个品。

这不是妥协，是唯一合法的路。
"""

from __future__ import annotations

import csv
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 上架时要填但机器猜不出来的字段，留空让你自己补
BLANK_ATTRS = [
    ("类目", "一级类目 / 二级类目"),
    ("品牌", "没有就填「其他」"),
    ("材质", ""),
    ("规格尺寸", ""),
    ("重量", ""),
    ("产地", ""),
    ("执行标准", "食品/电器类必填"),
]


@dataclass
class PackageResult:
    name: str
    dir: str
    images: int
    files: list[str] = field(default_factory=list)


def _sentences(text: str) -> list[str]:
    """把正文拆成句子，用来做卖点草稿。"""
    raw = re.split(r"[。；;\n]+", text or "")
    return [s.strip() for s in raw if len(s.strip()) >= 4]


def _mechanical_points(product: dict) -> list[str]:
    points = _sentences(product.get("body") or "")
    if not points:
        points = [f"{product.get('name', '商品')}"]
    return points[:5]


def _ai_points(product: dict, cfg: Any) -> list[str] | None:
    """有文本模型 key 就润色成卖点，没有就返回 None 走机械版。"""
    from .model.client import ModelError, OpenAICompatible

    if not cfg.has_model or not cfg.model.text_model:
        return None

    client = OpenAICompatible(
        base_url=cfg.model.base_url,
        api_key=cfg.model.api_key,
        timeout=cfg.model.timeout,
        text_model=cfg.model.text_model,
    )
    prompt = (
        "把这个商品的卖点改写成 5 条淘宝详情页短句，每条不超过 20 字，"
        "只写商品本身的事实，不要编造参数，不要加表情和感叹号。每行一条，不要编号。\n\n"
        f"商品名：{product.get('name')}\n"
        f"原始描述：{product.get('body') or '（无）'}\n"
        f"标签：{', '.join(product.get('tags') or []) or '（无）'}"
    )
    try:
        text = client.ask(prompt, system="你是电商文案，只做提炼，不臆造")
    except ModelError:
        return None
    lines = [ln.strip(" -··") for ln in text.splitlines() if ln.strip()]
    return lines[:5] or None


def build_package(product: dict, out_root: Path | str, cfg: Any) -> PackageResult:
    name = product.get("name") or product.get("id") or "未命名"
    target = Path(out_root) / re.sub(r'[\\/:*?"<>|]', "_", name)
    images_dir = target / "主图"
    images_dir.mkdir(parents=True, exist_ok=True)

    files: list[str] = []

    # ---- 主图按顺序重命名 ----
    copied = 0
    for index, raw in enumerate(product.get("images") or [], 1):
        source = Path(raw)
        if not source.is_file():
            continue
        suffix = source.suffix.lower() or ".jpg"
        dest = images_dir / f"{index:02d}{suffix}"
        shutil.copy2(source, dest)
        copied += 1
    if copied:
        files.append(f"主图/（{copied} 张，已按 01 02 03 顺序命名）")

    # ---- 标题 ----
    title = (product.get("title") or name).strip()
    (target / "标题.txt").write_text(title + "\n", encoding="utf-8")
    files.append("标题.txt")

    # ---- 卖点 ----
    ai_points = _ai_points(product, cfg)
    points = ai_points or _mechanical_points(product)
    source_note = "（AI 提炼，请核对是否属实）" if ai_points else "（从正文机械拆分，建议手动润色）"
    (target / "卖点.txt").write_text(
        "\n".join(f"{i}. {p}" for i, p in enumerate(points, 1)) + f"\n\n{source_note}\n",
        encoding="utf-8",
    )
    files.append("卖点.txt")

    # ---- 详情文案 ----
    body = (product.get("body") or "").strip()
    detail = [f"# {title}", ""]
    if points:
        detail += ["## 卖点", ""] + [f"- {p}" for p in points] + [""]
    if body:
        detail += ["## 详情", "", body, ""]
    tags = product.get("tags") or []
    if tags:
        detail += ["## 标签", "", " ".join(f"#{t}" for t in tags), ""]
    (target / "详情.md").write_text("\n".join(detail), encoding="utf-8")
    files.append("详情.md")

    # ---- 属性表 ----
    csv_path = target / "属性表.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["字段", "值", "说明"])
        writer.writerow(["商品标题", title, "30 字以内更好搜"])
        for key, hint in BLANK_ATTRS:
            writer.writerow([key, "", hint])
        writer.writerow(["", "", ""])
        writer.writerow(["素材来源", product.get("dir", ""), "原始导出目录"])
        writer.writerow(["图片数量", str(copied), ""])
        writer.writerow(["标签", " ".join(tags), "淘宝不用标签，这里留作关键词参考"])
    files.append("属性表.csv")

    # ---- 操作指引 ----
    guide = f"""# 上架指引 · {name}

## 为什么没有"一键上架"

淘宝/拼多多/抖音小店的商品发布接口不对个人开发者开放。
能批量上架的工具（店小秘、芒果店长）持有服务商资质。
模拟浏览器批量上架违反平台规则，账号风险远高于发内容。

所以这里的做法是：**把要填的东西全准备好，你复制粘贴。**

## 操作顺序（约 5 分钟）

1. 打开千牛卖家中心 → 发布宝贝
2. 类目：参考 `属性表.csv` 里的 `类目` 行，或按主图判断
3. 标题：复制 `标题.txt` 全文
4. 主图：上传 `主图/` 里的图，按 01 02 03 顺序
5. 卖点：复制 `卖点.txt` 里的句子，填到详情模块
6. 详情：`详情.md` 内容贴到详情编辑器（支持直接粘贴纯文本）
7. 属性：`属性表.csv` 里空着的字段必须补，尤其是材质、尺寸、执行标准
8. 价格：按你自己的成本算，毛利建议不低于 25%

## 清单

{chr(10).join('- ' + f for f in files)}

## 上架前自查

- [ ] 标题里有没有品牌词（有就是侵权风险）
- [ ] 主图是不是白底或场景图，有没有水印
- [ ] 属性表的空白字段填完了吗
- [ ] 价格算过平台扣点和退货损耗了吗
- [ ] 库存填的对不对（代发不要填太大）
"""
    (target / "上架指引.md").write_text(guide, encoding="utf-8")
    files.append("上架指引.md")

    return PackageResult(name=name, dir=str(target), images=copied, files=files)


def build_all(manifest: dict, out_root: Path | str, cfg: Any) -> list[PackageResult]:
    return [build_package(p, out_root, cfg) for p in (manifest.get("products") or [])]
