"""按平台 skill 改写。

skill 是 skills/*.md 文件，直接当 system prompt 用。
想改风格、加禁词、调结构，改 md 就行，不用碰代码。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..model.client import ModelError, OpenAICompatible

SKILL_DIR = Path(__file__).parent / "skills"
DEFAULT_SKILL = "小红书"


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

    system = load_skill(platform)

    client = OpenAICompatible(
        base_url=cfg.model.base_url,
        api_key=cfg.model.api_key,
        timeout=max(cfg.model.timeout, 180),
        text_model=cfg.model.text_model,
    )

    prompt = build_user_prompt(topic, source_text, extra=extra)
    raw = client.ask(prompt, system=system, max_tokens=4000, temperature=0.8)

    try:
        data = json.loads(_strip_fence(raw))
    except json.JSONDecodeError:
        raw = client.ask(
            prompt + "\n\n上次输出不是合法 JSON。这次只输出完整的 JSON 对象。",
            system=system, max_tokens=4000, temperature=0.3,
        )
        try:
            data = json.loads(_strip_fence(raw))
        except json.JSONDecodeError as exc:
            raise ModelError(f"模型两次都没返回合法 JSON：{exc}\n{raw[:300]}") from exc

    title = str(data.get("title") or "").strip()
    body = str(data.get("body") or "").strip()
    if not title or not body:
        raise ModelError("模型没有产出标题或正文")

    tags = [str(t).strip().lstrip("#") for t in (data.get("tags") or []) if str(t).strip()]
    gaps = [str(g).strip() for g in (data.get("gaps") or []) if str(g).strip()]

    if len(title) > 20:
        title = title[:20]

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
        "tags": tags[:8],
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
