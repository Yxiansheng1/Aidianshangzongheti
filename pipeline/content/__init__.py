"""内容流水线（项目 B）。

和电商那套（选品 / 商品图 / 上架包 / 发布到店铺）**完全独立**，互不引用。

流程：
    抓热点文章 → 抓正文 → 按平台 skill 改写 → 审核 → 提取画面 → 文生图 → 发布

skills/ 目录下是给模型的指令，每个平台一份，可以直接编辑。

注意：这里导入函数时用了别名，避免 `rewrite` / `visual` 这些函数名
把同名的子模块遮住（Python 的包属性会被后导入的同名对象覆盖）。
"""

from .pipeline import run
from .rewrite import list_skills, load_skill
from .rewrite import rewrite as rewrite_text
from .visual import plan as plan_visuals
from .visual import render as render_visuals

__all__ = [
    "run",
    "rewrite_text",
    "load_skill",
    "list_skills",
    "plan_visuals",
    "render_visuals",
]
