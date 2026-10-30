"""AI 审核：发文前先过一遍。

两层，缺一不可：

    规则层   固定禁词表。命中即拦截，不依赖模型，稳定可解释。
    AI 层    判断夸大、虚假、误导、与事实不符。模型擅长这个，但会飘，所以只做建议。

为什么规则层要独立：模型有时候会"体谅"你的营销话术，说"还行"。
但平台审核不讲情面，命中极限词就是违规。这条不能交给模型判断。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .model.client import ModelError, OpenAICompatible

SYSTEM = (
    "你是内容合规审核员。只判断，不改写。"
    "发现夸大、虚假、误导、无法证实的表述就指出，不要替作者圆场。"
    "输出必须是合法 JSON，不要代码围栏。"
)


def _strip_fence(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return (fenced.group(1) if fenced else text).strip()


# --------------------------------------------------------------- 规则层

# 结构：(类别, 词/短语, 建议)
# 用短语而不是单字——「最」会误伤「最后」「最近」，必须具体。
RULES: list[tuple[str, str, str]] = [
    # 广告法极限词
    ("极限词", "最好", "改成具体描述，比如「我用下来更顺手」"),
    ("极限词", "最佳", "改成具体描述"),
    ("极限词", "最强", "改成具体描述"),
    ("极限词", "最低价", "改成「这个价位」并给出实际价格"),
    ("极限词", "最便宜", "改成「我买到的是 xx 元」"),
    ("极限词", "最划算", "改成具体对比"),
    ("极限词", "第一品牌", "删掉，无法证实"),
    ("极限词", "全网第一", "删掉，无法证实"),
    ("极限词", "顶级", "改成具体材质或工艺"),
    ("极限词", "极致", "改成具体感受"),
    ("极限词", "唯一", "删掉或改成「我找到的」"),
    ("极限词", "独家", "删掉，除非有授权"),
    ("极限词", "国家级", "删掉，需资质"),
    ("极限词", "世界级", "删掉，无法证实"),
    ("极限词", "100%", "改成「基本」或给出实测数据"),
    ("极限词", "百分之百", "改成「基本」或给出实测数据"),
    ("极限词", "绝对", "删掉"),
    ("极限词", "永久", "改成具体时长"),
    ("极限词", "彻底", "改成具体效果"),
    ("极限词", "万能", "删掉"),
    ("极限词", "史上", "删掉"),

    # 医疗功效（普通商品不能宣称）
    ("医疗功效", "治愈", "普通商品不得宣称疗效，删掉"),
    ("医疗功效", "治疗", "普通商品不得宣称疗效，删掉"),
    ("医疗功效", "根治", "普通商品不得宣称疗效，删掉"),
    ("医疗功效", "消炎", "普通商品不得宣称疗效，删掉"),
    ("医疗功效", "杀菌", "需检测报告，否则删掉"),
    ("医疗功效", "抗病毒", "需资质，删掉"),
    ("医疗功效", "医用", "需资质，删掉"),
    ("医疗功效", "无副作用", "删掉，无法证实"),
    ("医疗功效", "包治", "删掉"),

    # 虚假承诺
    ("虚假承诺", "立竿见影", "改成具体周期，比如「用了两周」"),
    ("虚假承诺", "立刻见效", "改成具体周期"),
    ("虚假承诺", "一用就", "改成具体体验"),
    ("虚假承诺", "永不", "改成具体时长"),
    ("虚假承诺", "终身", "删掉或写清保修期"),
    ("虚假承诺", "无效退款", "删掉，属于承诺"),

    # 站外导流（平台最敏感）
    ("站外导流", "加微信", "平台禁止导流，删掉"),
    ("站外导流", "加v", "平台禁止导流，删掉"),
    ("站外导流", "私聊", "平台禁止导流，删掉"),
    ("站外导流", "vx", "平台禁止导流，删掉"),
    ("站外导流", "薇信", "平台禁止导流，删掉"),
    ("站外导流", "扫码", "平台禁止导流，删掉"),
    ("站外导流", "点击链接", "平台禁止站外链接，删掉"),
    ("站外导流", "点击领取", "改成平台内动作"),

    # 诱导互动
    ("诱导互动", "转发抽奖", "平台限制，改成自然互动"),
    ("诱导互动", "点赞送", "平台限制，删掉"),
    ("诱导互动", "关注领取", "平台限制，删掉"),
    ("诱导互动", "评论区扣", "改成自然提问"),

    # 金融
    ("金融违规", "稳赚", "删掉"),
    ("金融违规", "保本", "删掉"),
    ("金融违规", "零风险", "删掉"),
    ("金融违规", "躺赚", "删掉"),
    ("金融违规", "高收益", "删掉或标明风险"),

    # 迷信
    ("封建迷信", "转运", "平台限流词，慎用"),
    ("封建迷信", "招财", "平台限流词，慎用"),
    ("封建迷信", "辟邪", "平台限流词，慎用"),
    ("封建迷信", "开光", "删掉"),
    ("封建迷信", "风水", "慎用"),
]

# 平台额外重点
PLATFORM_FOCUS = {
    "xiaohongshu": ["站外导流", "诱导互动"],
    "zhihu": ["极限词", "虚假承诺"],
    "baijiahao": ["极限词", "虚假承诺", "医疗功效"],
    "dayu": ["极限词", "虚假承诺"],
    "douyin": ["站外导流", "诱导互动", "极限词"],
}


@dataclass
class Issue:
    level: str      # block 拦截 / warn 提醒
    kind: str
    text: str
    advice: str = ""

    def as_dict(self) -> dict:
        return {"level": self.level, "kind": self.kind, "text": self.text, "advice": self.advice}


@dataclass
class ReviewResult:
    platform: str
    passed: bool = True
    score: int = 100
    issues: list[Issue] = field(default_factory=list)
    summary: str = ""
    ai_used: bool = False
    claims_checked: int = 0

    def as_dict(self) -> dict:
        return {
            "platform": self.platform,
            "passed": self.passed,
            "score": self.score,
            "issues": [i.as_dict() for i in self.issues],
            "summary": self.summary,
            "ai_used": self.ai_used,
            "claims_checked": self.claims_checked,
        }


def rule_check(text: str, platform: str = "") -> list[Issue]:
    lowered = text.lower()
    found: list[Issue] = []
    seen: set[str] = set()

    focus = PLATFORM_FOCUS.get(platform, [])

    for kind, word, advice in RULES:
        needle = word.lower()
        if needle in lowered and word not in seen:
            seen.add(word)
            level = "block" if (kind in focus or kind in ("医疗功效", "站外导流", "金融违规")) else "warn"
            found.append(Issue(level=level, kind=kind, text=word, advice=advice))

    return found


# --------------------------------------------------------------- AI 层

AI_SCHEMA = """{
  "score": 0-100 的整数,
  "issues": [
    {"level": "block 或 warn", "kind": "问题类型", "text": "原文里的句子", "advice": "怎么改"}
  ],
  "summary": "一句话总评，不超过 40 字"
}"""


# --------------------------------------------------------------- 断言级核查
#
# 学 n8n 模板 20543 的做法：不是把整段丢给模型问"有没有问题"，
# 而是先把文稿拆成一条条**可核查的断言**，再逐条判断。
# 整段提问模型容易"体谅"作者，逐条核查会诚实得多。

CLAIM_SCHEMA = """{
  "claims": ["断言1", "断言2", "断言3"]
}"""

CLAIM_PROMPT = """把下面这段文案里**可被核查的事实性表述**拆出来。

