"""商品分析 + 生图文案 + 视频文案。

输入一个商品（链接解析结果 + 你手动补的信息），输出：
  1. 商品分析：定位、人群、卖点、差异点、售后风险、定价、搜索词
  2. 生图提示词：直接能粘到 `pipeline gen`
  3. 视频提示词：直接能粘到 `pipeline vid`
  4. 小红书文案

需要文本模型（config.toml 里的 [model]）。没有 key 就跑不了——
因为这部分靠的是判断，不是模板拼接。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .model.client import ModelError, OpenAICompatible

SYSTEM = (
    "你是电商选品与内容策划。只基于给定信息做判断；缺什么就明说缺，"
    "绝对不要编造参数、材质、销量、认证。"
    "输出必须是合法 JSON，不要代码围栏，不要任何解释性文字。"
)

SCHEMA_HINT = """{
  "positioning": "一句话：这是什么，卖给谁",
  "audience": "目标人群，具体到使用场景",
  "selling_points": ["3-5 条，每条不超过 15 字"],
  "differentiation": ["跟同类的差异点 2-4 条；想不出来就写「无明显差异」，不要硬编"],
  "after_sale_risks": ["售后风险 1-3 条"],
  "pricing": {"suggest": "建议售价区间", "reason": "一句话说明依据"},
  "search_keywords": ["8-12 个真实搜索词，从宽到窄"],
  "image_prompts": [
    {"name": "白底主图", "prompt": "……"},
    {"name": "场景图", "prompt": "……"},
    {"name": "细节特写", "prompt": "……"},
    {"name": "平铺组合", "prompt": "……"},
    {"name": "使用场景", "prompt": "……"}
  ],
  "video_prompts": [
    {"name": "缓慢推进", "prompt": "……"},
    {"name": "光影变化", "prompt": "……"}
  ],
  "xiaohongshu": {"title": "不超过 20 字", "body": "150-300 字，第一人称真实体验，不要用夸张词", "tags": ["5-8 个"]},
  "verdict": {"grade": "主推 或 备选 或 观察 或 放弃", "reason": "一句话理由"}
}"""

IMAGE_RULES = """
生图提示词的要求（很重要，直接决定出图效果）：
- 我们的模型是「参考图生图」，商品本身会原样保留，所以提示词**只描述环境和拍摄方式**，
  不要描述商品长什么样（写了反而会让商品变形）。
- 每条都必须包含：场景 + 光线 + 景深 + 构图 + 一句「商品保持原样不变形」。
- 中英文都可以，用中文。
- 五条分别是：白底主图、生活场景图、细节特写、平铺组合、真人使用场景。
- 每条 40-80 字，具体到能直接生成，不要写「高级感」这种虚词。
"""

VIDEO_RULES = """
视频提示词的要求：
- 我们的模型是「图生视频」，只有一张起始图，所以**不能描述画面里出现新东西**。
- 只描述：镜头怎么动 + 光线/氛围怎么变化 + 有没有轻微的自然动态。
- 每条 20-50 字，一条一个镜头，不要写分镜表。
"""


@dataclass
class ProductBrief:
    """分析用的原始信息。链接解析不出来的部分，靠 extra 补。"""

    name: str = ""
    url: str = ""
    price: str = ""
    description: str = ""
    extra: str = ""
    site: str = ""
    fetch_note: str = ""

    def as_text(self) -> str:
        lines = []
        if self.name:
            lines.append(f"商品名：{self.name}")
        if self.site:
            lines.append(f"平台：{self.site}")
        if self.price:
            lines.append(f"标价：{self.price}")
        if self.description:
            lines.append(f"页面描述：{self.description}")
        if self.extra:
            lines.append(f"补充信息：{self.extra}")
        if self.url:
            lines.append(f"链接：{self.url}")
        if self.fetch_note:
            lines.append(f"（抓取提示：{self.fetch_note}）")
        return "\n".join(lines) or "（没有任何商品信息）"


def build_prompt(brief: ProductBrief) -> str:
    return f"""分析这个商品，按下面的 JSON 结构输出。

商品信息：
{brief.as_text()}

{IMAGE_RULES}

{VIDEO_RULES}

JSON 结构：
{SCHEMA_HINT}

