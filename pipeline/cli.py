"""命令行入口。

    python -m pipeline check
    python -m pipeline ingest --dir "D:\\MxPage\\output"
    python -m pipeline publish --platform xiaohongshu
    python -m pipeline publish --platform xiaohongshu --execute
"""

from __future__ import annotations

import argparse
import json
import time
import unicodedata
from pathlib import Path

from .checks import run_check
from .config import load_config
from .ingest.mxpage import build_manifest, scan
from .model.comfyui import ComfyClient, ComfyError, generate, generate_video
from .listing import build_all as build_packages
from .pick import store as pick_store
from .pick.score import LABELS, WEIGHTS, rank as rank_candidates
from .publish.sau import build_plan, resolve_sau, run


def _add_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="配置文件路径，默认 ./config.toml")


def _cmd_check(args: argparse.Namespace) -> int:
    return run_check(load_config(args.config))


def _cmd_ingest(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    source = args.dir or cfg.mxpage_output_dir
    if not source:
        print("没有指定目录。用 --dir，或在 config.toml 里配置 mxpage.output_dir")
        return 2

    try:
        products = scan(source)
    except OSError as exc:
        print(f"读取失败：{exc}")
        return 1

    if not products:
        print(f"{source} 里没有识别到商品（至少需要一张图片）")
        return 1

    manifest = build_manifest(products, source)
    out = Path(args.out)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"识别到 {len(products)} 个商品，清单写入 {out.resolve()}")
    for product in products:
        missing = []
        if not product.body:
            missing.append("无正文")
        if not product.tags:
            missing.append("无标签")
        note = f"   ⚠ {', '.join(missing)}" if missing else ""
        print(f"  · {product.name}  {len(product.images)} 张图{note}")
    return 0