只拆这几类：
- 具体数字（时长、价格、尺寸、百分比、数量）
- 效果承诺（能干什么、多久见效、有什么作用）
- 材质、成分、产地、认证
- 对比结论（比别人好、比同类便宜）
- 用户反馈、销量、评价

**绝对不要拆**（这些不是断言，判了也是噪音）：
- 主观感受：「房间的感觉就变了」「人容易静下来」「闻着舒服」
- 修辞和比喻：「像有人在旁边陪着」
- 场景描写：「加班回来进门第一件事是扔包」
- 提问和引导：「你晚上会点什么」
- 肉眼可见的外观描述：「杯子是渐变的」「火苗是黄色的」——这类看照片就知道
- 个人偏好：「我选的是木质款」「我不喜欢太甜的」

如果文案里没有可核查的事实性表述，claims 返回空数组。宁可少拆，不要凑数。

最多 10 条。每条是原文的一句话或半句话，保持原样不要改写。

文案：
\"\"\"
{text}
\"\"\"

按这个 JSON 输出：
{schema}
"""

VERDICTS = ("属实", "存疑", "无法证实", "夸大", "主观")

CLAIM_CHECK_SCHEMA = """{
  "results": [
    {"claim": "原文断言", "verdict": "属实 或 存疑 或 无法证实 或 夸大 或 主观",
     "reason": "一句话理由", "advice": "怎么改；属实或主观就留空"}
  ]
}"""

CLAIM_CHECK_PROMPT = """逐条判断下面这些表述能不能站得住。

