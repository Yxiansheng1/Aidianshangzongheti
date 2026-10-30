"""验中药素材可得性：几个候选源能不能抓、抓到多少、是不是结构化。"""
import sys
import time

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.article import fetch
from pipeline.config import load_config

cfg = load_config()

URLS = [
    ("维基·枸杞子", "https://zh.wikipedia.org/wiki/枸杞子"),
    ("维基·陈皮", "https://zh.wikipedia.org/wiki/陈皮"),
    ("维基·甘草", "https://zh.wikipedia.org/wiki/甘草"),
    ("植物志·枸杞", "https://www.iplant.cn/info/Lycium%20chinense"),
    ("香港中药材标准", "https://www.cmcs.hk/tc"),
    ("国家中医药局", "http://www.satcm.gov.cn/"),
]

print(f"{'源':<16}{'结果':<6}{'字数':>7}{'秒':>6}  开头")
for name, url in URLS:
    t0 = time.time()
    page = fetch(url, proxy=cfg.trends.proxy or None)
    dt = round(time.time() - t0, 1)
    head = (page.text or "").replace("\n", " ")[:40] if page.ok else page.note[:40]
    print(f"{name:<16}{'OK' if page.ok else 'FAIL':<6}{(page.chars if page.ok else 0):>7}{dt:>6}  {head}")
