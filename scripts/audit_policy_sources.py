"""验国内政策原文的可抓性：官方站点是静态还是 JS 渲染。"""
import sys
import time

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.article import fetch
from pipeline.config import load_config

cfg = load_config()

CASES = [
    ("中国政府网 首页", "https://www.gov.cn/"),
    ("中国政府网 政策", "https://www.gov.cn/zhengce/"),
    ("新华网", "http://www.xinhuanet.com/"),
    ("人民网", "http://www.people.com.cn/"),
    ("上海政府网", "https://www.shanghai.gov.cn/"),
    ("人社部", "https://www.mohrss.gov.cn/"),
    ("国家医保局", "https://www.nhsa.gov.cn/"),
]

print(f"{'站点':<18}{'结果':<6}{'字数':>7}{'秒':>6}  开头")
for name, url in CASES:
    t0 = time.time()
    try:
        page = fetch(url, proxy=cfg.trends.proxy or None)
        dt = round(time.time() - t0, 1)
        if page.ok:
            head = (page.text or "").replace("\n", " ")[:34]
            print(f"{name:<18}{'OK':<6}{page.chars:>7}{dt:>6}  {head}")
        else:
            print(f"{name:<18}{'FAIL':<6}{0:>7}{dt:>6}  {page.note[:36]}")
    except Exception as exc:  # noqa: BLE001
        print(f"{name:<18}{'ERR':<6}{0:>7}{round(time.time() - t0, 1):>6}  {str(exc)[:36]}")