先分清两类：
- **主观**：个人感受、偏好、比喻、场景描写。这类不需要证据，判「主观」。
- **事实性断言**：数字、材质、效果承诺、对比结论。这类要证据。

对事实性断言，按这个标准判：
- 属实：常识或普遍事实；**或者在下面给的原文里能找到直接依据**
- 存疑：可能对，但缺依据，需要作者提供来源/检测/实测
- 无法证实：涉及具体数据，**原文里也没有**，也没有任何来源
- 夸大：明显超出合理范围，或把普通商品说成功效产品

保守一点。事实性断言拿不准就判「存疑」，不要替作者找理由。
但**不要把主观感受判成问题** —— 那是在制造噪音。
**也不要把原文里明确写了的事实判成无法证实** —— 那是在制造假警报。

文案背景：发在{platform}

{source_block}

待判断：
{claims}

按这个 JSON 输出：
{schema}
"""

SOURCE_BLOCK = """原文（改写依据，逐条比对）：
\"\"\"
{source}
\"\"\"

**判断时先在这里面找：**
- 找到了就直接判「属实」，不要因为"看起来像具体数据"就判无法证实
- 但**数字对得上 ≠ 表述正确**。要看语义。例如原文写 95% off（只付 5%），
  改写成「打 95 折」（只便宜 5%），数字都含 95，意思却反了 —— 这种要判「存疑」并指出
- 原文没有的，才判「无法证实」
"""


def _loads_loose(text: str) -> dict:
    """读模型返回的 JSON，截断了就尽量救回来。

    中转站偶发把长输出截断，一次核查格式异常不该让整篇稿子判不过。
    """
    body = _strip_fence(text)
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    fixed = body.rstrip()
    if fixed.count('"') % 2 == 1:
        fixed += '"'
    opens = fixed.count("{") - fixed.count("}")
    if opens > 0:
        fixed += "]" * max(0, fixed.count("[") - fixed.count("]")) + "}" * opens
    try:
        data = json.loads(fixed)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {}


def extract_claims(text: str, cfg: Any) -> list[str]:
    client = OpenAICompatible(
        base_url=cfg.model.base_url,
        api_key=cfg.model.api_key,
        timeout=max(cfg.model.timeout, 120),
        text_model=cfg.model.text_model,
    )
    raw = client.ask(
        CLAIM_PROMPT.format(text=text[:4000], schema=CLAIM_SCHEMA),
        system=SYSTEM, max_tokens=1500, temperature=0.2,
    )
    data = _loads_loose(raw)

    claims = [str(c).strip() for c in (data.get("claims") or []) if str(c).strip()]
    return claims[:10]


def check_claims(claims: list[str], platform: str, cfg: Any, *, source_text: str = "") -> list[Issue]:
    if not claims:
        return []

    client = OpenAICompatible(
        base_url=cfg.model.base_url,
        api_key=cfg.model.api_key,
        timeout=max(cfg.model.timeout, 120),
        text_model=cfg.model.text_model,
    )
    listed = "\n".join(f"{i}. {c}" for i, c in enumerate(claims, 1))

    if source_text.strip():
        # 给足原文。实测截断到 4000 字会把尾部定价那段切掉，导致误判
        source_block = SOURCE_BLOCK.format(source=source_text[:12000])
    else:
        source_block = "（没有提供原文，只能凭常识判断。具体数字要格外严格。）"

    prompt = CLAIM_CHECK_PROMPT.format(
        platform=platform, claims=listed,
        source_block=source_block, schema=CLAIM_CHECK_SCHEMA,
    )
    data = _loads_loose(client.ask(prompt, system=SYSTEM, max_tokens=2500, temperature=0.2))
    if not data.get("results"):
        # 截断或格式坏过一次，重问一次；两次都不行才当「没核查上」
        data = _loads_loose(client.ask(
            prompt + "\n\n上次输出无法解析。这次只输出完整的 JSON，不要解释，不要省略。",
            system=SYSTEM, max_tokens=3000, temperature=0.2,
        ))
    if not data.get("results"):
        return [Issue(level="warn", kind="核查失败", text="",
                      advice="断言核查两次都没返回可用结果，建议人工复核")]

    issues: list[Issue] = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        verdict = str(item.get("verdict") or "").strip()
        if verdict not in VERDICTS:
            verdict = "存疑"
        # 属实和主观的不用报，省的刷屏
        if verdict in ("属实", "主观"):
            continue
        # 「无法证实」和「夸大」直接拦：编造销量/好评率/检测数据是虚假宣传
        issues.append(Issue(
            level="block" if verdict in ("夸大", "无法证实") else "warn",
            kind=f"断言·{verdict}",
            text=str(item.get("claim") or ""),
            advice=str(item.get("advice") or item.get("reason") or ""),
        ))
    return issues


def _ai_prompt(text: str, platform: str) -> str:
    return f"""审核下面这段准备发到「{platform}」的文案。

