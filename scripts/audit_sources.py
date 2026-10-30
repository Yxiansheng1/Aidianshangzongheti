"""四个候选内容方向，先验素材能不能抓。

方向 -> 素材源 -> 能不能抓 -> 抓到多少
不是评估「好不好做」，只回答「原料有没有」。
"""
import sys
import time

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.article import fetch
from pipeline.config import load_config

cfg = load_config()

CASES = [
    ("劳动法 · 法条", "https://flk.npc.gov.cn/detail2.html?ZmY4MDgxODE4YWIzYTVhYjAxOGFjYjVhZmY5NjA2Yjc%3D"),
    ("劳动法 · 人社部", "https://www.mohrss.gov.cn/"),
    ("食材 · 维基番茄", "https://zh.wikipedia.org/wiki/番茄"),
    ("中药 · 维基枸杞子", "https://zh.wikipedia.org/wiki/枸杞子"),
    ("城市 · 维基景德镇", "https://zh.wikipedia.org/wiki/景德镇市"),
    ("AI 工具 · OpenAI 文档", "https://platform.openai.com/docs/guides/text-generation"),
    ("AI 工具 · Anthropic 文档", "https://docs.anthropic.com/en/docs/about-claude/models/overview"),
    ("判决书 · 裁判文书网", "https://wenshu.court.gov.cn/"),
]

print(f"{'素材源':<22}{'结果':<6}{'字数':>7}{'秒':>6}  开头")
for name, url in CASES:
    t0 = time.time()
    try:
        page = fetch(url, proxy=cfg.trends.proxy or None)
        dt = round(time.time() - t0, 1)
        if page.ok:
            head = (page.text or "").replace("\n", " ")[:36]
            print(f"{name:<22}{'OK':<6}{page.chars:>7}{dt:>6}  {head}")
        else:
            print(f"{name:<22}{'FAIL':<6}{0:>7}{dt:>6}  {page.note[:40]}")
    except Exception as exc:  # noqa: BLE001
        print(f"{name:<22}{'ERR':<6}{0:>7}{round(time.time() - t0, 1):>6}  {str(exc)[:40]}")
