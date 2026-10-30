"""验「一稿两版」：事实不变、标题/开头/结构真的不同。"""
import re
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.config import load_config
from pipeline.content.variants import make_variant

# 取最近一篇头条稿
dirs = sorted([p for p in Path(r"D:\AIdianshangzongheti\output\内容").iterdir()
               if p.is_dir() and (p / "文案.md").is_file()],
              key=lambda p: p.stat().st_mtime, reverse=True)
raw = (dirs[0] / "文案.md").read_text(encoding="utf-8")
lines = raw.splitlines()
title = lines[0].lstrip("# ").strip()
body = "\n".join(lines[3:]).split("## 没依据的地方")[0].strip()

print("第一版标题：", title, f"（{len(title)} 字）")
print("第一版开头：", body[:60].replace("\n", " "))
print("第一版正文：", len(body), "字\n")

second = make_variant(title, body, load_config(), platform="头条")

print("第二版标题：", second["title"], f"（{len(second['title'])} 字）")
print("第二版开头：", second["body"][:60].replace("\n", " "))
print("第二版正文：", len(second["body"]), "字\n")

# 事实一致性粗检：数字是否都在第二版里
nums = set(re.findall(r"\d+(?:\.\d+)?", body))
miss = sorted(n for n in nums if n not in second["body"])
print("第一版里的数字共", len(nums), "个；第二版缺失：", miss or "无")
print("开头是否相同：", body[:20] == second["body"][:20])