只审这些：
1. 有没有夸大、绝对化、无法证实的表述
2. 有没有编造数据、销量、评价、检测结果
3. 有没有把普通商品说成有医疗/保健功效
4. 有没有平台明确禁止的导流或诱导互动
5. 有没有明显的虚假宣传

不审错别字、不审文风、不审排版。

文案：
\"\"\"
{text[:4000]}
\"\"\"

按这个 JSON 输出：
{AI_SCHEMA}

没问题就返回 score 90 以上、issues 空数组。
"""


def ai_check(text: str, platform: str, cfg: Any) -> tuple[list[Issue], int, str]:
    client = OpenAICompatible(
        base_url=cfg.model.base_url,
        api_key=cfg.model.api_key,
        timeout=max(cfg.model.timeout, 120),
        text_model=cfg.model.text_model,
    )
    raw = client.ask(_ai_prompt(text, platform), system=SYSTEM, max_tokens=2000, temperature=0.2)

    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    body = (fenced.group(1) if fenced else raw).strip()

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return [], 70, "AI 审核返回格式异常，建议人工复核"

    issues: list[Issue] = []
    for item in data.get("issues") or []:
        if not isinstance(item, dict):
            continue
        issues.append(Issue(
            level="block" if str(item.get("level")) == "block" else "warn",
            kind=str(item.get("kind") or "AI 判断"),
            text=str(item.get("text") or ""),
            advice=str(item.get("advice") or ""),
        ))

    try:
        score = int(data.get("score") or 70)
    except (TypeError, ValueError):
        score = 70

    return issues, max(0, min(100, score)), str(data.get("summary") or "")


# --------------------------------------------------------------- 主流程


POLICY_PROMPT = """你是政策审校。逐条核对下面这段「政策解读」有没有把原文写歪。

只查四件事，别的不查：
1. **数字**：有没有被放大、折算错（月→年、含不含补贴、税前税后）
2. **限定条件**：原文里的「参加XX的 / 仅限 / 最高 / 不超过 / 年满」是不是还在
   —— 漏掉限定条件是最常见的误导，重点查这个
3. **因果**：原文说「A 的同时出现了 B」，不能写成「A 导致 B」
4. **无中生有**：有没有把原文没说的内容写成事实

原文：
\"\"\"
{source}
\"\"\"

解读：
\"\"\"
{text}
\"\"\"

按这个 JSON 输出：
{{"problems": [{{"quote": "解读里的原句", "problem": "属于上面哪一类", "fix": "怎么改"}}]}}