注意：
- 信息不足就在对应字段写「信息不足，需补充」，不要编。
- 如果判断这个品不值得做，verdict.grade 写「放弃」，reason 要具体。
"""


def _strip_fence(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return (fenced.group(1) if fenced else text).strip()


def _coerce(data: dict) -> dict:
    """把模型可能漏掉的字段补成安全默认值。"""
    def as_list(value: Any) -> list:
        if isinstance(value, list):
            return [str(v) for v in value if str(v).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    data.setdefault("positioning", "")
    data.setdefault("audience", "")
    data["selling_points"] = as_list(data.get("selling_points"))
    data["differentiation"] = as_list(data.get("differentiation"))
    data["after_sale_risks"] = as_list(data.get("after_sale_risks"))
    data["search_keywords"] = as_list(data.get("search_keywords"))

    pricing = data.get("pricing")
    if not isinstance(pricing, dict):
        pricing = {"suggest": str(pricing or ""), "reason": ""}
    data["pricing"] = pricing

    def prompt_list(value: Any) -> list[dict]:
        out = []
        for item in value or []:
            if isinstance(item, dict) and item.get("prompt"):
                out.append({
                    "name": str(item.get("name") or "未命名"),
                    "prompt": str(item["prompt"]).strip(),
                })
        return out

    data["image_prompts"] = prompt_list(data.get("image_prompts"))
    data["video_prompts"] = prompt_list(data.get("video_prompts"))

    xhs = data.get("xiaohongshu")
    if not isinstance(xhs, dict):
        xhs = {}
    data["xiaohongshu"] = {
        "title": str(xhs.get("title") or ""),
        "body": str(xhs.get("body") or ""),
        "tags": as_list(xhs.get("tags")),
    }

    verdict = data.get("verdict")
    if not isinstance(verdict, dict):
        verdict = {"grade": "观察", "reason": str(verdict or "")}
    data["verdict"] = verdict

    return data


def analyze(brief: ProductBrief, cfg: Any) -> dict:
    if not cfg.has_model:
        raise ModelError(
            "没有配置文本模型。这个功能靠模型判断，不能用模板替代。\n"
            "去 platform.deepseek.com 充 10 元拿个 key，填进 config.toml 的 [model] api_key。"
        )

    client = OpenAICompatible(
        base_url=cfg.model.base_url,
        api_key=cfg.model.api_key,
        timeout=max(cfg.model.timeout, 120),
        text_model=cfg.model.text_model,
    )
    text = client.ask(build_prompt(brief), system=SYSTEM)

    try:
        data = json.loads(_strip_fence(text))
    except json.JSONDecodeError as exc:
        raise ModelError(
            f"模型返回的不是合法 JSON（{exc}）。原始输出前 400 字：\n{text[:400]}"
        ) from exc

    if not isinstance(data, dict):
        raise ModelError("模型返回的 JSON 不是对象")

    return _coerce(data)


def render_markdown(result: dict, brief: ProductBrief) -> str:
    lines = [f"# {brief.name or '商品分析'}", ""]
    if brief.url:
        lines += [f"来源：{brief.site or ''} {brief.url}", ""]

    verdict = result.get("verdict", {})
    lines += [f"**结论：{verdict.get('grade', '')}** —— {verdict.get('reason', '')}", ""]

    lines += ["## 定位", "", result.get("positioning", "") or "—", ""]
    lines += ["## 目标人群", "", result.get("audience", "") or "—", ""]

    def bullets(title: str, items: list[str]) -> None:
        lines.extend([f"## {title}", ""])
        lines.extend([f"- {i}" for i in items] or ["- —"])
        lines.append("")

    bullets("核心卖点", result.get("selling_points", []))
    bullets("差异点", result.get("differentiation", []))
    bullets("售后风险", result.get("after_sale_risks", []))

    pricing = result.get("pricing", {})
    lines += ["## 定价", "", f"建议：{pricing.get('suggest', '—')}", "", f"{pricing.get('reason', '')}", ""]

    bullets("搜索词", result.get("search_keywords", []))

    lines += ["## 生图提示词", ""]
    for i, item in enumerate(result.get("image_prompts", []), 1):
        lines += [f"**{i}. {item['name']}**", "", "```", item["prompt"], "```", ""]

    lines += ["## 视频提示词", ""]
    for i, item in enumerate(result.get("video_prompts", []), 1):
        lines += [f"**{i}. {item['name']}**", "", "```", item["prompt"], "```", ""]

    xhs = result.get("xiaohongshu", {})
    lines += ["## 小红书文案", "", f"**{xhs.get('title', '')}**", "", xhs.get("body", ""), ""]
    if xhs.get("tags"):
        lines += [" ".join(f"#{t}" for t in xhs["tags"]), ""]

    return "\n".join(lines)
