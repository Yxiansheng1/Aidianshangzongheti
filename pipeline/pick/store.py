"""候选品的读写。用 TOML——人可以直接编辑，不用写代码。"""

from __future__ import annotations

import tomllib
from pathlib import Path

from .score import Candidate, from_dict, to_dict

DEFAULT_FILE = Path("candidates.toml")

TEMPLATE = """# 选品候选池
#
# 用法：
#   1. 往下加 [[candidate]] 块，一个品一个块
#   2. 填 price（售价）、cost（1688 代发成本含运费）
#   3. scores 每项 1-5 分，看完 docs/05-选品口径.md 再打
#   4. 跑 python -m pipeline pick rank
#
# veto 里只要写一个，这个品就直接淘汰，不管分数多高。
# 可选项：license brand fragile size heavy custom ban

[[candidate]]
name = "渐变杯装蜡烛"
url = "https://detail.1688.com/offer/xxx.html"
price = 89.0
cost = 32.0
return_rate = 8
veto = []
note = "1688 三家现货代发"

[candidate.scores]
competition = 4
margin = 4
after_sale = 5
low_inquiry = 4
supply = 4
visual = 4
repeat = 2

[[candidate]]
name = "宠物自动饮水器"
url = ""
price = 129.0
cost = 58.0
return_rate = 15
veto = []
note = ""

[candidate.scores]
competition = 3
margin = 3
after_sale = 3
low_inquiry = 3
supply = 5
visual = 4
repeat = 4

[[candidate]]
name = "纯棉短袖T恤（反例）"
url = ""
price = 59.0
cost = 28.0
return_rate = 35
veto = ["size", "brand"]
note = "尺码售后 + 品牌风险，直接淘汰"

[candidate.scores]
competition = 1
margin = 3
after_sale = 2
low_inquiry = 2
supply = 4
visual = 2
repeat = 3
"""


def load(path: Path | str = DEFAULT_FILE) -> list[Candidate]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"找不到 {p}，先跑 `python -m pipeline pick init`")
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    return [from_dict(item) for item in data.get("candidate", [])]


def save(candidates: list[Candidate], path: Path | str = DEFAULT_FILE) -> Path:
    p = Path(path)
    lines: list[str] = ["# 由 pipeline pick 生成，可以手改\n"]
    for c in candidates:
        d = to_dict(c)
        lines.append("\n[[candidate]]")
        for key in ("name", "url", "price", "cost", "return_rate"):
            value = d[key]
            if isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            else:
                lines.append(f"{key} = {value}")
        veto = ", ".join(f'"{v}"' for v in d["veto"])
        lines.append(f"veto = [{veto}]")
        lines.append(f'note = "{d["note"]}"')
        lines.append("\n[candidate.scores]")
        for key, value in d["scores"].items():
            lines.append(f"{key} = {value}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def init(path: Path | str = DEFAULT_FILE) -> Path:
    p = Path(path)
    if p.exists():
        raise FileExistsError(f"{p} 已存在，不覆盖")
    p.write_text(TEMPLATE, encoding="utf-8")
    return p