没问题就返回 {{"problems": []}}。
"""


def check_policy(text: str, cfg: Any, *, source_text: str = "") -> list[Issue]:
    """政策解读专用：口径核对 + 限定条件检查。

    这一层不判文风、不判禁词（那是别的层干的），只查「有没有把政策说歪」。
    """
    if not source_text.strip():
        return [Issue(level="block", kind="政策·无原文",
                      text="", advice="政策解读必须带原文出处；没有原文无法核对口径，先补原文再写")]

    client = OpenAICompatible(
        base_url=cfg.model.base_url,
        api_key=cfg.model.api_key,
        timeout=max(cfg.model.timeout, 150),
        text_model=cfg.model.text_model,
    )
    prompt = POLICY_PROMPT.format(source=source_text[:12000], text=text[:6000])
    data = _loads_loose(client.ask(prompt, system=SYSTEM, max_tokens=2500, temperature=0))
    if not data.get("problems"):
        return []

    issues: list[Issue] = []
    for item in data.get("problems") or []:
        if not isinstance(item, dict):
            continue
        issues.append(Issue(
            level="block",
            kind="政策·口径",
            text=str(item.get("quote") or "")[:80],
            advice=f"{item.get('problem', '')}；{item.get('fix', '')}"[:120],
        ))
    return issues


def review(text: str, platform: str, cfg: Any, *, use_ai: bool = True,
           source_text: str = "", mode: str = "") -> ReviewResult:
    """规则层 + 断言级核查。

    断言级是主力：先把文稿拆成可核查的事实性表述，逐条判「属实/存疑/无法证实/夸大」。
    这比"整段问模型有没有问题"准得多 —— 整段问的时候模型容易替作者说话。
    """
    if not text.strip():
        raise ValueError("没有内容可审")

    result = ReviewResult(platform=platform)
    result.issues = rule_check(text, platform)

    if use_ai and cfg.has_model:
        try:
            claims = extract_claims(text, cfg)
            result.claims_checked = len(claims)
            result.issues.extend(check_claims(claims, platform, cfg, source_text=source_text))
            if mode == "政策解读":
                result.issues.extend(check_policy(text, cfg, source_text=source_text))
            result.ai_used = True
        except ModelError as exc:
            result.summary = f"AI 核查不可用（{str(exc)[:60]}），仅规则层结果"

    blocks = [i for i in result.issues if i.level == "block"]
    warns = [i for i in result.issues if i.level != "block"]

    score = 100 - 40 * len(blocks) - 8 * len(warns)
    result.score = max(0, min(100, score))

    # 规则层或断言层命中 block 就直接否
    result.passed = not blocks and result.score >= 70

    if not result.summary:
        if not result.issues:
            result.summary = f"未发现问题（核查了 {result.claims_checked} 条断言）" if result.ai_used else "规则层未命中"
        else:
            result.summary = f"命中 {len(blocks)} 处必改、{len(warns)} 处建议改"

    return result


def render_markdown(result: ReviewResult) -> str:
    status = "✅ 通过" if result.passed else "❌ 不通过"
    ai_note = f"（AI 核查 {result.claims_checked} 条断言）" if result.ai_used else "（仅规则层）"
    lines = [
        f"# 审核结果 · {result.platform}",
        "",
        f"**{status}**　评分 {result.score}/100　{ai_note}",
        "",
        result.summary,
        "",
    ]

    if not result.issues:
        lines += ["没有发现问题。", ""]
        return "\n".join(lines)

    blocks = [i for i in result.issues if i.level == "block"]
    warns = [i for i in result.issues if i.level != "block"]

    if blocks:
        lines += ["## 必须改", "", "| 类型 | 命中 | 建议 |", "|---|---|---|"]
        for i in blocks:
            lines.append(f"| {i.kind} | {i.text} | {i.advice} |")
        lines.append("")

    if warns:
        lines += ["## 建议改", "", "| 类型 | 命中 | 建议 |", "|---|---|---|"]
        for i in warns:
            lines.append(f"| {i.kind} | {i.text} | {i.advice} |")
        lines.append("")

    return "\n".join(lines)
