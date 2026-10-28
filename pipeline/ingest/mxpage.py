"""扫描 MxPage 输出目录，生成发布清单。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
IGNORED_DIRS = {".git", "__pycache__", "node_modules"}

META_TITLE = ("title", "标题")
META_BODY = ("body", "desc", "copy", "正文", "文案")
META_TAGS = ("tags", "标签")


def slugify(name: str) -> str:
    """把商品名转成一个稳定的 id。保留中文，其余替换成 -。"""
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", name, flags=re.UNICODE).strip("-").lower()
    return s or "product"


def _natural_key(path: Path) -> list:
    """让 hero-2 排在 hero-10 前面。"""
    parts = re.split(r"(\d+)", path.name)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


# 图片角色优先级：主图 → 详情图 → 其他。
# 发布时主图必须在前，否则小红书/抖音的封面会取到详情图。
ROLE_ORDER = (
    ("hero", 0),
    ("主图", 0),
    ("main", 0),
    ("cover", 0),
    ("detail", 1),
    ("详情", 1),
    ("desc", 1),
)


def _role_rank(path: Path) -> int:
    stem = path.stem.lower()
    for keyword, rank in ROLE_ORDER:
        if keyword in stem:
            return rank
    return 2


def _image_sort_key(path: Path) -> tuple:
    return (_role_rank(path), _natural_key(path))


def _read_meta(folder: Path, keys: tuple[str, ...]) -> str:
    for key in keys:
        for candidate in (folder / key, folder / f"{key}.txt", folder / f"{key}.md"):
            if candidate.is_file():
                try:
                    return candidate.read_text(encoding="utf-8", errors="replace").strip()
                except OSError:
                    continue
    return ""


def _read_tags(folder: Path) -> list[str]:
    raw = _read_meta(folder, META_TAGS)
    if not raw:
        return []
    parts = re.split(r"[,，\s\n]+", raw)
    return [p.strip().lstrip("#") for p in parts if p.strip()]


def _images_in(folder: Path) -> list[Path]:
    return sorted(
        (
            p
            for p in folder.rglob("*")
            if p.is_file()
            and p.suffix.lower() in IMAGE_EXTS
            and not any(part in IGNORED_DIRS for part in p.parts)
        ),
        key=_image_sort_key,
    )


@dataclass
class Product:
    id: str
    name: str
    dir: str
    images: list[str] = field(default_factory=list)
    title: str = ""
    body: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        """够不够发出去的最小条件：有图。"""
        return bool(self.images)


def scan(root: Path | str) -> list[Product]:
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"目录不存在：{root}")

    subdirs = [
        p for p in sorted(root.iterdir(), key=_natural_key)
        if p.is_dir() and p.name not in IGNORED_DIRS and not p.name.startswith(".")
    ]

    # 没有任何子目录 → 把 root 当成一个商品
    if not subdirs:
        if not _images_in(root):
            return []
        subdirs = [root]

    products: list[Product] = []
    for folder in subdirs:
        images = _images_in(folder)
        if not images:
            continue
        name = folder.name if folder != root else root.name
        products.append(
            Product(
                id=slugify(name),
                name=name,
                dir=str(folder),
                images=[str(p) for p in images],
                title=_read_meta(folder, META_TITLE) or name,
                body=_read_meta(folder, META_BODY),
                tags=_read_tags(folder),
            )
        )

    return products


def build_manifest(products: list[Product], source_dir: Path | str) -> dict:
    return {
        "schema": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_dir": str(source_dir),
        "count": len(products),
        "products": [asdict(p) for p in products],
    }
