"""热点抓取。

只抓公开榜单页，低频调用（一天一次）。不登录、不绕风控、不碰私域数据。

实测可用（2026-10-29）：
    百度热搜  https://top.baidu.com/board?tab=realtime    51 条
    微博热搜  https://weibo.com/ajax/side/hotSearch       51 条（必须带 Referer）

抓不到的：
    知乎热榜  401，要登录态
    抖音热点  需要签名
    小红书    反爬 + 违规

设计原则：抓不到就跳过，不重试、不绕。少一个源不影响用。
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 默认关注词。可以在 config.toml 的 [trends] keywords 里改。
DEFAULT_KEYWORDS = [
    "家居", "收纳", "整理", "香薰", "香氛", "蜡烛", "氛围", "租房", "独居",
    "小户型", "桌面", "改造", "好物", "生活", "卧室", "书房", "厨房",
    "礼物", "送礼", "平价", "懒人", "宿舍",
    "情绪", "解压", "治愈", "松弛", "仪式感", "宅家", "冬天", "降温",
]

# 负面/敏感词。命中任何一个直接丢弃，不参与排序。
# 蹭正面热点叫借势，蹭负面叫找死。
NEGATIVE_WORDS = [
    "身亡", "遇袭", "死亡", "去世", "病逝", "猝死", "轻生", "自杀",
    "崩溃", "事故", "火灾", "爆炸", "坠", "车祸", "溺", "殴打", "暴力",
    "被捕", "判刑", "判决", "起诉", "拘留", "处罚", "罚款", "通报",
    "谣言", "编造", "诈骗", "骗", "偷", "抢", "贪", "腐败", "落马",
    "离婚", "出轨", "恋情", "分手", "道歉", "争议", "举报", "抵制",
    "确诊", "感染", "病毒", "疫情", "癌", "疾病",
    "暴雪", "暴雨", "台风", "地震", "洪水", "灾害",
    "战争", "冲突", "袭击", "制裁",
]

SOURCE_NAMES = {"baidu": "百度热搜", "weibo": "微博热搜"}


@dataclass
class TrendItem:
    source: str
    rank: int
    title: str
    heat: str = ""
    url: str = ""

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "source_name": SOURCE_NAMES.get(self.source, self.source),
            "rank": self.rank,
            "title": self.title,
            "heat": self.heat,
            "url": self.url,
        }


@dataclass
class TrendResult:
    items: list[TrendItem] = field(default_factory=list)
    matched: list[TrendItem] = field(default_factory=list)
    blocked: list[TrendItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    fetched_at: str = ""

    @property
    def total(self) -> int:
        return len(self.items)

    def as_dict(self) -> dict:
        return {
            "fetched_at": self.fetched_at,
            "total": len(self.items),
            "matched": len(self.matched),
            "blocked": len(self.blocked),
            "keywords": self.keywords,
            "errors": self.errors,
            "items": [i.as_dict() for i in self.items],
            "hot": [i.as_dict() for i in self.matched],
        }


def _get(url: str, referer: str = "", timeout: int = 15) -> bytes:
    headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    context = ssl._create_unverified_context()
    # 这些源都在国内，明确绕开系统代理，避免代理规则不匹配导致超时
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context),
    )
    with opener.open(request, timeout=timeout) as response:
        return response.read()


def fetch_baidu() -> list[TrendItem]:
    """百度热搜。榜单数据藏在 HTML 注释里：<!--s-data:{...}-->"""
    raw = _get("https://top.baidu.com/board?tab=realtime")
    html = raw.decode("utf-8", "replace")

    match = re.search(r"<!--s-data:(.*?)-->", html, re.S)
    if not match:
        raise ValueError("百度页面结构变了，找不到 s-data")

    data = json.loads(match.group(1))
    items: list[TrendItem] = []
    rank = 0
    for card in data.get("data", {}).get("cards", []):
        for entry in card.get("content", []) or []:
            word = (entry.get("word") or "").strip()
            if not word:
                continue
            rank += 1
            items.append(TrendItem(
                source="baidu",
                rank=rank,
                title=word,
                heat=str(entry.get("hotScore") or ""),
                url=entry.get("url") or entry.get("rawUrl") or "",
            ))
    if not items:
        raise ValueError("百度返回了 s-data 但没有条目")
    return items


def fetch_weibo() -> list[TrendItem]:
    """微博热搜。必须带 Referer，否则 403。"""
    raw = _get("https://weibo.com/ajax/side/hotSearch", referer="https://weibo.com/")
    data = json.loads(raw.decode("utf-8", "replace"))

    realtime = (data.get("data") or {}).get("realtime") or []
    items: list[TrendItem] = []
    rank = 0
    for entry in realtime:
        word = (entry.get("word") or "").strip()
        if not word:
            continue
        rank += 1
        items.append(TrendItem(
            source="weibo",
            rank=rank,
            title=word,
            heat=str(entry.get("num") or ""),
            url=f"https://s.weibo.com/weibo?q=%23{urllib.parse.quote(word)}%23",
        ))
    if not items:
        raise ValueError("微博返回了但没有条目")
    return items


FETCHERS = {
    "baidu": fetch_baidu,
    "weibo": fetch_weibo,
}


def is_negative(title: str) -> bool:
    return any(word in title for word in NEGATIVE_WORDS)


def score(item: TrendItem, keywords: list[str]) -> int:
    """相关性打分：命中关键词 + 排名越靠前分越高。"""
    hits = sum(1 for k in keywords if k in item.title)
    if hits == 0:
        return 0
    # 排名权重：第 1 名 50 分，第 51 名 0 分
    rank_bonus = max(0, 51 - item.rank)
    return hits * 100 + rank_bonus


def collect(
    sources: list[str] | None = None,
    keywords: list[str] | None = None,
    only_matched: bool = True,
    top: int = 10,
) -> TrendResult:
    sources = sources or list(FETCHERS)
    keywords = keywords or DEFAULT_KEYWORDS

    result = TrendResult(keywords=list(keywords), fetched_at=datetime.now().isoformat(timespec="seconds"))

    for name in sources:
        fetcher = FETCHERS.get(name)
        if not fetcher:
            result.errors.append(f"未知来源：{name}")
            continue
        try:
            result.items.extend(fetcher())
        except Exception as exc:  # noqa: BLE001 —— 单个源挂了不影响别的
            result.errors.append(f"{SOURCE_NAMES.get(name, name)}：{exc}")

    # 先把负面新闻剔掉，再算相关性
    blocked = [i for i in result.items if is_negative(i.title)]
    result.blocked = blocked
    candidates = [i for i in result.items if not is_negative(i.title)]

    scored = [(score(i, keywords), i) for i in candidates]
    matched = [i for s, i in sorted(scored, key=lambda x: -x[0]) if s > 0]

    result.matched = matched[:top] if only_matched else candidates[:top]
    return result


def render_markdown(result: TrendResult) -> str:
    lines = [
        f"# 今日热点 · {result.fetched_at[:10]}",
        "",
        f"抓取 {result.total} 条，命中关注词 {len(result.matched)} 条"
        + (f"，已过滤负面 {len(result.blocked)} 条" if result.blocked else "")
        + "。",
        "",
    ]

    if result.errors:
        lines += ["抓取异常：", ""]
        lines += [f"- {e}" for e in result.errors]
        lines.append("")

    lines += ["## 可以蹭的", ""]
    if not result.matched:
        lines += [
            "今天没有命中关注词的热点。",
            "",
            f"下面是全榜前 {min(15, len(result.items))} 条，自己扫一眼有没有能搭的：",
            "",
        ]
        lines += ["| # | 来源 | 排名 | 热点 |", "|---|---|---|---|"]
        for index, item in enumerate(result.items[:15], 1):
            title = item.title.replace("|", "｜")
            lines.append(f"| {index} | {SOURCE_NAMES.get(item.source, item.source)} | {item.rank} | {title} |")
        lines.append("")
    else:
        lines += ["| # | 来源 | 排名 | 热点 |", "|---|---|---|---|"]
        for index, item in enumerate(result.matched, 1):
            title = item.title.replace("|", "｜")
            lines.append(f"| {index} | {SOURCE_NAMES.get(item.source, item.source)} | {item.rank} | {title} |")
        lines.append("")

    lines += ["## 怎么用", ""]
    lines += [
        "1. 挑一条跟你的品能搭上的热点",
        "2. 把它丢进工作台「分析」页签的补充信息里",
        "3. 让 AI 想一个结合点，再出图和写文案",
        "",
        "注意：蹭热点要看语境。负面新闻（事故、纠纷、争议）别蹭，容易翻车。",
        "",
    ]

    return "\n".join(lines)


def save(result: TrendResult, directory: Path | str) -> Path:
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{result.fetched_at[:10]}.md"
    target.write_text(render_markdown(result), encoding="utf-8")
    return target
