"""端到端跑一条：抓原文 → 改写 → 审核 → 配图（含核对与重出）。

用缓存好的原文，不打网络。出图走本地 ComfyUI，约 20 秒/张。

    python scripts\\test_pipeline.py [平台] [张数]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.config import load_config, ROOT
from pipeline.content import pipeline as content_pipeline

cache = ROOT / "output" / "测试" / "_source.json"
if not cache.is_file():
    raise SystemExit("没有缓存的原文，先跑 scripts/_pick_source.py")

src = json.loads(cache.read_text(encoding="utf-8"))
platform = sys.argv[1] if len(sys.argv) > 1 else "小红书"
images = int(sys.argv[2]) if len(sys.argv) > 2 else 2

cfg = load_config()
result = content_pipeline.run(
    "", cfg, platform=platform, images=images, draw=images > 0,
    article={"title": src["title"], "text": src["text"]},
)

print("ok:", result.get("ok"))
steps = result.get("steps", {})
print("fetch   :", steps.get("fetch"))
print("rewrite :", steps.get("rewrite"))
review = steps.get("review", {})
print("review  :", {"passed": review.get("passed"), "score": review.get("score"),
                    "issues": len(review.get("issues") or [])})
visual = steps.get("visual", {})
print("visual  :", {"ok": visual.get("ok"), "count": visual.get("count"),
                    "retried": visual.get("retried"), "reason": visual.get("reason")})
for scene, check in zip(visual.get("scenes") or [], visual.get("checks") or []):
    print(f"  [{check.get('index')}] {'✅' if check.get('ok') else ('❔' if check.get('ok') is None else '❌')} "
          f"{check.get('main_subject') or check.get('reason')} ← {scene.get('subject')}")
    print(f"       anchor: {scene.get('anchor')}")

print("\n产物:", result.get("dir"))
