"""多平台改写横评：同一篇原文，9 个平台各自的 skill 各写一遍。

只跑「改写 + 审核」，不出图（出图另测），产出：
    output/测试/多平台-<时间戳>/<平台>.md      每个平台一份稿
    .../summary.json                          结构化指标
    .../summary.md                            人看的对比表
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.config import load_config, ROOT
from pipeline.article import fetch
from pipeline.content.rewrite import rewrite, list_skills, TITLE_LIMITS, TAG_LIMITS
from pipeline.review import review

EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\u2190-\u21FF\u2B00-\u2BFF]"
)
BANNED = ["此外", "至关重要", "赋能", "助力", "总的来说", "综上所述", "值得注意的是",
          "由此可见", "不可或缺", "全方位", "旨在", "说白了", "本质上", "众所周知"]

CACHE = ROOT / "output" / "测试" / "_source.json"


def get_source(cfg):
    if CACHE.is_file():
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        print(f"[缓存] {data['url']}  {data['chars']} 字")
        return data

    for url in (
        "https://blog.google/technology/google-deepmind/gemini-4-carbon/",
        "https://techcrunch.com/2026/10/29/upwind-series-c/",
    ):
        page = fetch(url, proxy=cfg.trends.proxy or None)
        if page.ok and page.chars > 500:
            data = {"url": url, "title": page.title or url, "text": page.text, "chars": page.chars}
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[抓取] {url}  {page.chars} 字")
            return data
        print(f"[失败] {url}  {page.note}")

    raise SystemExit("原文都没抓到，先检查网络")


def main():
    cfg = load_config()
    src = get_source(cfg)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = ROOT / "output" / "测试" / f"多平台-{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    skills = [s for s in list_skills() if s in TITLE_LIMITS]
    if len(sys.argv) > 1:
        wanted = sys.argv[1:]
        skills = [s for s in wanted if s in skills]
    print("平台：", "、".join(skills), flush=True)

    rows = []
    for name in skills:
        t0 = time.time()
        try:
            draft = rewrite(src["title"], src["text"], cfg, platform=name)
        except Exception as exc:  # noqa: BLE001
            print(f"[{name}] 改写失败：{exc}", flush=True)
            rows.append({"platform": name, "ok": False, "err": str(exc)[:200]})
            continue

        body, title = draft["body"], draft["title"]
        emoji_n = len(EMOJI.findall(body))
        banned = [w for w in BANNED if w in body]
        para = [p for p in body.split("\n") if p.strip()]

        try:
            checked = review(f"{title}\n\n{body}", name, cfg, source_text=src["text"])
            review_info = {"passed": checked.passed, "score": checked.score,
                           "issues": len(checked.issues)}
        except Exception as exc:  # noqa: BLE001
            review_info = {"error": str(exc)[:120]}

        row = {
            "platform": name,
            "ok": True,
            "title": title,
            "title_len": len(title),
            "title_limit": TITLE_LIMITS.get(name),
            "title_over": max(0, len(title) - (TITLE_LIMITS.get(name) or 999)),
            "body_len": draft["length"],
            "paragraphs": len(para),
            "max_para_chars": max((len(p) for p in para), default=0),
            "emoji": emoji_n,
            "tags": draft["tags"],
            "tag_limit": TAG_LIMITS.get(name),
            "gaps": len(draft["gaps"]),
            "banned_hits": banned,
            "review": review_info,
            "seconds": round(time.time() - t0, 1),
            "first_line": para[0][:60] if para else "",
            "preview": body[:200].replace("\n", " / "),
        }
        rows.append(row)

        md = [f"# {title}", "", f"平台：{name}　字数：{draft['length']}", "", body, ""]
        if draft["tags"]:
            md += [" ".join(f"#{t}" for t in draft["tags"]), ""]
        if draft["gaps"]:
            md += ["## 没依据的地方", ""] + [f"- {g}" for g in draft["gaps"]] + [""]
        (out / f"{name}.md").write_text("\n".join(md), encoding="utf-8")
        print(f"[{name}] {draft['length']} 字 / {emoji_n} emoji / 审核 "
              f"{review_info.get('score', '?')} 分 / {row['seconds']}s", flush=True)

    (out / "summary.json").write_text(
        json.dumps({"source": {"url": src["url"], "title": src["title"], "chars": src["chars"]},
                    "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    # 人看的对比表
    lines = [f"# 多平台改写横评", "",
             f"原文：{src['title']}（{src['chars']} 字）  ",
             f"{src['url']}", "",
             "| 平台 | 字数 | 段数 | 最长段 | emoji | 标签 | 缺口 | 审核 | 标题超长 | 禁词 | 耗时 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if not r.get("ok"):
            lines.append(f"| {r['platform']} | ✗ {r.get('err', '')[:30]} | | | | | | | | | |")
            continue
        rv = r["review"]
        rev = f"{'✅' if rv.get('passed') else '❌'}{rv.get('score', '?')}" if "score" in rv else "✗"
        lines.append(
            f"| {r['platform']} | {r['body_len']} | {r['paragraphs']} | {r['max_para_chars']} | "
            f"{r['emoji']} | {len(r['tags'])} | {r['gaps']} | {rev} | {r['title_over']} | "
            f"{'、'.join(r['banned_hits']) or '—'} | {r['seconds']}s |")
    lines += ["", "## 每篇开头一句", ""]
    for r in rows:
        if r.get("ok"):
            lines.append(f"- **{r['platform']}**：{r['first_line']}")
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    print("产物：", out, flush=True)


if __name__ == "__main__":
    main()
