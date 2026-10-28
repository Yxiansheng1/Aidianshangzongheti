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
from .pick import store as pick_store
from .pick.score import LABELS, WEIGHTS, rank as rank_candidates
from .publish.sau import build_plan, run


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
    for product in products:
        kind = args.kind or ("video" if product.get("video") else "note")
        for platform in platforms:
            try:
                plan = build_plan(
                    product,
                    platform,
                    account=cfg.accounts[platform],
                    sau_cmd=cfg.sau_cmd,
                    kind=kind,
                    schedule=args.schedule,
                    headed=args.headed,
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
