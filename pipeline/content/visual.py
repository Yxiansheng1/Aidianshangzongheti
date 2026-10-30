"""配图：从文案里提取画面，再用 SDXL 文生图。

两条路都支持：
    plan()   让模型从文案里挑最值得配的画面，输出英文 SDXL 提示词
    render() 用 text2img 逐张出图

不抓原文配图（版权风险），只走纯文生图。

## 两条硬规矩（之前踩过的坑）

1. **主体来自文案，不来自风格。**
   上一版把所有图都锁成「桌面 / 书本 / 杯子 / 植物 / 暖光」，结果讲电路板打样的
   文章配出「窗台绿植」。风格只能约束镜头和光，不能约束题材。

2. **每张图必须挂到文案里的一句原话。**
   `anchor` 字段是文案的原文片段，本地会核对它真的出现在正文里；
   对不上就丢掉这一张，不给它发表格样的机会。这就是 grounding。

3. 出图后用视觉模型核对一次：图里到底有没有那个主体。
   对不上就重写提示词重出一张。核对失败（网络/不支持）不阻塞，只标「未核对」。
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from ..model.client import ModelError, OpenAICompatible
from ..model.comfyui import ComfyClient
from ..text2img import Text2ImgConfig, generate

SYSTEM = "你是视觉策划。只输出 JSON，不要代码围栏，不要解释。"

# 只约束「镜头语言」，不约束题材。
# 上一版这里写了 cozy lived-in interior / everyday objects / 桌面书本杯子植物，
# 结果任何题材都被拉回「暖光书桌绿植」。风格后缀不该规定画什么。
CAMERA_SUFFIX = (
    ", natural available light, shot on 35mm film, shallow depth of field, "
    "true-to-life muted colors, slightly imperfect framing like a candid photo, "
    "no text, no logo, no watermark"
)

# 负向词只管画质和乱加的文字，不再否定题材。
# 上一版把 corporate / skyscraper / office 写进负向词，等于禁止拍写字楼——
# 可文案讲的就是写字楼里的事。
NEGATIVE = (
    "text, watermark, logo, signature, username, ui screenshot, "
    "lowres, blurry, deformed, extra limbs, jpeg artifacts, worst quality, "
    "oversaturated, plastic look"
)

# 每个平台的画面调性。只影响光、色、构图，不影响画什么。
PLATFORM_TONE = {
    "小红书": "生活化实拍：像在自己家或工位随手拍的，暖光、浅景深、物件有使用痕迹",
    "抖音": "冲击力优先：主体大、对比强、色彩饱和一点，一眼看懂在拍什么",
    "快手": "朴素纪实：普通人的真实环境，不要精致布景，不要滤镜感",
    "知乎": "干净纪实：信息型配图，光线均匀、构图规整，不要情绪化调色",
    "B站": "偏冷调、带屏幕和设备感，构图适合横屏封面",
    "视频号": "明亮稳妥：白天自然光，物件清楚，不用潮流滤镜",
    "百家号": "新闻纪实：现场感、真实环境，不要艺术化处理",
    "头条": "新闻纪实：现场感、真实环境，不要艺术化处理",
}

# 已"实现"过（占比很高的画面）的主体，用来提示模型别偷懒
BANNED_FALLBACK = "桌面摆件、绿植、咖啡杯、摊开的笔记本、纯色背景产品图"

PLAN_PROMPT = """从下面这篇要发**{platform}**的文案里，挑 {n} 个最值得配图的画面。

## 最重要的一条：画面主体必须是文案里真实写到的东西

文案讲电路板打样，主体就是电路板、报价单、工厂工位；
文案讲融资，主体就是会议室桌上的文件、计算器、签约的手；
文案讲写代码，主体就是屏幕上的终端、键盘、线缆。

**不许**把主体替换成「氛围道具」——{banned}。
那些东西本身没错，但它们**不是这篇文案的主体**，放上去就是图文不符。

如果文案的主语是抽象的事（政策、诉讼、并购、争论），
把它落到一个**能拍到的具体场景**，并在 anchor 里指明对应哪句话。

