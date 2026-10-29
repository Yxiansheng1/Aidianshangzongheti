"""验 _loads_loose：正常 JSON 不当截断，截断 JSON 能救回标题和正文。"""
import json
import sys

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.content.rewrite import _loads_loose

# 1) 正常 JSON
normal = json.dumps({"title": "标题", "body": "正文一段。\n\n第二段。",
                     "tags": ["a", "b"], "gaps": ["x"]}, ensure_ascii=False)
data, trunc = _loads_loose(normal)
print("正常:", trunc is False, data["title"], len(data["body"]))

# 2) 截断在正文字符串中间（真实出错时的样子）
broken = ('{\n  "title": "Mistral 开源 1 万亿参数",\n'
          '  "body": "第一段。\\n\\n第二段写到一半就断')
data, trunc = _loads_loose(broken)
print("截断:", trunc is True, "| title =", data.get("title"))
print("        body =", repr(data.get("body")))

# 3) 截断在引号之后、字段没闭合
broken2 = '{"title": "标题", "body": "完整正文。", "tags": ["a", "b'
data, trunc = _loads_loose(broken2)
print("半闭:", trunc is True, "| title =", data.get("title"), "| body =", data.get("body"))

# 4) 带代码围栏
fenced = '```json\n{"title": "t", "body": "b"}\n```'
data, trunc = _loads_loose(fenced)
print("围栏:", trunc is False, data)
