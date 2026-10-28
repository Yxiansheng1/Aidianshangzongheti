"""命令行入口。

    python -m pipeline check
    python -m pipeline ingest --dir "D:\\MxPage\\output"
    python -m pipeline publish --platform xiaohongshu
    python -m pipeline publish --platform xiaohongshu --execute
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .checks import run_check
from .config import load_config
from .ingest.mxpage import build_manifest, scan
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

    errors = 0
    for product in products:
        for platform in platforms:
            plan = build_plan(
                product,
                platform,
                sau_cmd=cfg.sau_cmd,
                templates=cfg.templates,
            )
            if run(plan, execute=execute) != 0:
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
    p_pub.set_defaults(func=_cmd_publish)

    args = parser.parse_args(argv)
    return args.func(args)