**不要靠画面里的文字传达信息。** 图像模型写不出可读的字，
所以别选「两栏价格的报价单」「写满字的合同」这种必须靠字才能看懂的物件；
换成靠**形状、材质、数量**就能看懂的（计算器、成沓的纸、盖章页、堆叠的样品）。

## 风格只管镜头，不管题材

- 平台调性：{tone}
- 生活化实拍感：像一个人在现场用手机/相机随手拍的
- 自然光、浅景深、真实色彩；不摆拍、不商业摄影棚
- 不出现人脸（可以拍手、背影、局部）
- 风格统一由代码追加，**你不要在 prompt 里写暖光/木桌/绿植这类氛围词**

## 每张图必须做到

- `anchor`：**从正文里原样复制**的一句短语（6-25 字，不要改写、不要加标点变化）。
  这句话要能说明「为什么配这张图」。本地会核对它是否真在正文里，编的会被丢掉。
- `subject`：一句话说这张图**主体是什么**（中文，具体名词）
- `props`：画面里必须出现的 2-4 个物件（中文）
- `prompt`：英文 SDXL 提示词，25-50 词。结构：**主体 + 具体物件 + 场景 + 光线 + 镜头**。
  主体要放最前面、写得最具体（材质、颜色、形状、状态），不要写"a scene about …"。
  **道具要用位置关系写（lying on / beside / behind / in the background）**，
  只堆名词模型会只画主体、把其他东西全丢掉。
  不要写 light、film、bokeh、sharp focus 这类词，风格由代码统一追加。
{ref_section}
文案标题：{title}

文案正文：
\"\"\"
{body}
\"\"\"

按这个 JSON 输出：
{{"scenes": [{{"anchor": "正文里的一句原话", "subject": "主体是什么", "props": ["物件1", "物件2"], "scene": "中文一句话说这张画什么", "prompt": "English SDXL prompt"}}]}}
"""

REVISE_PROMPT = """这几张图**没有画出该有的东西**，现在要修提示词。

{items}

按失败类型改，别一律放大主体：

**A. 缺了某个道具/上下文（最常见）**
不要放大主体，反而要**拉远**：换成俯拍全景或中景，写成
「<道具> 铺在画面下方，<主体> 压在它上面，四周露出白边」这种**位置关系**，
让缺的那个东西在画面里占 20% 以上。只列名词没用，必须写清它和主体的关系。
**别指望画面里的字**——要的是那个物件的形状和数量，不是上面写了什么。

**B. 主体本身错了**
才把主体放到最前面，写成极具体的实体（材质+颜色+形状+状态），占画面一半以上。

**统一要求**
- 25-50 个英文单词
- 不写光线、景深、胶片、画质这些词（代码会统一追加，写了会打架）
- 不要写 studio lighting / sharp focus / bokeh / beautiful lighting
- 不写文字、logo、人脸

按这个 JSON 输出，保持原来的序号：
{{"scenes": [{{"index": 1, "prompt": "English SDXL prompt"}}]}}
"""

CHECK_PROMPT = """看这张图，回答它画的是什么。不要评价画质，不要猜测用途。

判定标准：
- 只看**主体和物件有没有出现**，不看画面里的文字内容（模型写不出可读的字，这不是问题）
- 主体是同一个东西就算匹配，哪怕角度、背景不同
- 如果图里的主体是完全不相干的东西（比如该拍电路板却拍了绿植），判不匹配

按这个 JSON 输出：
{{"main_subject": "画面主体是什么（中文，20 字以内）", "visible": ["看到的物件1", "物件2"], "matches": true, "reason": "为什么算匹配或不匹配（20 字以内）"}}

