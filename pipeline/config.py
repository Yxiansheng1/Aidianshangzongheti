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
class AppConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    mxpage_output_dir: str = ""
    sau_cmd: str = "sau"
    platforms: list[str] = field(default_factory=list)
    dry_run: bool = True
    templates: dict[str, str] = field(default_factory=dict)
    source: Path | None = None

    @property
    def has_model(self) -> bool:
        return bool(self.model.api_key and self.model.base_url)


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

    cfg.mxpage_output_dir = data.get("mxpage", {}).get("output_dir", "")

    pub = data.get("publish", {})
    cfg.sau_cmd = pub.get("sau_cmd", cfg.sau_cmd)
    cfg.platforms = list(pub.get("platforms", []))
    cfg.dry_run = bool(pub.get("dry_run", True))
    cfg.templates = dict(pub.get("templates", {}))

    return cfg
