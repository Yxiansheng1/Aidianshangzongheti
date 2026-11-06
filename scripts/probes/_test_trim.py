"""验硬截后的收尾：不能留半句话。"""
import sys

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.content.rewrite import _smart_truncate, _trim_incomplete

body = (
    "法国 Mistral 公开了 Mistral Large 4（代号 Le Chonk）的模型权重。一万亿参数，原生多模态。\n\n"
    "对用的人来说，重点是省钱。官方数据里，编程智能体指数 48%，每个任务少用 47% 词元。\n\n"
    "分数来自厂商和合作方的评测。如果您的活儿以中文长文档为主，或想本地部署却没有算力"
)
cut = _smart_truncate(body, 120)
print("硬截 :", repr(cut[-40:]))
print("修完 :", repr(_trim_incomplete(cut, 120)[-40:]))

# 结尾本来就是句号的，不该被改动
ok = "第一句。第二句。"
print("已是完整句:", _trim_incomplete(ok, 120) == ok)
