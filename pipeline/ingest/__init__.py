"""MxPage 产物解析。

约定（MxPage 输出目录结构）：

    output/
      渐变杯装蜡烛/          <- 一个商品一个文件夹，文件夹名 = 商品名
        hero-1.jpg
        hero-2.jpg
        detail-1.jpg
        title.txt            <- 可选，没有就用文件夹名
        body.txt             <- 可选，正文
        tags.txt             <- 可选，一行一个或用逗号分隔

也兼容「目录下直接放图片」的单商品情况。
"""

from __future__ import annotations

from .mxpage import Product, build_manifest, scan, slugify

__all__ = ["Product", "scan", "build_manifest", "slugify"]
