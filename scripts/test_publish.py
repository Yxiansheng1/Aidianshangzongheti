"""发布命令校验：不真的发，只用 sau 自己的 argparse 解析一遍。

这一步能抓出一类很贵的错：参数名写错、必填项漏了、某平台根本没有 --headed。
（20261030 实测：bilibili upload-video 没有 --headed，旧代码一律加，发一次挂一次。）

用 sau 的 venv 跑：
    D:\\social-auto-upload\\.venv\\Scripts\\python.exe scripts\\test_publish.py
"""
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.path.insert(0, r"D:\social-auto-upload")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.config import load_config, ROOT
from pipeline.content import publish as pub

try:
    from sau_cli import build_parser
except Exception as exc:  # noqa: BLE001
    raise SystemExit(f"导入 sau 的 parser 失败（要在 sau 的 venv 里跑）：{exc}")

IMAGE = ROOT / "output" / "内容" / "20261029-174959" / "img-1.png"
VIDEO = ROOT / "output" / "内容" / "20261029-174959" / "video.mp4"

TITLE = "Mistral 开源了新模型，但没说的是这三个数"
BODY = "正文占位，只用来校验命令参数，内容不重要。" * 3
TAGS = ["开源模型", "Mistral", "AI"]


def check(platform, kind):
    kwargs = dict(title=TITLE, body=BODY, tags=TAGS, cfg=load_config())
    kwargs["images"] = [str(IMAGE)] if kind == "note" else []
    kwargs["video"] = str(VIDEO) if kind == "video" else ""
    try:
        payload = pub.build(platform, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return False, f"构造失败：{str(exc)[:70]}", ""

    argv = payload["argv"][1:]  # 去掉 sau 可执行文件路径
    try:
        build_parser().parse_args(argv)
    except SystemExit:
        return False, "argparse 拒绝", payload["command"]

    extra = ""
    if "zhihu" in argv:
        extra = "（正文文件已生成）"
    return True, "ok" + extra, payload["command"]


def main():
    if not IMAGE.is_file():
        raise SystemExit(f"测试图不存在：{IMAGE}")
    if not VIDEO.is_file():
        raise SystemExit(f"测试视频不存在：{VIDEO}")

    rows = []
    for platform in list(pub.TARGETS) + list(pub.NO_PUBLISH_REASON):
        kinds = pub.kinds(platform)
        if not kinds:
            print(f"[SKIP] {platform:<5} 不支持发布（{pub.NO_PUBLISH_REASON.get(platform, '本轮不做')}）")
            rows.append((platform, "—", "不支持发布", True))
            continue
        for kind in kinds:
            ok, note, cmd = check(platform, kind)
            rows.append((platform, kind, note, ok))
            print(f"[{'OK ' if ok else 'FAIL'}] {platform:<5} {kind:<5} {note}")
            print(f"        {cmd}")

    bad = [r for r in rows if not r[3]]
    print("\n汇总：", "全部通过" if not bad else f"{len(bad)} 个失败")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
