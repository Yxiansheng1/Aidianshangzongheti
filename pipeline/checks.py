"""环境自检。只读，不修改任何东西。"""

from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path

from .config import AppConfig
from .ingest.mxpage import scan
from .model.client import ModelError, OpenAICompatible
from .model.comfyui import ComfyClient, ComfyError
from .publish.sau import resolve_sau

OK = "[ OK ]"
WARN = "[WARN]"
FAIL = "[FAIL]"


def _line(status: str, label: str, detail: str = "") -> None:
    print(f"{status} {label:<20} {detail}".rstrip())


def run_check(cfg: AppConfig) -> int:
    failures = 0

    print("=" * 64)
    print(" AI 电商综合体 · 环境自检")
    print("=" * 64)

    # 1. Python
    version = ".".join(str(n) for n in sys.version_info[:3])
    if sys.version_info >= (3, 10):
        _line(OK, "Python", f"{version}  ({platform.system()})")
    else:
        _line(FAIL, "Python", f"{version}  —— 需要 3.10 及以上")
        failures += 1

    # 2. 配置文件
    if cfg.source:
        _line(OK, "config.toml", str(cfg.source))
    else:
        _line(WARN, "config.toml", "不存在，全部使用默认值（复制 config.example.toml 开始）")

    # 3. 模型接口
    if not cfg.has_model:
        _line(WARN, "模型接口", "未配置 api_key，跳过连通性测试")
    else:
        client = OpenAICompatible(
            base_url=cfg.model.base_url,
            api_key=cfg.model.api_key,
            timeout=cfg.model.timeout,
            text_model=cfg.model.text_model,
        )
        try:
            models = client.list_models()
            _line(OK, "模型接口", f"{cfg.model.base_url}  可用模型 {len(models)} 个")
            if not cfg.model.text_model:
                _line(WARN, "文本模型", "未配置 model.text_model")
            elif cfg.model.text_model in models:
                _line(OK, "文本模型", cfg.model.text_model)
            else:
                _line(WARN, "文本模型", f"{cfg.model.text_model} 不在返回列表里，确认名字")
        except ModelError as exc:
            _line(FAIL, "模型接口", str(exc).splitlines()[0])
            failures += 1

    # 4. 本地 ComfyUI
    local = ComfyClient(cfg.local.comfyui_url, timeout=5)
    if not local.is_up():
        _line(WARN, "ComfyUI", f"{cfg.local.comfyui_url} 未启动（跑 Start_Wan_8GB.bat）")
    else:
        _line(OK, "ComfyUI", cfg.local.comfyui_url)
        try:
            unets = local.node_options("UnetLoaderGGUF", "unet_name")
            if cfg.local.unet in unets:
                _line(OK, "本地图像模型", cfg.local.unet)
            else:
                _line(WARN, "本地图像模型", f"{cfg.local.unet} 不在列表里，检查 [local] unet")
            for label, node, field, want in (
                ("本地 CLIP", "CLIPLoader", "clip_name", cfg.local.clip),
                ("本地 VAE", "VAELoader", "vae_name", cfg.local.vae),
            ):
                options = local.node_options(node, field)
                if want in options:
                    _line(OK, label, want)
                else:
                    _line(WARN, label, f"{want} 不在列表里")

            # 视频三件套
            video_missing = [u for u in (cfg.local.wan_unet_high, cfg.local.wan_unet_low) if u not in unets]
            if video_missing:
                _line(WARN, "本地视频模型", f"缺 {', '.join(video_missing)}")
            else:
                _line(OK, "本地视频模型", "Wan2.2 I2V 双模型齐全")
            clip_options = local.node_options("CLIPLoader", "clip_name")
            if cfg.local.wan_clip in clip_options:
                _line(OK, "视频文本编码器", cfg.local.wan_clip)
            else:
                _line(WARN, "视频文本编码器", f"{cfg.local.wan_clip} 不在列表里")
            vae_options = local.node_options("VAELoader", "vae_name")
            if cfg.local.wan_vae in vae_options:
                _line(OK, "视频 VAE", cfg.local.wan_vae)
            else:
                _line(WARN, "视频 VAE", f"{cfg.local.wan_vae} 不在列表里")
            vision_options = local.node_options("CLIPVisionLoader", "clip_name")
            if cfg.local.wan_clip_vision in vision_options:
                _line(OK, "视频 CLIP Vision", cfg.local.wan_clip_vision)
            else:
                _line(WARN, "视频 CLIP Vision", f"{cfg.local.wan_clip_vision} 不在列表里")
        except ComfyError as exc:
            _line(WARN, "本地模型", str(exc).splitlines()[0])

    # 5. MxPage 输出目录
    if not cfg.mxpage_output_dir:
        _line(WARN, "MxPage 输出目录", "未配置 mxpage.output_dir")
    else:
        folder = Path(cfg.mxpage_output_dir)
        if not folder.is_dir():
            _line(WARN, "MxPage 输出目录", f"{folder} 不存在（还没导出过？）")
        else:
            try:
                products = scan(folder)
            except OSError as exc:
                _line(FAIL, "MxPage 输出目录", str(exc))
                failures += 1
            else:
                if products:
                    _line(OK, "MxPage 输出目录", f"{folder}  识别到 {len(products)} 个商品")
                    for product in products[:5]:
                        print(f"         · {product.name}（{len(product.images)} 张图）")
                    if len(products) > 5:
                        print(f"         · 还有 {len(products) - 5} 个未显示")
                else:
                    _line(WARN, "MxPage 输出目录", f"{folder} 里没有找到图片")

    # 6. 发布工具
    if not cfg.sau_cmd:
        _line(WARN, "发布工具 sau", "未配置 publish.sau_cmd")
    else:
        found = resolve_sau(cfg.sau_cmd, cfg.sau_cwd)
        if Path(found).exists() or shutil.which(found):
            _line(OK, "发布工具 sau", found)
        else:
            _line(WARN, "发布工具 sau", f"找不到 {cfg.sau_cmd!r}（安装清单第 2 步还没做）")

    # 7. 发布账号登录态
    if cfg.platforms and cfg.sau_cwd:
        for platform in cfg.platforms:
            account = cfg.accounts.get(platform, "")
            if not account:
                _line(WARN, f"账号 {platform}", "config.toml 里没有 [publish.accounts] 配置")
                continue
            cookie = Path(cfg.sau_cwd) / "cookies" / f"{platform}_{account}.json"
            if cookie.is_file():
                _line(OK, f"账号 {platform}", f"{cookie.name}（已登录过）")
            else:
                _line(WARN, f"账号 {platform}", f"未登录，跑 sau {platform} login --account {account} --headed")

    print("-" * 64)
    if failures:
        print(f" 有 {failures} 项阻塞问题，先解决再往下走。")
    else:
        print(" 没有阻塞问题。")
    return failures