def _cmd_gen(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    client = ComfyClient(cfg.local.comfyui_url)

    if not client.is_up():
        print(f"ComfyUI 没在跑（{cfg.local.comfyui_url}）")
        print("先启动：D:\\AI\\ComfyUI_windows_portable\\Start_Wan_8GB.bat（8GB 显存用这个）")
        return 2

    out = args.out or str(Path(args.image).with_name(Path(args.image).stem + "-gen.png"))

    try:
        path = generate(
            client,
            args.image,
            args.prompt,
            out,
            unet=cfg.local.unet,
            clip=cfg.local.clip,
            vae=cfg.local.vae,
            width=args.width or cfg.local.width,
            height=args.height or cfg.local.height,
            steps=args.steps or cfg.local.steps,
            cfg=args.cfg if args.cfg is not None else cfg.local.cfg,
            shift=cfg.local.shift,
            seed=args.seed,
            wait_timeout=cfg.local.wait_timeout,
        )
    except ComfyError as exc:
        print(f"失败：{exc}")
        return 1

    print(f"完成：{path.resolve()}  ({path.stat().st_size / 1024:.0f} KB)")
    return 0


def _cmd_vid(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    client = ComfyClient(cfg.local.comfyui_url)

    if not client.is_up():
        print(f"ComfyUI 没在跑（{cfg.local.comfyui_url}）")
        print("先启动：D:\\AI\\ComfyUI_windows_portable\\Start_Wan_8GB.bat")
        return 2

    out = args.out or str(Path(args.image).with_suffix(".mp4"))

    t0 = time.time()
    try:
        path = generate_video(
            client,
            args.image,
            args.prompt,
            out,
            unet_high=cfg.local.wan_unet_high,
            unet_low=cfg.local.wan_unet_low,
            clip=cfg.local.wan_clip,
            vae=cfg.local.wan_vae,
            clip_vision=cfg.local.wan_clip_vision,
            width=args.width or cfg.local.video_width,
            height=args.height or cfg.local.video_height,
            length=args.length or cfg.local.video_length,
            fps=args.fps or cfg.local.video_fps,
            steps=args.steps or cfg.local.video_steps,
            cfg=args.cfg if args.cfg is not None else cfg.local.video_cfg,
            shift=cfg.local.video_shift,
            seed=args.seed,
            wait_timeout=cfg.local.video_timeout,
        )
    except ComfyError as exc:
        print(f"失败：{exc}")
        return 1

    print(f"完成：{path.resolve()}  ({path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"耗时：{time.time() - t0:.0f} 秒")
    return 0


def _disp_width(text: str) -> int:
    """中文占两格，不然表格会错位。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(text))


def _pad(text: str, width: int, right: bool = False) -> str:
    gap = max(0, width - _disp_width(text))
    return (" " * gap + text) if right else (text + " " * gap)


def _cmd_pick(args: argparse.Namespace) -> int:
    if args.pick_action == "init":
        try:
            path = pick_store.init(args.file)
        except FileExistsError as exc:
            print(exc)
            return 1
        print(f"已生成 {path.resolve()}")
        print("打开它，把你的候选品填进去，然后跑：python -m pipeline pick rank")
        return 0

    try:
        candidates = pick_store.load(args.file)
    except FileNotFoundError as exc:
        print(exc)
        return 2

    if not candidates:
        print("候选池里没有品。用 `python -m pipeline pick init` 生成模板。")
        return 1

    ordered = rank_candidates(candidates)
    if args.top:
        ordered = ordered[: args.top]

    headers = ["#", "候选品", "总分", "评级", "售价", "毛利率", "否决项"]
    rows: list[list[str]] = []
    for index, c in enumerate(ordered, 1):
        _, rate = c.margin()
        rows.append([
            str(index),
            c.name or "未命名",
            f"{c.total():.1f}",
            c.grade(),
            f"{c.price:.0f}",
            f"{rate * 100:.1f}%",
            c.veto_hit() or "—",
        ])

    widths = [
        max([_disp_width(headers[i])] + [_disp_width(r[i]) for r in rows])
        for i in range(len(headers))
    ]

    def line(cells: list[str]) -> str:
        return "  ".join(_pad(cell, widths[i], right=(i >= 2)) for i, cell in enumerate(cells))

    print(line(headers))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(line(row))

    print()
    if len(candidates) < 5:
        print(f"⚠ 只有 {len(candidates)} 个候选。少于 5 个时结论不可靠，容易是矬子里拔将军。")

    best = ordered[0]
    if best.veto_hit():
        print("没有能做的品：排名第一的也被一票否决了。换一批候选。")
    elif best.total() < 60:
        print(f"最高分只有 {best.total():.1f}，没到备选线（60）。这批品都不值得拿样。")
    else:
        profit, _ = best.margin()
        print(f"建议先拿样：{best.name}（{best.total():.1f} 分 / {best.grade()} / 单件毛利 ¥{profit:.1f}）")
        print("只拿前 2 名的样，不要超过 3 个。")
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    from .gui.server import serve

    serve(port=args.port, open_browser=args.open)
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    from .analyze import ProductBrief, analyze, build_prompt, render_markdown
    from .fetch import FetchError, fetch
    from .model.client import ModelError

    cfg = load_config(args.config)
    brief = ProductBrief(
        name=args.name or "",
        url=args.url or "",
        price=args.price or "",
        description=args.desc or "",
        extra=args.extra or "",
    )

    if args.url:
        try:
            page = fetch(args.url)
        except FetchError as exc:
            print(f"链接有问题：{exc}")
            return 2
        brief.site = page.site
        brief.fetch_note = page.note
        brief.name = brief.name or page.title
        brief.description = brief.description or page.description
        brief.price = brief.price or page.price
        if not page.ok:
            print(f"⚠ {page.note}")
            print("  用 --name / --desc / --extra 补充信息，否则分析会很空。\n")

    if not (brief.name or brief.description or brief.extra):
        print("没有商品信息。至少给一个：--url / --name / --desc / --extra")
        return 2

    if args.dry_run:
        print("=== 将发给模型的提示词 ===")
        print(build_prompt(brief))
        return 0

    try:
        result = analyze(brief, cfg)
    except ModelError as exc:
        print(f"失败：{exc}")
        return 1

    markdown = render_markdown(result, brief)
    out = Path(args.out or (Path("output") / "分析" / f"{(brief.name or '商品')[:20]}.md"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    out.with_suffix(".json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(markdown)
    print(f"\n已保存：{out.resolve()}")
    print(f"         {out.with_suffix('.json').resolve()}")
    return 0


def _cmd_trends(args: argparse.Namespace) -> int:
    from .trends import collect, render_markdown, save

    cfg = load_config(args.config)
    sources = [s.strip() for s in args.sources.split(",")] if args.sources else None
    categories = [c.strip() for c in args.category.split(",")] if args.category else None

    result = collect(
        sources=sources,
        keywords=cfg.trends.keywords or None,
        proxy=cfg.trends.proxy or None,
        categories=categories,
    )

    print(render_markdown(result))

    if args.save:
        path = save(result, Path("output") / "热点")
        print(f"已保存：{path.resolve()}")
    return 0


def _cmd_write(args: argparse.Namespace) -> int:
    from .model.client import ModelError
    from .review import render_markdown as render_review
    from .review import review
    from .writer import PLATFORMS, render_markdown, write

    cfg = load_config(args.config)

    if args.platform not in PLATFORMS:
        print(f"不支持的平台：{args.platform}")
        print(f"可选：{', '.join(PLATFORMS)}")
        return 2

    try:
        result = write(
            args.topic,
            args.platform,
            cfg,
            product=args.product or "",
            extra=args.extra or "",
            tone=args.tone or "",
        )
    except (ModelError, ValueError) as exc:
        print(f"失败：{exc}")
        return 1

    print(render_markdown(result))

    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_markdown(result), encoding="utf-8")
        print(f"\n已保存：{target.resolve()}")

    if args.review:
        print()
        combined = f"{result['title']}\n\n{result['body']}"
        outcome = review(combined, args.platform, cfg)
        print(render_review(outcome))

    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    from .model.client import ModelError
    from .review import render_markdown, review

    cfg = load_config(args.config)

    if args.file:
        path = Path(args.file)
        if not path.is_file():
            print(f"找不到文件：{path}")
            return 2
        text = path.read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        print("给一个 --file 或 --text")
        return 2

    try:
        result = review(text, args.platform, cfg, use_ai=not args.no_ai)
    except (ModelError, ValueError) as exc:
        print(f"失败：{exc}")
        return 1

    print(render_markdown(result))
    return 0 if result.passed else 1


def _cmd_content(args: argparse.Namespace) -> int:
    from .content import pipeline as content_pipeline
    from .content.rewrite import load_skill, list_skills, render_markdown

    cfg = load_config(args.config)

    if args.skills:
        print("可用 skill：" + "、".join(list_skills()))
        return 0

    if not args.url and not args.file:
        print("给一个 --url，或者 --file 传一个本地文本文件")
        return 2

    article = None
    if args.file:
        path = Path(args.file)
        if not path.is_file():
            print(f"找不到文件：{path}")
            return 2
        article = {
            "title": args.topic or path.stem,
            "text": path.read_text(encoding="utf-8"),
        }

    try:
        load_skill(args.platform)
    except FileNotFoundError as exc:
        print(exc)
        return 2

    print(f"开始跑：{args.url or args.file}  →  {args.platform}"
          + (f"（题材：{args.mode}）" if getattr(args, "mode", "") else "") + "\n")
    result = content_pipeline.run(
        args.url or "",
        cfg,
        platform=args.platform,
        mode=getattr(args, "mode", "") or "",
        images=args.images,
        draw=not args.no_draw,
        article=article,
    )

    for name, step in result["steps"].items():
        ok = step.get("ok")
        mark = "OK " if ok else "ERR"
        detail = ""
        if name == "fetch":
            detail = f'{step.get("chars", 0)} 字' if ok else step.get("reason", "")
        elif name == "rewrite":
            detail = f'{step.get("length", 0)} 字' if ok else step.get("reason", "")
        elif name == "review":
            if ok:
                detail = f'{"通过" if step.get("passed") else "不通过"} {step.get("score")} 分　{len(step.get("issues") or [])} 个问题'
            else:
                detail = step.get("reason", "")
        elif name == "visual":
            detail = f'{step.get("count", 0)} 张' if ok else step.get("reason", "")
            if step.get("skipped"):
                detail = "已跳过"
        print(f"  [{mark}] {name:<8} {detail}")

    print()
    if "draft" in result:
        print(render_markdown(result["draft"]))
    if result.get("dir"):
        print(f"\n产物目录：{result['dir']}")

    return 0 if result.get("ok") else 1


def _cmd_package(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print(f"找不到清单 {manifest_path}，先跑 `python -m pipeline ingest`")
        return 2

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not (data.get("products") or []):
        print("清单里没有商品。")
        return 2

    out_root = Path(args.out or "output/上架包")
    results = build_packages(data, out_root, cfg)

    print(f"生成 {len(results)} 个上架包 → {out_root.resolve()}\n")
    for item in results:
        print(f"  · {item.name}  {item.images} 张图")
        print(f"    {item.dir}")
    print("\n打开每个包里的「上架指引.md」，照着做。")
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print(f"找不到清单 {manifest_path}，先跑 `python -m pipeline ingest`")
        return 2

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    products = data.get("products", [])
    if not products:
        print("清单里没有商品。")
        return 2

    platforms = args.platform or cfg.platforms
    if not platforms:
        print("没有指定平台。用 --platform，或在 config.toml 里配置 publish.platforms")
        return 2

    execute = bool(args.execute) and not cfg.dry_run
    if args.execute and cfg.dry_run:
        print("config.toml 里 dry_run = true，本次只打印计划。要真正执行请改成 false。")

    missing = [p for p in platforms if not cfg.accounts.get(p)]
    if missing:
        print("缺少账号配置。在 config.toml 里补上：\n")
        print("  [publish.accounts]")
        for p in missing:
            print(f'  {p} = "main"')
        print("\naccount 名是你在 `sau <platform> login --account <名字>` 时自己起的。")
        return 2

    errors = 0
    sau_cmd = resolve_sau(cfg.sau_cmd, cfg.sau_cwd)
    for product in products:
        kind = args.kind or ("video" if product.get("video") else "note")
        for platform in platforms:
            try:
                plan = build_plan(
                    product,
                    platform,
                    account=cfg.accounts[platform],
                    sau_cmd=sau_cmd,
                    kind=kind,
                    schedule=args.schedule,
                    headed=args.headed,
                    zhihu_category=cfg.zhihu_category,
                )
            except (ValueError, FileNotFoundError) as exc:
                print(f"[跳过] {platform:<12} {product.get('name')}：{exc}")
                errors += 1
                continue
            if run(plan, execute=execute, cwd=cfg.sau_cwd or None) != 0:
                errors += 1

    total = len(products) * len(platforms)
    print(f"\n共 {len(products)} 个商品 × {len(platforms)} 个平台 = {total} 条任务")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="AI 电商综合体：MxPage 产物 → 多平台发布",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="环境自检")
    _add_config(p_check)
    p_check.set_defaults(func=_cmd_check)

    p_ingest = sub.add_parser("ingest", help="扫描 MxPage 输出目录，生成发布清单")
    _add_config(p_ingest)
    p_ingest.add_argument("--dir", help="覆盖 config.toml 里的 mxpage.output_dir")
    p_ingest.add_argument("--out", default="manifest.json", help="清单输出路径")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_gen = sub.add_parser("gen", help="本地生成一张图（ComfyUI + Qwen-Image-Edit）")
    _add_config(p_gen)
    p_gen.add_argument("--image", required=True, help="商品原图路径")
    p_gen.add_argument("--prompt", required=True, help="想改成什么样，例如：放到木桌上，晨光，浅景深")
    p_gen.add_argument("--out", help="输出路径，默认在原图旁边加 -gen")
    p_gen.add_argument("--width", type=int, help="默认取 config.toml")
    p_gen.add_argument("--height", type=int)
    p_gen.add_argument("--steps", type=int)
    p_gen.add_argument("--cfg", type=float)
    p_gen.add_argument("--seed", type=int, default=0)
    p_gen.set_defaults(func=_cmd_gen)

    p_vid = sub.add_parser("vid", help="本地图生视频（ComfyUI + Wan2.2 I2V）")
    _add_config(p_vid)
    p_vid.add_argument("--image", required=True, help="起始图路径，通常用 gen 出的主图")
    p_vid.add_argument("--prompt", required=True, help="描述画面怎么动")
    p_vid.add_argument("--out", help="输出 mp4 路径，默认与原图同名")
    p_vid.add_argument("--width", type=int)
    p_vid.add_argument("--height", type=int)
    p_vid.add_argument("--length", type=int, help="帧数，必须是 4n+1（33/49/65/81）")
    p_vid.add_argument("--fps", type=int)
    p_vid.add_argument("--steps", type=int)
    p_vid.add_argument("--cfg", type=float)
    p_vid.add_argument("--seed", type=int, default=0)
    p_vid.set_defaults(func=_cmd_vid)

    p_pick = sub.add_parser("pick", help="选品打分：给候选池排序")
    _add_config(p_pick)
    pick_actions = p_pick.add_subparsers(dest="pick_action", required=True)

    p_pick_init = pick_actions.add_parser("init", help="生成候选池模板")
    p_pick_init.add_argument("--file", default="candidates.toml")

    p_pick_rank = pick_actions.add_parser("rank", help="排序并给建议")
    p_pick_rank.add_argument("--file", default="candidates.toml")
    p_pick_rank.add_argument("--top", type=int, help="只显示前 N 名")

    p_pick.set_defaults(func=_cmd_pick)

    p_gui = sub.add_parser("gui", help="打开本地 Web 界面（零依赖）")
    _add_config(p_gui)
    p_gui.add_argument("--port", type=int, default=8899, help="端口，默认 8899")
    p_gui.add_argument("--open", action="store_true", help="自动打开浏览器")
    p_gui.set_defaults(func=_cmd_gui)

    p_pkg = sub.add_parser("package", help="生成上架资料包（淘宝/拼多多上架前准备）")
    _add_config(p_pkg)
    p_pkg.add_argument("--manifest", default="manifest.json")
    p_pkg.add_argument("--out", help="输出目录，默认 output/上架包")
    p_pkg.set_defaults(func=_cmd_package)

    p_an = sub.add_parser("analyze", help="商品分析 + 生图/视频文案（需要文本模型）")
    _add_config(p_an)
    p_an.add_argument("--url", help="商品链接。抓不到内容时会提示你补充")
    p_an.add_argument("--name", help="商品名")
    p_an.add_argument("--price", help="售价或成本")
    p_an.add_argument("--desc", help="商品描述/参数，可以从页面复制")
    p_an.add_argument("--extra", help="任何补充信息：材质、人群、竞品、你的判断")
    p_an.add_argument("--out", help="输出 md 路径")
    p_an.add_argument("--dry-run", action="store_true", help="只打印提示词，不调模型")
    p_an.set_defaults(func=_cmd_analyze)

    p_tr = sub.add_parser("trends", help="抓热点（国内 + 国外），按分类列菜单")
    _add_config(p_tr)
    p_tr.add_argument("--sources", help="来源，逗号分隔。可选：baidu weibo hn arxiv techcrunch verge ars googlenews bbc defense")
    p_tr.add_argument("--category", help="分类，逗号分隔。可选：国内热搜 AI与科技 国际时事 军事")
    p_tr.add_argument("--save", action="store_true", help="同时保存到 output/热点/日期.md")
    p_tr.set_defaults(func=_cmd_trends)

    p_wr = sub.add_parser("write", help="AI 改写：把主题写成各平台能发的稿子")
    _add_config(p_wr)
    p_wr.add_argument("--topic", required=True, help="主题或热点标题")
    p_wr.add_argument("--platform", required=True,
                      help="xiaohongshu / zhihu / baijiahao / dayu / douyin")
    p_wr.add_argument("--product", help="要推广的商品")
    p_wr.add_argument("--extra", help="补充信息")
    p_wr.add_argument("--tone", help="语气，例如 轻松 / 专业 / 克制")
    p_wr.add_argument("--out", help="保存到文件")
    p_wr.add_argument("--review", action="store_true", help="生成后立即跑一遍审核")
    p_wr.set_defaults(func=_cmd_write)

    p_rv = sub.add_parser("review", help="AI 审核：发文前查禁词和夸大表述")
    _add_config(p_rv)
    p_rv.add_argument("--file", help="要审的文件路径")
    p_rv.add_argument("--text", help="直接给一段文字")
    p_rv.add_argument("--platform", default="xiaohongshu", help="目标平台")
    p_rv.add_argument("--no-ai", action="store_true", help="只用规则层，不调模型（快且免费）")
    p_rv.set_defaults(func=_cmd_review)

    p_ct = sub.add_parser("content", help="内容流水线（项目B）：抓文章 → 改写 → 审核 → 配图")
    _add_config(p_ct)
    p_ct.add_argument("--url", help="文章链接")
    p_ct.add_argument("--file", help="本地文本文件（代替 --url）")
    p_ct.add_argument("--topic", help="主题，默认用文章标题")
    p_ct.add_argument("--platform", default="小红书", help="用哪个 skill，默认 小红书")
    p_ct.add_argument("--mode", default="", help="题材：政策解读 / 国际军事 / 历史（可留空）")
    p_ct.add_argument("--images", type=int, default=2, help="生成几张配图，默认 2")
    p_ct.add_argument("--no-draw", action="store_true", help="只写文案，不出图")
    p_ct.add_argument("--skills", action="store_true", help="列出可用的 skill")
    p_ct.set_defaults(func=_cmd_content)

    p_pub = sub.add_parser("publish", help="按清单发布")
    _add_config(p_pub)
    p_pub.add_argument("--manifest", default="manifest.json", help="清单路径")
    p_pub.add_argument(
        "--platform",
        action="append",
        help="可重复指定，如 --platform xiaohongshu --platform douyin",
    )
    p_pub.add_argument(
        "--execute",
        action="store_true",
        help="真正执行（还要求 config.toml 里 dry_run = false）",
    )
    p_pub.add_argument("--kind", choices=["note", "video"], help="发布形态，默认按商品有无 video 自动判断")
    p_pub.add_argument("--schedule", help='定时发布，格式 "2026-11-01 10:00"')
    p_pub.add_argument("--headed", action="store_true", help="带浏览器界面跑，排查问题时用")
    p_pub.set_defaults(func=_cmd_publish)

    args = parser.parse_args(argv)
    return args.func(args)
