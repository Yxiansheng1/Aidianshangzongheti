"""验「抓原文顺便抓图」：原文图能否提取、下载、喂给视觉模型、影响配图。"""
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.config import load_config
from pipeline.content import pipeline as content_pipeline

cfg = load_config()
url = "https://mistral.ai/news/mistral-large-4-oss/"

result = content_pipeline.run(url, cfg, platform="头条", mode="国际军事", images=2)
print("ok:", result.get("ok"))

fetch = (result.get("steps") or {}).get("fetch") or {}
print("正文:", fetch.get("chars"), "字")
print("发现配图:", fetch.get("images_found"))
print("已下载:", [Path(p).name for p in (fetch.get("images") or [])])
print("视觉描述:", fetch.get("image_note") or "（无）")

visual = (result.get("steps") or {}).get("visual") or {}
print("生成图:", visual.get("count"), "张｜重出:", visual.get("retried"))
for scene, check in zip(visual.get("scenes") or [], visual.get("checks") or []):
    print(f"  [{'✅' if check.get('ok') else '❔'} {check.get('main_subject') or check.get('reason')}]")
    print("     主体:", scene.get("subject"))
print("产物:", result.get("dir"))
