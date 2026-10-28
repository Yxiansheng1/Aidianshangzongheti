# samples

用来自测的文件，不含真实商品数据，图片是纯色占位图。

## 可以直接跑

```powershell
python -m pipeline ingest --dir "samples\示例输出" --out "samples\manifest.sample.json"
python -m pipeline publish --manifest "samples\manifest.sample.json" --platform xiaohongshu
```

预期结果：

- `ingest` 识别到 **2 个商品**
- `渐变杯装蜡烛` 识别到 4 张图，顺序是 `hero-1 → hero-2 → hero-10 → detail-1`
  （主图优先，数字自然排序，`hero-10` 不会排在 `hero-2` 前面）
- `桌面收纳抽屉盒` 会提示「无正文、无标签」——这是故意的，用来看缺字段的提示长什么样
- `publish` 默认只打印命令，不执行

## 目录就是约定

```
示例输出\
  渐变杯装蜡烛\        ← 文件夹名 = 商品名 = 默认标题
    hero-1.png         ← hero / 主图 / main / cover 开头 → 排最前
    hero-2.png
    hero-10.png
    detail-1.png       ← detail / 详情 开头 → 排在主图之后
    title.txt          ← 可选，覆盖标题
    body.txt           ← 可选，正文（多行会被压成一行）
    tags.txt           ← 可选，逗号或空格分隔
```

## 换成真实数据

MxPage 导出后，按上面的结构整理一次就行。真实商品不需要改代码，只需要整理文件夹。
