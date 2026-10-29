"""按平台 skill 改写。

skill 是 skills/*.md 文件，直接当 system prompt 用。
想改风格、加禁词、调结构，改 md 就行，不用碰代码。
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from ..model.client import ModelError, OpenAICompatible

SKILL_DIR = Path(__file__).parent / "skills"
DEFAULT_SKILL = "小红书"

# 各平台的硬限制。skill 里写了，代码也兜一层，防止模型不听话。
TITLE_LIMITS = {
    "小红书": 20, "头条": 30, "百家号": 30,
    "抖音": 30, "快手": 28, "知乎": 45, "微博": 20, "B站": 35, "视频号": 25,
}
TAG_LIMITS = {
    "小红书": 8, "头条": 5, "百家号": 5,
    "抖音": 5, "快手": 4, "知乎": 5, "微博": 2, "B站": 10, "视频号": 3,
}

# 正文字数区间。模型经常写超（实测小红书 955/上限 800、头条 1554/上限 1200），
# 所以超了要让它自己压一遍，别直接截断——截断会把结构切坏。
BODY_RANGE = {
    "小红书": (300, 800), "头条": (900, 1200), "百家号": (800, 1200),
    "抖音": (120, 300), "快手": (150, 300), "知乎": (800, 1500),
    "微博": (140, 280), "B站": (100, 300), "视频号": (120, 250),
}

# 所有平台通用的硬规则。代码追加在 skill 后面：
# 这样 9 个 skill 各自写风格，底线只维护一处，改 skill 也覆盖不掉它。
SHARED_RULES = """

---

## 附：所有平台通用硬规则（代码追加，优先级高于上面的风格要求）

- **禁用广告法极限词**：最强、最好、最佳、第一、唯一、独家、绝对、100%、
  史上、国家级、世界级、顶级、极致。要表达领先就写具体数字和口径。
- **数字只能来自原文**。原文没给的数字一个都不许编，包括"约""大概"。
- **没做过的经历不许写成做过的**。宁可少一句亲历，也不要编一句。
- **gaps 必须如实填写**：推测、常识补全、原文没说的地方，全写进去。
- 输出必须是合法 JSON，不要代码围栏。
"""

# 广告法极限词。skill 里写了、SHARED_RULES 里也写了，模型还是偶尔漏，
# 所以生成后本地再查一遍，命中就让模型定点改掉。
EXTREME_WORDS = [
    "最强", "最好", "最佳", "最便宜", "最划算", "第一品牌", "全网第一",
    "唯一", "独家", "绝对", "100%", "百分之百", "史上", "国家级",
    "世界级", "顶级", "极致", "万能",
]

CLEAN_PROMPT = """下面这篇 {platform} 文案的正文里出现了这些广告法极限词：{hits}

请**只改用了这些词的那几句**：
- 换成具体、可核查的表述（写数字、写口径、写实测、写对比）
- 不许换成另一个极限词
- 其余内容一个字都不要动，不要新增事实

正文：
\"\"\"
{body}
\"\"\"

按原来的 JSON 格式输出，title 沿用原标题。
"""

RESIZE_PROMPT = """下面这篇 {platform} 文案的正文是 {current} 字，但平台要求 **{low}–{high} 字**。

请改写一版，把正文控制到 {low}–{high} 字之间。

规则：
- **骨架不动**：段落顺序、论点顺序、开头钩子都不要变
- **事实不动**：数字、公司名、专有名词一个字都不能改，也不许加新的
- **只动表达**：{action}，不要新增信息
- 依然遵守原来那份 skill 的所有要求（禁词、人称、emoji、标题规则）

原正文：
\"\"\"
{body}
\"\"\"

