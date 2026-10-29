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
  "gaps": ["这篇里有哪些地方是我没有依据、靠推测写的"]
}"""


@dataclass(frozen=True)
class PlatformStyle:
    key: str
    name: str
    title_max: int
    tag_max: int
    guide: str


POLISH_SYSTEM = "你是中文编辑。只改装扮，不改事实。直接输出改好的正文，不要解释，不要加标题。"

POLISH_PROMPT = """把下面这篇改掉 AI 味。**只改写法，不改事实。**

必做：
1. 换掉这些词：此外、至关重要、赋能、助力、深入探讨、无缝、总的来说、综上所述、
   值得注意的是、需要强调、由此可见、不可或缺、大幅提升、显著改善、全方位、
   多维度、旨在、闭环、抓手
2. 删掉这些讲义动作：拆一拆、盘一盘、说白了、本质上、换句话说
3. 打破每段「观点+解释+总结」的同构。让段落长短交替，有的一段只有一句话
4. 段尾不要补抽象结论，停在具体事实、场景或引语上
5. 破折号一段最多 1 处，多余的换成句号
6. 如果结尾在喊口号或升华，改成一件可执行的小事，或者一个真能被回答的问题

不许做：
- 不许改事实、数字、专有名词、你原来的观点
- 不许添加原文没有的经历和细节
- 不许加 emoji

原文：
\"\"\"
{text}
\"\"\"

只输出改好的正文。
"""


def polish(body: str, platform: str, cfg: Any) -> str:
    """第二遍：去掉 AI 味。失败就返回原文，不影响主流程。"""
    if len(body) < 80:
        return body
    try:
        client = OpenAICompatible(
            base_url=cfg.model.base_url,
            api_key=cfg.model.api_key,
            timeout=max(cfg.model.timeout, 120),
            text_model=cfg.model.text_model,
        )
        out = client.ask(
            POLISH_PROMPT.format(text=body),
            system=POLISH_SYSTEM, max_tokens=3000, temperature=0.6,
        )
    except ModelError:
        return body

    cleaned = out.strip().strip('"""').strip()
    # 改坏了（太短或太长）就退回原稿
    if len(cleaned) < len(body) * 0.5 or len(cleaned) > len(body) * 2:
        return body
    return cleaned


PLATFORMS: dict[str, PlatformStyle] = {
    "xiaohongshu": PlatformStyle(
        key="xiaohongshu", name="小红书", title_max=20, tag_max=8,
        guide=(
            "小红书。这次是**热点追评**，不是新闻复述。\n"
            "骨架（来源：墨痕 skill 的热点追评文体）：\n"
            "  ① 事件：一句话带过。**最多一句**，不要复述报道，"
            "不要写「据报道」「截至X日」「看XX网的报道」。\n"
            "  ② 我的看法：这篇的主体。你什么态度、为什么这么想。\n"
            "  ③ 反方说法：别人可能怎么反驳你。写出来，证明不是拍脑袋。\n"
            "  ④ 不跟风下结论：留个开放口子，别给标准答案。\n\n"
            "开头 3 行是生死线（折叠线，划不开就没人看）。四选一：\n"
            "  · 结果前置：先说结论或结果，再解释\n"
            "  · 身份+痛点：说清你是谁、正卡在什么处境\n"
            "  · 反转否定：先否掉一个大家默认的做法\n"
            "  · 原话吐槽：一句真实的、带情绪的抱怨开场\n"
            "禁止「大家好」「最近」「随着…」开场，禁止背景铺垫。\n\n"
            "硬要求：\n"
            "- 每段 1-3 行，超过 3 行必须拆；段间空行；全文 300-800 字\n"
            "- 用「我」不用「笔者」；正文里指挥读者的「你」全文最多 1 次\n"
            "- **必须写至少 1 处缺点或「不适合谁」**，这是可信度最便宜的来源\n"
            "- 至少 2 次「我试过/我用过/我算过」这类亲历表达\n"
            "- 感受要具体：不写「效果很好」，写「第 5 天下巴那颗闭口平了」\n"
            "- 允许口语和不完整句，允许自嘲\n\n"
            "禁用的 AI 腔词（出现即不合格）：\n"
            "此外、至关重要、赋能、助力、深入探讨、无缝、总的来说、综上所述、\n"
            "值得注意的是、需要强调、由此可见、不可或缺、大幅提升、显著改善、\n"
            "全方位、多维度、旨在、闭环、抓手、打造生态\n\n"
            "禁用的公众号腔：众所周知、随着…的发展、首先其次最后、\n"
            "希望对你有所帮助、值得一提的是、拆一拆、盘一盘、说白了、本质上\n\n"
            "节奏：长短句交替，每 200 字内至少切换一次。段尾停在具体事实或场景，\n"
            "别每段补一句抽象总结。破折号一段最多 1 处。\n\n"
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


def build_prompt(topic: str, platform: str, *, product: str = "", extra: str = "",
                 source_text: str = "") -> str:
    style = PLATFORMS.get(platform)
    if not style:
        raise ValueError(f"不支持的平台：{platform}。可选：{', '.join(PLATFORMS)}")

    parts = [
        f"平台：{style.name}",
        f"写作要求：{style.guide}",
        "",
        f"主题：{topic}",
    ]
    if source_text:
        parts += [
            "",
            "以下是抓到的原文，**必须以它为事实依据改写**：",
            '"""',
            source_text[:4000],
            '"""',
            "改写要求：保留原文的事实、数字、专有名词、当事人；"
            "重新组织语言和切入角度，写成符合平台风格的内容；"
            "**原文没有的信息不要添加**。",
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
        "**必须照写，不要交白卷。**",
        "如果主题跟你手上的材料对不上、或者有些细节你不确定：",
        "- 照样写出一篇完整的稿子",
        "- 但把推测的部分写得克制，别编造具体数字、日期、品牌事件",
        "- 在 gaps 字段里逐条列出「这篇里哪些地方我没有依据」",
        "不要因为缺材料就拒绝，也不要为了凑数编造事实。写你能写的，标出你虚的地方。",
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
    source_text: str = "",
    use_polish: bool = True,
) -> dict[str, Any]:
    if not cfg.has_model:
        raise ModelError(
            "没有配置文本模型。去 config.toml 的 [model] 填 api_key（中转站也行）。"
        )
    if not topic.strip():
        raise ValueError("主题不能为空")

    style = PLATFORMS[platform]
    # 没指定商品时，用账号定位里的商品当背景（只是背景信息，不影响写什么主题）
    if not product:
        brand = getattr(cfg, "brand", None)
        if brand and brand.product.strip():
            product = brand.product

    client = OpenAICompatible(
        base_url=cfg.model.base_url,
        api_key=cfg.model.api_key,
        timeout=max(cfg.model.timeout, 120),
        text_model=cfg.model.text_model,
    )

    prompt = build_prompt(topic, platform, product=product, extra=extra, source_text=source_text)
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
    gaps = [str(g).strip() for g in (data.get("gaps") or []) if str(g).strip()]

    if not title or not body:
        raise ModelError(
            "模型这次什么都没写出来。\n"
            f"它说：{notes or '（没说明）'}\n\n"
            "再跑一次，或者给一点更具体的信息。"
        )

    tags = [str(t).strip().lstrip("#") for t in (data.get("tags") or []) if str(t).strip()]

    if use_polish:
        body = polish(body, platform, cfg)

    warnings: list[str] = []
    if gaps:
        warnings.append("这篇里有 %d 处没有依据，建议核实：" % len(gaps))
        warnings.extend(gaps)
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