预期主体：{subject}
它应该支撑这句文案：「{anchor}」
"""


def _norm(text: str) -> str:
    """去掉标点、空格、emoji，只留字母/数字/汉字，用来做原文核对。"""
    return "".join(ch for ch in text if ch.isalnum())


def _grounded(anchor: str, body: str) -> bool:
    """anchor 是不是真的出自正文。

    允许模型少抄一两个字，所以除了全等，还看有没有 8 字窗口命中。
    """
    na, nb = _norm(anchor), _norm(body)
    if len(na) < 5:
        return False
    if na in nb:
        return True
    window = 8
    if len(na) < window:
        return False
    return any(na[i:i + window] in nb for i in range(len(na) - window + 1))


def _strip_fence(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return (fenced.group(1) if fenced else text).strip()


def _client(cfg: Any, *, timeout: int = 120) -> OpenAICompatible:
    if not cfg.has_model:
        raise ModelError("没有配置文本模型")
    return OpenAICompatible(
        base_url=cfg.model.base_url,
        api_key=cfg.model.api_key,
        timeout=max(cfg.model.timeout, timeout),
        text_model=cfg.model.text_model,
    )


def plan(
    title: str,
    body: str,
    cfg: Any,
    *,
    n: int = 2,
    platform: str = "小红书",
    ref_note: str = "",
) -> list[dict[str, Any]]:
    """让模型给出配图方案，并把「没落到原文」的画面剔掉。

    ref_note：原文配图的画面描述（由视觉模型给出）。有它就对齐世界观，
    但明确要求不要复刻构图——照抄一张通讯社图是要出事的。
    """
    client = _client(cfg)

    ref_section = ""
    if ref_note.strip():
        ref_section = (
            "\n## 原文配图里有什么（对齐世界观，不要照抄）\n\n"
            f"> {ref_note.strip()[:200]}\n\n"
            "新图要和这段描述的场景、物件、氛围一致，**但不要复刻构图，也不要画成同一张照片**。\n"
        )

    def ask(extra: str = "") -> list[dict[str, Any]]:
        prompt = PLAN_PROMPT.format(
            n=n, title=title, body=body[:3000],
            platform=platform, banned=BANNED_FALLBACK,
            tone=PLATFORM_TONE.get(platform, PLATFORM_TONE["小红书"]),
            ref_section=ref_section,
        )
        raw = client.ask(
            prompt + extra, system=SYSTEM, max_tokens=1800, temperature=0.6,
        )
        data = json.loads(_strip_fence(raw))
        scenes: list[dict[str, Any]] = []
        for item in data.get("scenes") or []:
            if not isinstance(item, dict):
                continue
            prompt_en = str(item.get("prompt") or "").strip()
            anchor = str(item.get("anchor") or "").strip()
            if prompt_en:
                scenes.append({
                    "anchor": anchor,
                    "subject": str(item.get("subject") or "").strip(),
                    "props": [str(p).strip() for p in (item.get("props") or []) if str(p).strip()],
                    "scene": str(item.get("scene") or "").strip(),
                    "prompt": prompt_en,
                })
        return scenes

    scenes = ask()

    def keep(scene: dict[str, Any]) -> bool:
        return _grounded(scene["anchor"], body)

    good = [s for s in scenes if keep(s)]
    dropped = [s for s in scenes if not keep(s)]

    # 有画面没落到原文：带着具体原因再要一次，这次只补缺的张数
    if len(good) < n and dropped:
        bad = "、".join(f"「{s['anchor'][:18]}」" for s in dropped[:3])
        retry = ask(
            f"\n\n上一次有 {len(dropped)} 个画面挂在正文里找不到的句子上（{bad}）。"
            f"这些已经被丢掉。这次只输出 {n - len(good)} 张，anchor 必须逐字出自正文。"
        )
        good += [s for s in retry if keep(s)]

    # 还不够就保留原文能对上的那些，宁可少一张也不配错图
    return good[:n]


def render_into(
    scene: dict[str, Any],
    target: Path | str,
    cfg: Any,
    *,
    size: tuple[int, int] = (832, 1216),
    steps: int = 20,
    seed: int = 1000,
) -> Path:
    """把一张画面直接画到指定路径。重出同一张时用它，产物目录不会乱。"""
    client = ComfyClient()
    if not client.is_up():
        raise RuntimeError("ComfyUI 没在跑，先启动 启动工作台.bat")

    t2i = Text2ImgConfig(width=size[0], height=size[1], steps=steps)
    out = Path(target)
    prompt = scene["prompt"].rstrip(" .,") + CAMERA_SUFFIX
    generate(client, prompt, out, cfg=t2i, seed=seed, negative=NEGATIVE)
    scene["final_prompt"] = prompt
    scene["file"] = str(out)
    return out


def render(
    scenes: list[dict[str, Any]],
    cfg: Any,
    out_dir: Path | str,
    *,
    prefix: str = "content",
    size: tuple[int, int] = (832, 1216),
    steps: int = 20,
    seed_base: int = 1000,
) -> list[Path]:
    """按方案逐张出图。ComfyUI 没起来就抛错。"""
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)

    return [
        render_into(
            scene, folder / f"{prefix}-{index}.png", cfg,
            size=size, steps=steps, seed=seed_base + index * 1000,
        )
        for index, scene in enumerate(scenes, 1)
    ]


def _ask_json(
    client: OpenAICompatible,
    prompt: str,
    image: Path | None = None,
    *,
    attempts: int = 3,
    max_tokens: int = 400,
) -> dict[str, Any]:
    """提问并要求返回 JSON，传输失败或 JSON 不合法都重试。

    中转站对带图请求偶发 502 / TLS EOF（实测约 1/4），带图请求的输出也偶发被截断
    （JSON 半截）。重试基本都能过；三次都失败才算「没核对上」。
    """
    last: Exception | None = None
    for i in range(attempts):
        try:
            if image is None:
                raw = client.ask(prompt, system=SYSTEM, max_tokens=max_tokens, temperature=0)
            else:
                raw = client.ask_image(
                    prompt, image, system=SYSTEM, max_tokens=max_tokens, temperature=0,
                )
            return json.loads(_strip_fence(raw))
        except (ModelError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(1.5 * (i + 1))
    raise ModelError(f"连试 {attempts} 次都失败：{str(last)[:120]}")


def check(
    scenes: list[dict[str, Any]],
    cfg: Any,
    *,
    timeout: int = 90,
) -> list[dict[str, Any]]:
    """用视觉模型核对每张图有没有画出主体。

    不抛错：核对失败只是「没核对上」，不该把已经出好的图作废。
    """
    client = _client(cfg, timeout=timeout)
    verdicts: list[dict[str, Any]] = []

    for index, scene in enumerate(scenes, 1):
        path = Path(str(scene.get("file") or ""))
        item: dict[str, Any] = {"index": index, "ok": None, "reason": ""}
        if not path.is_file():
            item["reason"] = "图不存在"
            verdicts.append(item)
            continue
        try:
            data = _ask_json(
                client,
                CHECK_PROMPT.format(
                    subject=scene.get("subject") or "（未说明）",
                    anchor=scene.get("anchor") or "（无）",
                ),
                path,
            )
            item["main_subject"] = str(data.get("main_subject") or "")
            item["visible"] = [str(v) for v in (data.get("visible") or [])][:8]
            item["ok"] = bool(data.get("matches"))
            item["reason"] = str(data.get("reason") or "")
        except Exception as exc:  # noqa: BLE001
            item["ok"] = None
            item["reason"] = f"核对失败：{str(exc)[:80]}"

        verdicts.append(item)

    return verdicts


def revise(
    scenes: list[dict[str, Any]],
    verdicts: list[dict[str, Any]],
    cfg: Any,
) -> dict[int, str]:
    """对没画出主体的那几张，重写英文提示词。返回 {序号: 新提示词}。"""
    bad = []
    for scene, verdict in zip(scenes, verdicts):
        if verdict.get("ok") is False:
            bad.append({
                "index": verdict["index"],
                "subject": scene.get("subject") or "",
                "props": scene.get("props") or [],
                "anchor": scene.get("anchor") or "",
                "prompt": scene.get("prompt") or "",
                "seen": verdict.get("main_subject") or "",
            })
    if not bad:
        return {}

    client = _client(cfg, timeout=150)
    items = "\n".join(
        f"{b['index']}. 期望主体：{b['subject']}"
        f"（必须出现：{'、'.join(b['props']) or '—'}）；"
        f"实际画成了：{b['seen']}；原提示词：{b['prompt']}"
        for b in bad
    )
    try:
        data = _ask_json(
            client, REVISE_PROMPT.format(items=items), max_tokens=1200,
        )
    except Exception:  # noqa: BLE001
        return {}

    out: dict[int, str] = {}
    for item in data.get("scenes") or []:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        prompt = str(item.get("prompt") or "").strip()
        if prompt:
            out[index] = prompt
    return out