按原来的 JSON 格式输出，title 可以沿用原文标题。
"""


def _ask(client: OpenAICompatible, prompt: str, system: str, **kwargs: Any) -> str:
    """调用模型，网络类失败重试。

    中转站对大输出偶发超时（实测 B站/视频号 那两次 read timeout），
    这类错误重试一次基本能过；4xx 这种业务错误不重试。
    """
    transient = ("timed out", "timeout", "connection", "eof", "502", "503", "504")
    last: Exception | None = None
    for i in range(3):
        try:
            return client.ask(prompt, system=system, **kwargs)
        except ModelError as exc:
            msg = str(exc).lower()
            if not any(key in msg for key in transient):
                raise
            last = exc
            time.sleep(1.5 * (i + 1))
    raise ModelError(f"连试 3 次都失败：{str(last)[:150]}")


def _close_truncated(text: str) -> str:
    """给被截断的 JSON 补上收尾引号和括号，能救回一部分。"""
    out = text.rstrip()
    if out.count('"') % 2 == 1:
        out += '"'
    opens = out.count("{") - out.count("}")
    if opens > 0:
        out += "]" * max(0, out.count("[") - out.count("]"))
        out += "}" * opens
    return out


def _loads_loose(text: str) -> tuple[dict, bool]:
    """先把模型输出当 JSON 读，读不动就用正则硬抠。

    中转站偶发把长输出截断（实测头条那篇 JSON 到 1800 字符就断了），
    这种情况不该整篇作废——标题和正文大部分是好的，抠出来比报错有用。
    返回 (数据, 是否被截断过)。
    """
    txt = _strip_fence(text)
    for candidate in (txt, _close_truncated(txt)):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data, candidate != txt
        except json.JSONDecodeError:
            pass

    data: dict = {}
    m = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', txt)
    if m:
        try:
            data["title"] = json.loads(f'"{m.group(1)}"')
        except json.JSONDecodeError:
            data["title"] = m.group(1)

    m = re.search(r'"body"\s*:\s*"(.*)$', txt, re.S)
    if m:
        body = re.split(r'"\s*,\s*"(?:tags|gaps)"', m.group(1))[0]
        body = body.rstrip().rstrip('"')
        try:
            data["body"] = json.loads(f'"{body}"')
        except json.JSONDecodeError:
            data["body"] = body.replace("\\n", "\n").replace('\\"', '"')

    return data, True


def _smart_truncate(text: str, limit: int) -> str:
    """按字数截断，但不要砍在词中间。

    优先在中文标点处断；没有标点再退到空格，并丢掉结尾那个悬空的短片段
    （实测「Terminal-Bench 4.0 拿 41%，输出 token 少 30%」会被截成
    「…41%，输出」，读着像半句话）。
    """
    if len(text) <= limit:
        return text
    head = text[:limit]
    floor = max(1, int(limit * 0.6))

    for marks in ("，。、；：！？", ",.;:!?"):
        for i in range(len(head) - 1, floor, -1):
            if head[i] in marks:
                return head[:i].rstrip()

    for i in range(len(head) - 1, floor, -1):
        if head[i] == " ":
            cut = head[:i].rstrip()
            dangling = re.search(r"[，。、；：！？,.;:!?]\s*\S{1,3}$", cut)
            if dangling:
                cut = cut[: dangling.start()].rstrip()
            return cut

    return head


def list_skills() -> list[str]:
    if not SKILL_DIR.is_dir():
        return []
    return sorted(p.stem for p in SKILL_DIR.glob("*.md"))


def load_skill(name: str = DEFAULT_SKILL) -> str:
    path = SKILL_DIR / f"{name}.md"
    if not path.is_file():
        available = "、".join(list_skills()) or "（没有）"
        raise FileNotFoundError(f"没有这个 skill：{name}。可选：{available}")
    return path.read_text(encoding="utf-8")


def _strip_fence(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return (fenced.group(1) if fenced else text).strip()


def build_user_prompt(topic: str, source_text: str, *, extra: str = "") -> str:
    parts = [
        f"主题：{topic}",
        "",
    ]
    if source_text:
        parts += [
            "下面是原文，**改写必须以它为事实依据**：",
            '"""',
            source_text[:5000],
            '"""',
            "",
            "改写要求：",
            "- 原文里的事实、数字、专有名词、当事人姓名要保留准确",
            "- 重新组织语言和切入角度，不要照抄原文句子",
            "- **原文没有的信息不要添加**；不确定的写进 gaps",
        ]
    else:
        parts += ["（没有原文，只能凭主题写。这种情况下要格外克制，不要编造具体事实。）"]

    if extra:
        parts += ["", f"补充要求：{extra}"]

    parts += ["", "按 skill 里规定的 JSON 格式输出。"]
    return "\n".join(parts)


def _fit_length(
    client: OpenAICompatible,
    system: str,
    body: str,
    platform: str,
    low: int,
    high: int,
    gaps: list[str],
) -> str:
    """把正文压/扩进平台的字数区间。

    优先让模型自己改（保留结构和事实），改不动再硬截并留一条 gap。
    """
    over = len(body) > high
    action = (
        f"删掉重复表达、铺垫和多余的修饰，压掉 {len(body) - high} 字左右"
        if over else
        f"补上 {low - len(body)} 字左右，优先补原文里有、但正文漏掉的细节"
    )
    try:
        raw = _ask(
            client,
            RESIZE_PROMPT.format(
                platform=platform, current=len(body), low=low, high=high,
                action=action, body=body,
            ),
            system, max_tokens=8000, temperature=0.5,
        )
        candidate = str(_loads_loose(raw)[0].get("body") or "").strip()
        if candidate and candidate != body:
            body = candidate
    except ModelError:
        pass

    if len(body) > high:
        body = _smart_truncate(body, high)
        gaps.append(f"正文超过 {platform} 的字数上限（{high} 字），已截断，结尾可能不完整")
    return body


