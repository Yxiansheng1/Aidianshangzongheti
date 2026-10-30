"""建历史题库：40 个题，逐个核维基词条是否存在，输出 md + json。

存在性用维基 API 批量查（一次 20 个），重定向也一并解析，
所以「抗美援朝」这类别名会自动落到正确词条上。
"""
import json
import ssl
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.config import ROOT, load_config

TOPICS = [
    ("第一次鸦片战争", "1840 年的这场仗，清朝输在哪一步"),
    ("第二次鸦片战争", "圆明园被烧那天，英法联军进了几道门"),
    ("太平天国", "太平天国为什么守不住天京"),
    ("洋务运动", "洋务运动办了三十年，为什么还是打不过"),
    ("甲午战争", "甲午一战，北洋水师到底缺什么"),
    ("马关条约", "马关条约签的那一晚，李鸿章遇刺"),
    ("戊戌变法", "戊戌变法 103 天，卡在哪一步"),
    ("义和团运动", "义和团进京之后，秩序是怎么崩的"),
    ("辛丑条约", "辛丑条约里的赔款，还了多少年"),
    ("辛亥革命", "武昌起义那夜，是谁先开的枪"),
    ("北洋军阀", "北洋军阀混战那些年，钱从哪来"),
    ("五四运动", "五四那天，学生为什么去赵家楼"),
    ("国民革命军北伐", "北伐为什么能打到长江边"),
    ("南昌起义", "南昌起义之后，队伍去了哪"),
    ("井冈山", "井冈山时期，红军靠什么活下来"),
    ("长征", "长征路上最难的一段是哪一段"),
    ("西安事变", "西安事变那 13 天，谁在中间传话"),
    ("七七事变", "卢沟桥那一夜，到底谁先开的枪"),
    ("淞沪会战", "淞沪会战三个月，为什么守不住"),
    ("台儿庄战役", "台儿庄大捷，代价是多少人"),
    ("武汉会战", "武汉会战之后，战场为什么进入相持"),
    ("百团大战", "百团大战的规模，是怎么统计出来的"),
    ("滇缅公路", "滇缅公路是怎么在八个月里修通的"),
    ("驼峰航线", "驼峰航线上，飞一趟要冒多大风险"),
    ("中国远征军", "中国远征军第一次入缅，败在哪"),
    ("重庆谈判", "重庆谈判 43 天，谈成了什么"),
    ("淮海战役", "淮海战役，小车推出来的后勤线"),
    ("渡江战役", "渡江那夜，长江防线是怎么破的"),
    ("抗美援朝", "1950 年入朝，第一个冬天有多冷"),
    ("上甘岭战役", "上甘岭 43 天，坑道里怎么撑住"),
    ("第一个五年计划", "一五计划的 156 项工程，都落在哪"),
    ("三线建设", "三线建设迁走的那批厂，后来去哪了"),
    ("鞍山钢铁", "鞍钢恢复生产，靠的是什么"),
    ("长春第一汽车制造厂", "中国第一辆汽车下线，是几点"),
    ("洛阳第一拖拉机制造厂", "中国第一台拖拉机，为什么造在洛阳"),
    ("武汉长江大桥", "武汉长江大桥，为什么建在龟山蛇山之间"),
    ("两弹一星", "两弹一星那些年，人在哪里工作"),
    ("成昆铁路", "成昆铁路，为什么修了十二年"),
    ("中苏交恶", "中苏关系是怎么一步步走到对立"),
    ("中印边界战争", "1962 年那场边境战，为什么打得快退得也快"),
]

API = "https://zh.wikipedia.org/w/api.php"


def _opener(proxy: str | None):
    handlers = [urllib.request.HTTPSHandler(context=ssl._create_unverified_context())]
    handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy} if proxy else {}))
    return urllib.request.build_opener(*handlers)


def _query(titles: list[str], proxy: str | None = None) -> dict[str, str]:
    """返回 {原标题: 实际词条名}，查不到的映射成空串。

    网络走 trends 里那套代理（维基需要走代理，直连会握手失败）。
    """
    from pipeline.trends import _get

    params = {
        "action": "query", "format": "json", "redirects": "1",
        "titles": "|".join(titles), "utf8": "1",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    data = json.loads(_get(url, proxy=proxy, timeout=30).decode("utf-8", "replace"))

    q = data.get("query") or {}
    redirects = {r["from"]: r["to"] for r in (q.get("redirects") or [])}
    normalized = {n["from"]: n["to"] for n in (q.get("normalized") or [])}

    exists = {}
    for page in (q.get("pages") or {}).values():
        title = page.get("title") or ""
        if page.get("missing") is not None or not title:
            continue
        exists[title] = title

    out: dict[str, str] = {}
    for original in titles:
        step = normalized.get(original, original)
        step = redirects.get(step, step)
        out[original] = step if step in exists else ""
    return out


def main() -> None:
    resolved: dict[str, str] = {}
    proxy = load_config().trends.proxy or None
    batch = 20
    for start in range(0, len(TOPICS), batch):
        chunk = [t[0] for t in TOPICS[start:start + batch]]
        resolved.update(_query(chunk, proxy))
        time.sleep(0.5)

    rows = []
    missing = []
    for page, topic in TOPICS:
        final = resolved.get(page, "")
        if not final:
            missing.append(page)
            continue
        url = f"https://zh.wikipedia.org/wiki/{urllib.parse.quote(final.replace(' ', '_'))}"
        rows.append({"page": final, "topic": topic, "url": url})

    out_dir = ROOT / "pipeline" / "content" / "topics"
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "# 历史题库（号2 · 档案室）",
        "",
        f"共 {len(rows)} 题，词条已逐个核对存在。用法：贴链接到写作台 → 题材选「历史」→ 生成。",
        "",
        "| # | 题目方向 | 维基词条 |",
        "|---|---|---|",
    ]
    for index, row in enumerate(rows, 1):
        lines.append(f"| {index} | {row['topic']} | [{row['page']}]({row['url']}) |")
    if missing:
        lines += ["", "## 没核到的（需要换词条或换题）", ""]
        lines += [f"- {name}" for name in missing]

    (out_dir / "历史题库.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "历史题库.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"题库 {len(rows)} 题 → {out_dir / '历史题库.md'}")
    if missing:
        print("没核到：", "、".join(missing))
    print("\n前 5 条：")
    for row in rows[:5]:
        print(" ", row["topic"], "→", row["url"])


if __name__ == "__main__":
    main()
