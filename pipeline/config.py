"""配置加载。

配置文件是 config.toml（已被 git 忽略）。没有配置文件时全部使用默认值，
让 `python -m pipeline check` 在什么都没装的情况下也能跑起来。
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.toml"


@dataclass
class ModelConfig:
    # 默认指向本地 one-api；第一阶段直接改成供应商地址也可以
    base_url: str = "http://127.0.0.1:3000/v1"
    api_key: str = ""
    text_model: str = ""
    image_model: str = ""
    timeout: int = 60


@dataclass
class LocalConfig:
    """本地 ComfyUI。不花钱，但慢——8GB 显存跑 20GB 模型要忍耐。"""

    comfyui_url: str = "http://127.0.0.1:8188"
    unet: str = "qwen-image-edit-2511-Q8_0.gguf"
    clip: str = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
    vae: str = "qwen_image_vae.safetensors"
    steps: int = 20
    cfg: float = 2.5
    shift: float = 3.1
    width: int = 1024
    height: int = 1024
    wait_timeout: int = 900


@dataclass
class AppConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    local: LocalConfig = field(default_factory=LocalConfig)
    mxpage_output_dir: str = ""
    sau_cmd: str = "sau"
    platforms: list[str] = field(default_factory=list)
    dry_run: bool = True
    templates: dict[str, str] = field(default_factory=dict)
    source: Path | None = None

    @property
    def has_model(self) -> bool:
        key = self.model.api_key.strip()
        # 占位符（含中文）也当成「没配置」，避免拿它去发请求
        return bool(key and key.isascii() and self.model.base_url)


def load_config(path: Path | str | None = None) -> AppConfig:
    p = Path(path) if path else DEFAULT_CONFIG
    cfg = AppConfig()

    if not p.is_file():
        return cfg

    data = tomllib.loads(p.read_text(encoding="utf-8"))
    cfg.source = p

    raw_model = data.get("model", {})
    known = set(ModelConfig.__dataclass_fields__)
    cfg.model = ModelConfig(**{k: v for k, v in raw_model.items() if k in known})

    raw_local = data.get("local", {})
    known_local = set(LocalConfig.__dataclass_fields__)
    cfg.local = LocalConfig(**{k: v for k, v in raw_local.items() if k in known_local})

    cfg.mxpage_output_dir = data.get("mxpage", {}).get("output_dir", "")

    pub = data.get("publish", {})
    cfg.sau_cmd = pub.get("sau_cmd", cfg.sau_cmd)
    cfg.platforms = list(pub.get("platforms", []))
    cfg.dry_run = bool(pub.get("dry_run", True))
    cfg.templates = dict(pub.get("templates", {}))

    return cfg