def _clean_extremes(
    client: OpenAICompatible,
    system: str,
    body: str,
    platform: str,
    gaps: list[str],
) -> str:
    """把广告法极限词定点改掉。

    这些词是硬违规（平台下架的那种），交给审核拦是最后一道，不该是第一道。
    """
    hits = [w for w in EXTREME_WORDS if w in body]
    if not hits:
        return body

    try:
        raw = _ask(
            client,
            CLEAN_PROMPT.format(platform=platform, hits="、".join(hits), body=body),
            system, max_tokens=8000, temperature=0.3,
        )
        candidate = str(_loads_loose(raw)[0].get("body") or "").strip()
        if candidate:
            body = candidate
    except ModelError:
        pass

    left = [w for w in EXTREME_WORDS if w in body]
    if left:
        gaps.append("正文里还有极限词没清掉：" + "、".join(left) + "（审核会拦，建议手改）")
    return body


def rewrite(
    topic: str,
    source_text: str,
    cfg: Any,
    *,
    platform: str = DEFAULT_SKILL,
    extra: str = "",
) -> dict[str, Any]:
    if not cfg.has_model:
        raise ModelError("没有配置文本模型，去 config.toml 的 [model] 填 api_key")

    if not topic.strip():
        raise ValueError("主题不能为空")

    system = load_skill(platform) + SHARED_RULES

    client = OpenAICompatible(
        base_url=cfg.model.base_url,
        api_key=cfg.model.api_key,
        timeout=max(cfg.model.timeout, 240),
        text_model=cfg.model.text_model,
    )

    prompt = build_user_prompt(topic, source_text, extra=extra)
    raw = _ask(client, prompt, system, max_tokens=8000, temperature=0.8)
    data, truncated = _loads_loose(raw)

    if not (str(data.get("title") or "").strip() and str(data.get("body") or "").strip()):
        raw = _ask(
            client,
            prompt + "\n\n上次输出不完整或不是合法 JSON。这次只输出完整的 JSON 对象，不要任何解释。",
            system, max_tokens=8000, temperature=0.3,
        )
        data, truncated = _loads_loose(raw)
        if not str(data.get("body") or "").strip():
            raise ModelError(f"模型两次都没返回可用的正文：{raw[:300]}")

    title = str(data.get("title") or "").strip()
    body = str(data.get("body") or "").strip()
    if not title or not body:
        raise ModelError("模型没有产出标题或正文")

    tags = [str(t).strip().lstrip("#") for t in (data.get("tags") or []) if str(t).strip()]
    gaps = [str(g).strip() for g in (data.get("gaps") or []) if str(g).strip()]
    if truncated:
        gaps.append("模型输出被中转站截断过，标签和 gaps 可能不完整，发布前核对结尾")

    # 字数越界就让模型自己压/扩一遍。硬截会把结构切坏，所以只在它压不下来时兜底。
    low, high = BODY_RANGE.get(platform, (0, 10 ** 6))
    if not (low <= len(body) <= high):
        body = _fit_length(
            client, system, body, platform, low, high, gaps,
        )

    # 极限词是硬违规，生成后本地再清一遍
    body = _clean_extremes(client, system, body, platform, gaps)

    # 清极限词时可能改动字数，再校一次区间
    if not (low <= len(body) <= high):
        body = _fit_length(client, system, body, platform, low, high, gaps)

    title_limit = TITLE_LIMITS.get(platform, 30)
    tag_limit = TAG_LIMITS.get(platform, 5)

    if len(title) > title_limit:
        title = _smart_truncate(title, title_limit)

    # 本地兜底检查：skill 里列的禁词，模型偶尔还是漏
    banned = ["此外", "至关重要", "赋能", "助力", "总的来说", "综上所述",
              "值得注意的是", "由此可见", "不可或缺", "全方位", "旨在",
              "说白了", "本质上", "众所周知"]
    hits = [w for w in banned if w in body]
    if hits:
        gaps.append("正文里还有 AI 腔词没清掉：" + "、".join(hits))

    return {
        "platform": platform,
        "topic": topic,
        "title": title,
        "body": body,
        "tags": tags[:tag_limit],
        "gaps": gaps,
        "length": len(body),
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# {result['title']}",
        "",
        f"平台：{result['platform']}　字数：{result['length']}",
        "",
        result["body"],
        "",
    ]
    if result["tags"]:
        lines += [" ".join(f"#{t}" for t in result["tags"]), ""]
    if result.get("gaps"):
        lines += ["## 没依据的地方", ""]
        lines += [f"- {g}" for g in result["gaps"]]
        lines.append("")
    return "\n".join(lines)
