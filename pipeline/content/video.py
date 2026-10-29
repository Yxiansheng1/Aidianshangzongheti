"""视频：内容流水线的视频产出。

两种做法，按需选：

    slideshow()  图文轮播。几秒钟出片，稳定可控，国内内容号最常见的形式。
    ai_clip()    Wan2.2 图生视频。一段 2-3 秒要十几分钟，适合做氛围片头。

默认走 slideshow。ai_clip 慢，除非明确要，不然别用。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class VideoError(RuntimeError):
    pass


def ffmpeg_path() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise VideoError("找不到 ffmpeg。装一个：winget install Gyan.FFmpeg")
    return exe


def slideshow(
    images: list[Path | str],
    out_path: Path | str,
    *,
    width: int = 1080,
    height: int = 1440,
    seconds_per_image: float = 3.0,
    fps: int = 30,
    bg: str = "0x101010",
) -> Path:
    """把几张图拼成一个竖版轮播视频。

    每张停留 seconds_per_image 秒，统一缩放加黑边补边，输出 h264 mp4。
    小红书 / 头条 / 百家号都能直接传。
    """
    files = [Path(p) for p in images if Path(p).is_file()]
    if not files:
        raise VideoError("没有可用的图片")

    ffmpeg = ffmpeg_path()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 用 filter_complex 精确控制每张时长，避免 concat demuxer 末帧多算一份
    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []

    for index, f in enumerate(files):
        inputs += ["-loop", "1", "-t", str(seconds_per_image), "-i", str(f.resolve())]
        filters.append(
            f"[{index}:v]"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={bg},"
            f"setsar=1,fps={fps}[v{index}]"
        )
        labels.append(f"[v{index}]")

    filter_complex = ";".join(filters) + ";" + "".join(labels) + f"concat=n={len(files)}:v=1:a=0[out]"

    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=600)
    if result.returncode != 0:
        raise VideoError((result.stderr or "ffmpeg 失败")[-600:])

    if not out.is_file() or out.stat().st_size < 1024:
        raise VideoError("视频没生成出来")
    return out


def ai_clip(
    image: Path | str,
    prompt: str,
    out_path: Path | str,
    *,
    length: int = 33,
    width: int = 480,
    height: int = 832,
) -> Path:
    """Wan2.2 图生视频。很慢，8GB 显存一段 2 秒要十几分钟。"""
    from ..model.comfyui import ComfyClient, generate_video
    from ..config import load_config

    cfg = load_config()
    client = ComfyClient(cfg.local.comfyui_url)
    if not client.is_up():
        raise VideoError("ComfyUI 没在跑")

    return generate_video(
        client, image, prompt, out_path,
        unet_high=cfg.local.wan_unet_high,
        unet_low=cfg.local.wan_unet_low,
        clip=cfg.local.wan_clip,
        vae=cfg.local.wan_vae,
        clip_vision=cfg.local.wan_clip_vision,
        width=width, height=height, length=length,
        fps=cfg.local.video_fps, steps=cfg.local.video_steps,
        cfg=cfg.local.video_cfg, shift=cfg.local.video_shift,
        wait_timeout=cfg.local.video_timeout,
    )


def info(path: Path | str) -> dict[str, Any]:
    """读视频基本信息，发布前自检用。"""
    ffmpeg = ffmpeg_path()
    ffprobe = str(Path(ffmpeg).with_name("ffprobe.exe"))
    if not Path(ffprobe).is_file():
        ffprobe = shutil.which("ffprobe") or ffprobe

    p = Path(path)
    if not p.is_file():
        raise VideoError(f"文件不存在：{p}")

    result = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(p)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    if result.returncode != 0:
        return {"ok": False, "reason": (result.stderr or "")[-300:]}

    import json as _json
    data = _json.loads(result.stdout or "{}")
    fmt = data.get("format", {})
    stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})

    return {
        "ok": True,
        "size_mb": round(int(fmt.get("size", 0)) / 1024 / 1024, 2),
        "duration": round(float(fmt.get("duration", 0)), 1),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "codec": stream.get("codec_name"),
    }
