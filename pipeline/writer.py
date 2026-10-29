"""AI 改写：把一个主题写成各平台能发的稿子。

和 analyze 的区别：
    analyze  分析"这个商品值不值得做"，产出生图提示词
    writer   拿到一个主题/热点，写成"能直接发"的文案

平台风格差异很大，不能一套文案全平台发。所以每个平台单独一套提示词。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .model.client import ModelError, OpenAICompatible

SYSTEM = (
    "你是中文内容编辑，写给真实的人看。"
    "只说事实和真实感受，不编造数据、不写绝对化用语、不用夸张营销腔。"
    "输出必须是合法 JSON，不要代码围栏，不要任何解释文字。"
)

SCHEMA = """{
  "title": "标题",
  "body": "正文",
  "tags": ["标签1", "标签2"],
  "notes": "如果信息不足，写这里；没有就留空字符串"
}"""


@dataclass(frozen=True)
class PlatformStyle:
    key: str
    name: str
    title_max: int
    tag_max: int
    guide: str


PLATFORMS: dict[str, PlatformStyle] = {
    "xiaohongshu": PlatformStyle(
        key="xiaohongshu", name="小红书", title_max=20, tag_max=8,
        guide=(
            "小红书图文。必须按这四段写：\n"
            "① 钩子（1-2 句）：一个具体的、有画面的场景，或一个反常识的判断。"
            "不要「最近」「大家好」这种开场。\n"
            "② 主体（2-3 段）：具体发生了什么 + 你的真实动作。"
            "必须带可验证的细节：时间、数字、具体牌子、具体感受。"
            "写不出细节就别写。\n"
            "③ 转折或边界（1 段）：什么情况下不适合 / 有什么代价 / 你也没解决的部分。"
            "这一段决定可信度，不能省。\n"
            "④ 收尾（1 句）：一个具体的、对方能真的回答的问题。"
            "不要「你会怎么选」「评论区聊聊」这种假互动。\n\n"
            "硬性禁止：\n"
            "- 不写「如何核实信息」「信息素养」「保持理性」这类方法论空话\n"
            "- 不写「我先去对了两件事」「以原文为准」这类新闻编辑腔\n"
            "- 不写自己没有真实经历的事，宁可写得很小很具体\n"
            "- 不用「绝了」「谁懂啊」「家人们」\n"
            "标题不超过 20 字，要具体，不要悬念式标题党。"
        ),
    ),
    "zhihu": PlatformStyle(
        key="zhihu", name="知乎", title_max=60, tag_max=5,
        guide=(
            "知乎回答/文章。理性、有信息密度、分小标题。"
            "先给结论再展开，不要寒暄。可以列数据但要标明是估算。"
            "正文 400-800 字。不要营销腔，不要「家人们」。"
        ),
    ),
    "baijiahao": PlatformStyle(
        key="baijiahao", name="百家号", title_max=30, tag_max=5,
        guide=(
            "百家号资讯体。客观平实，导语一句话说清核心事实，然后分段展开。"
            "段落短，每段 2-3 句。适合被搜索到，标题里要有具体名词。"
            "正文 500-800 字。不要第一人称代入，不要煽动。"
        ),
    ),
    "dayu": PlatformStyle(
        key="dayu", name="大鱼号", title_max=30, tag_max=5,
        guide=(
            "大鱼号资讯体。跟百家号类似，但更口语一点，段落更短。"
            "正文 400-600 字。"
        ),
    ),
    "douyin": PlatformStyle(
        key="douyin", name="抖音口播", title_max=30, tag_max=5,
        guide=(
            "抖音短视频口播稿。前 3 秒必须抓住人（一个反常识、一个具体数字、或一个提问）。"
            "全篇口语，短句，一句一行。总长控制在 150-200 字（约 30-40 秒）。"
            "不要写「大家好我是」，直接进内容。"
        ),
    ),
}

PLATFORM_NAMES = {k: v.name for k, v in PLATFORMS.items()}


def build_prompt(topic: str, platform: str, *, product: str = "", extra: str = "") -> str:
    style = PLATFORMS.get(platform)
    if not style:
        raise ValueError(f"不支持的平台：{platform}。可选：{', '.join(PLATFORMS)}")

    parts = [
        f"平台：{style.name}",
        f"写作要求：{style.guide}",
        "",
        f"主题：{topic}",
    ]
    if product:
        parts.append(f"要推广的商品：{product}")
    if extra:
        parts.append(f"补充信息：{extra}")
    parts += [
        "",
        "硬性要求：",
        f"- 标题不超过 {style.title_max} 字",
        f"- 标签不超过 {style.tag_max} 个",
        "- 不写「最」「第一」「100%」「治愈」「根治」这类绝对化或功效词",
        "- 不编造销量、评价、检测报告、用户反馈",
        "- 不用「家人们」「绝了」「谁懂啊」这种空洞流行语",
        "",
        "**最重要的一条：**",
        "如果你发现这个主题跟给到的商品/经历之间没有可写的具体关联，"
        "**不要硬凑**。直接返回 title 和 body 都为空字符串，"
        "在 notes 里写清缺什么（例如：这个主题跟商品无关，需要一个具体的使用场景）。",
        "宁可交白卷，也不要写一篇谁都不想看的空话。",
        "",
        "按这个 JSON 输出：",
        SCHEMA,
    ]
    return "\n".join(parts)


def _strip_fence(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return (fenced.group(1) if fenced else text).strip()


def write(
    topic: str,
    platform: str,
    cfg: Any,
    *,
    product: str = "",
    extra: str = "",
    tone: str = "",
) -> dict[str, Any]:
    if not cfg.has_model:
        raise ModelError(
            "没有配置文本模型。去 config.toml 的 [model] 填 api_key（中转站也行）。"
        )
    if not topic.strip():
        raise ValueError("主题不能为空")

    style = PLATFORMS[platform]
    client = OpenAICompatible(
        base_url=cfg.model.base_url,
        api_key=cfg.model.api_key,
        timeout=max(cfg.model.timeout, 120),
        text_model=cfg.model.text_model,
    )

    prompt = build_prompt(topic, platform, product=product, extra=extra)
    if tone:
        prompt += f"\n语气：{tone}"

    text = client.ask(prompt, system=SYSTEM, max_tokens=4000, temperature=0.7)

    try:
        data = json.loads(_strip_fence(text))
    except json.JSONDecodeError:
        text = client.ask(
            prompt + "\n\n上次输出不是合法 JSON。这次只输出完整闭合的 JSON 对象。",
            system=SYSTEM, max_tokens=4000, temperature=0.3,
        )
        try:
            data = json.loads(_strip_fence(text))
        except json.JSONDecodeError as exc:
            raise ModelError(f"模型两次都返回非 JSON：{exc}\n{text[:300]}") from exc

    title = str(data.get("title") or "").strip()
    body = str(data.get("body") or "").strip()
    notes = str(data.get("notes") or "").strip()

    if not title or not body:
        raise ModelError(
            "模型判断这个主题写不出东西，拒绝硬凑。\n"
            f"它给的理由：{notes or '（没说明）'}\n\n"
            "换一个角度：给一个具体的经历、场景或商品细节，再试。"
        )

    tags = [str(t).strip().lstrip("#") for t in (data.get("tags") or []) if str(t).strip()]

    warnings: list[str] = []
    if len(title) > style.title_max:
        title = title[: style.title_max]
        warnings.append(f"标题超过 {style.title_max} 字，已截断")
    if len(tags) > style.tag_max:
        tags = tags[: style.tag_max]
        warnings.append(f"标签超过 {style.tag_max} 个，已截断")

    return {
        "platform": platform,
        "platform_name": style.name,
        "topic": topic,
        "title": title,
        "body": body,
        "tags": tags,
        "notes": notes,
        "warnings": warnings,
        "length": len(body),
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# {result['title']}",
        "",
        f"平台：{result['platform_name']}　字数：{result['length']}",
        "",
        result["body"],
        "",
    ]
    if result["tags"]:
        lines += [" ".join(f"#{t}" for t in result["tags"]), ""]
    if result.get("notes"):
        lines += [f"> 备注：{result['notes']}", ""]
    for warning in result.get("warnings", []):
        lines.append(f"> ⚠ {warning}")
    return "\n".join(lines)
