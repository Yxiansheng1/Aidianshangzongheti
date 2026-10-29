"""验标题截断：不要切出半句话。"""
import sys

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.content.rewrite import _smart_truncate

cases = [
    ("Terminal-Bench 4.0 拿 41%，输出 token 少 30%", 30),
    ("Mistral 开源 1 万亿参数 Le Chonk，代码基准追平 GLM-5.3", 30),
    ("拒掉 Datadog 收购，Upwind 转身融了 4 亿美元", 20),
    ("短标题", 20),
    ("没有标点而且很长的一串文字一直写下去不断句标题就这样超了", 20),
]

for text, limit in cases:
    out = _smart_truncate(text, limit)
    print(f"{len(out):>2} 字 | {out}")
