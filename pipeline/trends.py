"""热点抓取（国内 + 国外）。

设计分两层，别混：

    菜单层   所有抓到的条目，按分类列出来。**不过滤**，你自己挑。
    推荐层   类目命中 + 非负面。这一栏才是"能蹭的"。

为什么要分开：你想看军事新闻，但「战争/袭击/冲突」在负面词表里。
如果只输出推荐层，军事类会全军覆没。所以菜单层必须全量。

数据源（2026-10-29 实测）：

    国内 · 热搜     百度 ✅ 51 条   微博 ✅ 51 条（要 Referer）
    AI与科技        HackerNews ✅   arXiv cs.AI ✅   TechCrunch ✅
                    The Verge ✅   Ars Technica ✅
    国际时事        Google News ✅  BBC ✅
    军事            Defense News ✅

    知乎 401、抖音要签名、Reuters 404 —— 不支持，抓不到就跳过。

网络：国内源直连（绕开代理），国外源走代理。代理地址在 config.toml 的
[trends] proxy 里配，默认 http://127.0.0.1:7897。
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

DEFAULT_PROXY = "http://127.0.0.1:7897"

CATEGORIES = [
    "国内热搜", "AI与科技", "政治", "国际", "军事",
    "财经", "影视", "体育", "学术", "游戏",
    "政策", "历史",
]


# --------------------------------------------------------------- 数据模型


@dataclass
class TrendItem:
    source: str
    source_name: str
    category: str
    rank: int
    title: str
    url: str = ""
    heat: str = ""
    summary: str = ""          # RSS 里的导语，改写时的第一手材料
    matched: bool = False      # 命中关注词
    blocked: bool = False      # 命中负面词

    def as_dict(self) -> dict:
        return {
            "category": self.category,
            "source": self.source_name,
            "rank": self.rank,
            "title": self.title,
            "url": self.url,
            "heat": self.heat,
            "summary": self.summary,
            "matched": self.matched,
            "blocked": self.blocked,
        }


@dataclass
class TrendResult:
    items: list[TrendItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    fetched_at: str = ""

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def matched(self) -> list[TrendItem]:
        return [i for i in self.items if i.matched and not i.blocked]

    @property
    def blocked(self) -> list[TrendItem]:
        return [i for i in self.items if i.blocked]

    def by_category(self) -> dict[str, list[TrendItem]]:
        out: dict[str, list[TrendItem]] = {}
        for item in self.items:
            out.setdefault(item.category, []).append(item)
        for items in out.values():
            items.sort(key=lambda x: x.rank)
        return out

    def as_dict(self) -> dict:
        return {
            "fetched_at": self.fetched_at,
            "total": self.total,
            "matched": len(self.matched),
            "blocked": len(self.blocked),
            "keywords": self.keywords,
            "errors": self.errors,
            "items": [i.as_dict() for i in self.items],
            "hot": [i.as_dict() for i in self.matched],
        }


# --------------------------------------------------------------- 词表


DEFAULT_KEYWORDS = [
    "家居", "收纳", "整理", "香薰", "香氛", "蜡烛", "氛围", "租房", "独居",
    "小户型", "桌面", "改造", "好物", "生活", "卧室", "书房", "厨房",
    "礼物", "送礼", "平价", "懒人", "宿舍",
    "情绪", "解压", "治愈", "松弛", "仪式感", "宅家", "冬天", "降温",
    "AI", "人工智能", "设计", "创意", "手作", "DIY",
]

# 只影响"能不能蹭"，不影响"要不要展示"。
NEGATIVE_WORDS = [
    "身亡", "遇袭", "死亡", "去世", "病逝", "猝死", "轻生", "自杀",
    "崩溃", "事故", "火灾", "爆炸", "坠", "车祸", "溺", "殴打", "暴力",
    "被捕", "判刑", "判决", "起诉", "拘留", "处罚", "罚款", "通报",
    "谣言", "编造", "诈骗", "骗", "偷", "抢", "贪", "腐败", "落马",
    "离婚", "出轨", "恋情", "分手", "道歉", "争议", "举报", "抵制",
    "确诊", "感染", "病毒", "疫情", "癌", "疾病",
    "暴雪", "暴雨", "台风", "地震", "洪水", "灾害",
    "战争", "冲突", "袭击", "制裁", "伤亡", "导弹", "空袭",
]

# 英文负面词。国外源必须单独列，否则 "train crash kills 68" 会被当成可蹭热点。
NEGATIVE_WORDS_EN = [
    "kill", "killed", "kills", "dead", "death", "dies", "died", "fatal",
    "crash", "collision", "attack", "attacks", "war", "missile", "airstrike",
    "invasion", "shooting", "shot", "injured", "wounded", "hostage", "terror",
    "hack", "hacked", "leak", "leaked", "breach", "ransomware",
    "scandal", "fraud", "lawsuit", "sued", "arrest", "arrested", "jailed",
    "guilty", "convicted", "resign", "resigns", "layoff", "layoffs",
    "bankrupt", "bankruptcy", "collapse", "crisis", "protest", "riot",
    "flood", "hurricane", "wildfire", "earthquake", "tsunami",
    "pandemic", "outbreak", "virus", "cancer", "victim", "tragedy",
]


def is_negative(title: str) -> bool:
    lowered = title.lower()
    if any(word in title for word in NEGATIVE_WORDS):
        return True
    return any(word in lowered for word in NEGATIVE_WORDS_EN)


def build_matcher(keywords: list[str]):
    """中文按子串匹配，英文按词边界匹配。

    不这么做的话，「AI」会命中 claims / failure / Faith ——实测就是这样，
    结果一堆政治新闻被标成"AI 相关"。
    """
    ascii_patterns = [
        re.compile(rf"(?<![A-Za-z]){re.escape(k)}(?![A-Za-z])", re.I)
        for k in keywords
        if k.isascii()
    ]
    cjk_words = [k for k in keywords if not k.isascii()]

    def match(title: str) -> bool:
        if any(word in title for word in cjk_words):
            return True
        return any(pattern.search(title) for pattern in ascii_patterns)

    return match


def is_matched(title: str, keywords: list[str]) -> bool:
    return build_matcher(keywords)(title)


# --------------------------------------------------------------- 抓取


def _get(url: str, *, proxy: str | None, referer: str = "", timeout: int = 20) -> bytes:
    headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    context = ssl._create_unverified_context()

    handlers: list = [urllib.request.HTTPSHandler(context=context)]
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))

    opener = urllib.request.build_opener(*handlers)
    with opener.open(request, timeout=timeout) as response:
        return response.read()


def _fetch_baidu(proxy: str | None) -> list[TrendItem]:
    html = _get("https://top.baidu.com/board?tab=realtime", proxy=None).decode("utf-8", "replace")
    match = re.search(r"<!--s-data:(.*?)-->", html, re.S)
    if not match:
        raise ValueError("百度页面结构变了")
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
                source="baidu", source_name="百度热搜", category="国内热搜",
                rank=rank, title=word, heat=str(entry.get("hotScore") or ""),
                url=entry.get("url") or entry.get("rawUrl") or "",
            ))
    return items


def _fetch_weibo(proxy: str | None) -> list[TrendItem]:
    raw = _get("https://weibo.com/ajax/side/hotSearch", proxy=None, referer="https://weibo.com/")
    data = json.loads(raw.decode("utf-8", "replace"))
    items: list[TrendItem] = []
    rank = 0
    for entry in (data.get("data") or {}).get("realtime") or []:
        word = (entry.get("word") or "").strip()
        if not word:
            continue
        rank += 1
        items.append(TrendItem(
            source="weibo", source_name="微博热搜", category="国内热搜",
            rank=rank, title=word, heat=str(entry.get("num") or ""),
            url=f"https://s.weibo.com/weibo?q=%23{urllib.parse.quote(word)}%23",
        ))
    return items


def _fetch_hn(proxy: str | None) -> list[TrendItem]:
    """Hacker News 用 Algolia 的 front_page，一次拿到标题+链接+分数。"""
    raw = _get("https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=25", proxy=proxy)
    data = json.loads(raw.decode("utf-8", "replace"))
    items: list[TrendItem] = []
    for rank, hit in enumerate(data.get("hits", []), 1):
        title = (hit.get("title") or "").strip()
        if not title:
            continue
        items.append(TrendItem(
            source="hn", source_name="Hacker News", category="AI与科技",
            rank=rank, title=title, heat=str(hit.get("points") or ""),
            url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
        ))
    return items


POLICY_LINK = re.compile(r'href="([^"]*zhengce/content/[^"]+\.htm)"[^>]*>(.*?)</a>', re.S)

# 历史源只留这些方向：中国、战争、军队、条约、工业建设
HISTORY_KEEP = (
    "中国", "中华", "战", "军", "条约", "协定", "铁路", "工厂", "解放",
    "抗战", "清", "民国", "人民", "革命", "外交", "投降", "起义", "建设", "迁",
)


def _fetch_gov_policy(proxy: str | None) -> list[TrendItem]:
    """国务院政策：从政策频道首页解析出政策文件链接。

    索引页是静态 HTML（36KB 左右），但正文提取器会把链接全过滤掉，
    所以这里直接读原始 HTML 抠 <a>。
    """
    raw = _get("https://www.gov.cn/zhengce/", proxy=proxy, timeout=25)
    page = raw.decode("utf-8", "replace")

    items: list[TrendItem] = []
    seen: set[str] = set()
    for href, inner in POLICY_LINK.findall(page):
        title = re.sub(r"<[^>]+>", " ", inner)
        title = re.sub(r"\s+", " ", title).strip()
        if len(title) < 6:
            continue
        url = urllib.parse.urljoin("https://www.gov.cn/zhengce/", href)
        if url in seen:
            continue
        seen.add(url)
        items.append(TrendItem(
            source="gov", source_name="国务院政策", category="政策",
            rank=len(items) + 1, title=title, url=url,
        ))
        if len(items) >= 25:
            break
    return items


def _fetch_history(proxy: str | None) -> list[TrendItem]:
    """维基「历史上的今天」：每天返回 50 条，这里只留中国/战史/工业方向的。

    这是「碰运气」的来源——撞上能写的题就用，撞不上还有题库。
    """
    now = datetime.now()
    api = f"https://zh.wikipedia.org/api/rest_v1/feed/onthisday/events/{now.month}/{now.day}"
    raw = _get(api, proxy=proxy, timeout=25)
    data = json.loads(raw.decode("utf-8", "replace"))

    items: list[TrendItem] = []
    for event in data.get("events") or []:
        text = re.sub(r"\s+", " ", str(event.get("text") or "")).strip()
        if len(text) < 12:
            continue
        if not any(key in text for key in HISTORY_KEEP):
            continue

        pages = event.get("pages") or []
        slug = ""
        for page in pages:
            title = str((page.get("titles") or {}).get("normalized") or "")
            # 优先指向具体词条，别指向「2002年」这种年份页
            if title and not re.fullmatch(r"\d{3,4}年", title):
                slug = title
                break
        if not slug and pages:
            slug = str((pages[0].get("titles") or {}).get("normalized") or "")
        url = f"https://zh.wikipedia.org/wiki/{urllib.parse.quote(slug)}" if slug else ""

        items.append(TrendItem(
            source="wiki_otd", source_name="维基·历史上的今天", category="历史",
            rank=len(items) + 1,
            title=f"{event.get('year')}年 {text[:44]}",
            url=url,
        ))
        if len(items) >= 15:
            break
    return items


ATOM = "{http://www.w3.org/2005/Atom}"


def _parse_feed(raw: bytes) -> list[tuple[str, str, str, str]]:
    """返回 [(标题, 链接, 时间, 导语)]，同时支持 RSS 2.0 和 Atom。"""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"不是合法 XML：{exc}") from exc

    out: list[tuple[str, str, str, str]] = []

    for node in root.iter("item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        date = (node.findtext("pubDate") or "").strip()
        desc = (node.findtext("description") or "").strip()
        # description 里常常带 HTML，去掉标签
        desc = re.sub(r"<[^>]+>", " ", desc)
        desc = re.sub(r"\s+", " ", desc).strip()
        if title:
            out.append((title, link, date, desc))

    if not out:
        for node in root.iter(f"{ATOM}entry"):
            title = (node.findtext(f"{ATOM}title") or "").strip()
            link_node = node.find(f"{ATOM}link")
            link = link_node.get("href", "") if link_node is not None else ""
            date = (node.findtext(f"{ATOM}updated") or node.findtext(f"{ATOM}published") or "").strip()
            desc = (node.findtext(f"{ATOM}summary") or "").strip()
            if title:
                out.append((title, link, date, desc))

    return out


def _make_rss_fetcher(source: str, name: str, category: str, url: str, limit: int = 15):
    def fetch(proxy: str | None) -> list[TrendItem]:
        raw = _get(url, proxy=proxy, timeout=25)
        entries = _parse_feed(raw)[:limit]
        if not entries:
            raise ValueError("feed 里没有条目")
        return [
            TrendItem(
                source=source, source_name=name, category=category,
                rank=index, title=title.strip(), url=link, summary=desc,
            )
            for index, (title, link, _date, desc) in enumerate(entries, 1)
        ]

    return fetch


# --------------------------------------------------------------- 源注册表


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    category: str
    needs_proxy: bool
    fetcher: object


SOURCES: list[Source] = [
    # 政策 / 历史（给两个头条号用：号1 政策解读，号2 近代史战史）
    Source("gov", "国务院政策", "政策", False, _fetch_gov_policy),
    Source("wiki_otd", "维基·历史上的今天", "历史", True, _fetch_history),

    # 国内
    Source("baidu", "百度热搜", "国内热搜", False, _fetch_baidu),
    Source("weibo", "微博热搜", "国内热搜", False, _fetch_weibo),

    # AI 与科技
    Source("hn", "Hacker News", "AI与科技", True, _fetch_hn),
    Source("techcrunch", "TechCrunch", "AI与科技", True,
           _make_rss_fetcher("techcrunch", "TechCrunch", "AI与科技",
                             "https://techcrunch.com/feed/", limit=12)),
    Source("verge", "The Verge", "AI与科技", True,
           _make_rss_fetcher("verge", "The Verge", "AI与科技",
                             "https://www.theverge.com/rss/index.xml", limit=12)),
    Source("ars", "Ars Technica", "AI与科技", True,
           _make_rss_fetcher("ars", "Ars Technica", "AI与科技",
                             "https://feeds.arstechnica.com/arstechnica/index", limit=12)),

    # 政治
    Source("politico", "Politico", "政治", True,
           _make_rss_fetcher("politico", "Politico", "政治",
                             "https://rss.politico.com/politics-news.xml", limit=15)),

    # 国际
    Source("googlenews", "Google News", "国际", True,
           _make_rss_fetcher("googlenews", "Google News", "国际",
                             "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en", limit=15)),
    Source("bbc", "BBC", "国际", True,
           _make_rss_fetcher("bbc", "BBC", "国际",
                             "https://feeds.bbci.co.uk/news/rss.xml", limit=15)),
    Source("npr", "NPR", "国际", True,
           _make_rss_fetcher("npr", "NPR", "国际",
                             "https://feeds.npr.org/1001/rss.xml", limit=12)),

    # 军事
    Source("defense", "Defense News", "军事", True,
           _make_rss_fetcher("defense", "Defense News", "军事",
                             "https://www.defensenews.com/arc/outboundfeeds/rss/", limit=12)),

    # 财经
    Source("cnbc", "CNBC", "财经", True,
           _make_rss_fetcher("cnbc", "CNBC", "财经",
                             "https://www.cnbc.com/id/100003114/device/rss/rss.html", limit=12)),
    Source("marketwatch", "MarketWatch", "财经", True,
           _make_rss_fetcher("marketwatch", "MarketWatch", "财经",
                             "http://feeds.marketwatch.com/marketwatch/topstories/", limit=12)),

    # 影视
    Source("variety", "Variety", "影视", True,
           _make_rss_fetcher("variety", "Variety", "影视",
                             "https://variety.com/feed/", limit=12)),
    Source("deadline", "Deadline", "影视", True,
           _make_rss_fetcher("deadline", "Deadline", "影视",
                             "https://deadline.com/feed/", limit=12)),
    Source("thr", "Hollywood Reporter", "影视", True,
           _make_rss_fetcher("thr", "Hollywood Reporter", "影视",
                             "https://www.hollywoodreporter.com/feed/", limit=12)),

    # 体育
    Source("bbcsport", "BBC Sport", "体育", True,
           _make_rss_fetcher("bbcsport", "BBC Sport", "体育",
                             "http://feeds.bbci.co.uk/sport/rss.xml", limit=15)),

    # 学术
    Source("arxiv", "arXiv cs.AI", "学术", True,
           _make_rss_fetcher("arxiv", "arXiv cs.AI", "学术",
                             "https://export.arxiv.org/rss/cs.AI", limit=10)),
    Source("nature", "Nature", "学术", True,
           _make_rss_fetcher("nature", "Nature", "学术",
                             "https://www.nature.com/nature.rss", limit=10)),
    Source("science", "Science", "学术", True,
           _make_rss_fetcher("science", "Science", "学术",
                             "https://www.science.org/rss/news_current.xml", limit=10)),

    # 游戏
    Source("ign", "IGN", "游戏", True,
           _make_rss_fetcher("ign", "IGN", "游戏",
                             "https://feeds.ign.com/ign/all", limit=12)),
]

SOURCE_MAP = {s.key: s for s in SOURCES}


# --------------------------------------------------------------- 主流程


def collect(
    sources: list[str] | None = None,
    keywords: list[str] | None = None,
    proxy: str | None = DEFAULT_PROXY,
    categories: list[str] | None = None,
) -> TrendResult:
    """抓取所有源。单个源失败不影响其他。"""
    keywords = keywords or DEFAULT_KEYWORDS
    result = TrendResult(keywords=list(keywords), fetched_at=datetime.now().isoformat(timespec="seconds"))

    selected = SOURCES
    if sources:
        selected = [s for s in SOURCES if s.key in sources]
    if categories:
        selected = [s for s in selected if s.category in categories]

    for source in selected:
        try:
            items = source.fetcher(proxy if source.needs_proxy else None)
            result.items.extend(items)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"{source.name}：{exc}")

    matcher = build_matcher(keywords)
    for item in result.items:
        item.matched = matcher(item.title)
        item.blocked = is_negative(item.title)

    return result


def render_markdown(result: TrendResult) -> str:
    lines = [
        f"# 今日热点 · {result.fetched_at[:10]}",
        "",
        f"共 {result.total} 条，其中类目命中且可蹭 {len(result.matched)} 条。",
        "",
    ]

    if result.errors:
        lines += ["抓取失败：", ""]
        lines += [f"- {e}" for e in result.errors]
        lines.append("")

    hot = result.matched
    lines += ["## 推荐蹭的", ""]
    if not hot:
        lines += ["今天没有同时满足「类目相关 + 不负面」的，自己去下面菜单里挑。", ""]
    else:
        lines += ["| # | 分类 | 来源 | 标题 |", "|---|---|---|---|"]
        for index, item in enumerate(hot, 1):
            lines.append(f"| {index} | {item.category} | {item.source_name} | {item.title.replace('|', '｜')} |")
        lines.append("")

    lines += ["## 完整菜单", ""]
    for category in CATEGORIES:
        items = result.by_category().get(category)
        if not items:
            continue
        lines += [f"### {category}", ""]
        lines += ["| # | 来源 | 标题 | 标记 |", "|---|---|---|---|"]
        for item in items:
            mark = ""
            if item.blocked:
                mark = "负面"
            elif item.matched:
                mark = "相关"
            title = item.title.replace("|", "｜")
            if len(title) > 70:
                title = title[:70] + "…"
            lines.append(f"| {item.rank} | {item.source_name} | {title} | {mark} |")
        lines.append("")

    lines += [
        "## 标记说明",
        "",
        "- **相关**：命中你的关注词，可能能蹭",
        "- **负面**：命中负面词表，**别蹭**（但可以看，做判断用）",
        "- 空白：跟你的类目无关，纯信息",
        "",
    ]

    return "\n".join(lines)


def save(result: TrendResult, directory: Path | str) -> Path:
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{result.fetched_at[:10]}.md"
    target.write_text(render_markdown(result), encoding="utf-8")
    return target
