"""本地 Web 界面。只用标准库，不需要 pip install 任何东西。"""

from __future__ import annotations

import json
import mimetypes
import time
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ..config import ROOT, load_config
from ..ingest.mxpage import build_manifest, scan
from ..model.comfyui import ComfyClient, ComfyError, generate, generate_video
from ..pick import store as pick_store
from ..pick.score import LABELS, VETO_LABELS, rank as rank_candidates
from ..publish.sau import build_plan, resolve_sau, run as run_plan

UI_FILE = Path(__file__).with_name("ui.html")
UPLOAD_DIR = ROOT / "input_uploads"
OUTPUT_DIR = ROOT / "output"


# ------------------------------------------------------------------ 工具


def _safe_path(raw: str) -> Path | None:
    """只允许读仓库目录内的文件，挡住路径穿越。"""
    try:
        target = Path(raw).resolve()
        target.relative_to(ROOT.resolve())
    except (OSError, ValueError):
        return None
    return target if target.is_file() else None


def _status() -> dict[str, Any]:
    cfg = load_config()
    local = ComfyClient(cfg.local.comfyui_url, timeout=3)
    comfy = local.is_up()

    unets: list[str] = []
    if comfy:
        try:
            unets = local.node_options("UnetLoaderGGUF", "unet_name")
        except ComfyError:
            unets = []

    return {
        "comfy": comfy,
        "comfy_url": cfg.local.comfyui_url,
        "image_model": cfg.local.unet if cfg.local.unet in unets else None,
        "video_model": (
            "Wan2.2 I2V"
            if cfg.local.wan_unet_high in unets and cfg.local.wan_unet_low in unets
            else None
        ),
        "sau_cmd": cfg.sau_cmd,
        "dry_run": cfg.dry_run,
        "platforms": cfg.platforms,
        "accounts": cfg.accounts,
        "wx_ready": bool(cfg.model.api_key),
    }


def _candidates_payload() -> dict[str, Any]:
    try:
        items = pick_store.load(pick_store.DEFAULT_FILE)
    except FileNotFoundError:
        return {"exists": False, "rows": [], "advice": ""}

    ordered = rank_candidates(items)
    rows = []
    for index, c in enumerate(ordered, 1):
        profit, rate = c.margin()
        rows.append({
            "rank": index,
            "name": c.name or "未命名",
            "total": round(c.total(), 1),
            "grade": c.grade(),
            "price": c.price,
            "cost": c.cost,
            "rate": round(rate * 100, 1),
            "profit": round(profit, 1),
            "veto": c.veto_hit() or "",
            "note": c.note,
        })

    advice = ""
    if rows:
        best = ordered[0]
        if best.veto_hit():
            advice = "没有能做的品：排名第一的也被一票否决了。换一批候选。"
        elif best.total() < 60:
            advice = f"最高分只有 {best.total():.1f}，没到备选线（60）。这批都不值得拿样。"
        else:
            advice = f"建议先拿样：{best.name}（{best.total():.1f} 分 / {best.grade()}）"
        if len(items) < 5:
            advice += f"　⚠ 只有 {len(items)} 个候选，少于 5 个时结论不可靠。"

    return {
        "exists": True,
        "rows": rows,
        "advice": advice,
        "dims": LABELS,
        "veto_labels": VETO_LABELS,
    }


# ------------------------------------------------------------------ 任务


def _cfg_from(params: dict[str, Any]):
    return load_config()


def start_gen(params: dict[str, Any]):
    source = Path(str(params.get("source", "")))
    prompt = str(params.get("prompt", "")).strip()
    if not source.is_file():
        raise ValueError("先选一张原图")
    if not prompt:
        raise ValueError("提示词不能为空")

    size = int(params.get("size") or 1024)
    steps = int(params.get("steps") or 0)

    def work(job):
        cfg = _cfg_from(params)
        client = ComfyClient(cfg.local.comfyui_url)
        if not client.is_up():
            raise ComfyError("ComfyUI 没在跑，先去启动 Start_Wan_8GB.bat")

        job.message = "正在提交并加载模型…"
        out = OUTPUT_DIR / f"{source.stem}-gen-{int(time.time())}.png"
        job.message = "生成中。8GB 显存约 8 分钟，先去倒杯水"
        path = generate(
            client,
            source,
            prompt,
            out,
            unet=cfg.local.unet,
            clip=cfg.local.clip,
            vae=cfg.local.vae,
            width=size,
            height=size,
            steps=steps or cfg.local.steps,
            cfg=cfg.local.cfg,
            shift=cfg.local.shift,
            wait_timeout=cfg.local.wait_timeout,
        )
        return {
            "path": str(path),
            "url": "/file?path=" + urllib.parse.quote(str(path)),
            "name": path.name,
        }

    from .jobs import REGISTRY

    return REGISTRY.submit("image", work)


def start_vid(params: dict[str, Any]):
    source = Path(str(params.get("source", "")))
    prompt = str(params.get("prompt", "")).strip()
    if not source.is_file():
        raise ValueError("先选一张起始图")
    if not prompt:
        raise ValueError("提示词不能为空")

    length = int(params.get("length") or 33)

    def work(job):
        cfg = _cfg_from(params)
        client = ComfyClient(cfg.local.comfyui_url)
        if not client.is_up():
            raise ComfyError("ComfyUI 没在跑，先去启动 Start_Wan_8GB.bat")

        job.message = "正在提交…"
        out = OUTPUT_DIR / f"{source.stem}-vid-{int(time.time())}.mp4"
        job.message = "视频生成中。双 14B 模型接力，可能要半小时以上"
        path = generate_video(
            client,
            source,
            prompt,
            out,
            unet_high=cfg.local.wan_unet_high,
            unet_low=cfg.local.wan_unet_low,
            clip=cfg.local.wan_clip,
            vae=cfg.local.wan_vae,
            clip_vision=cfg.local.wan_clip_vision,
            width=cfg.local.video_width,
            height=cfg.local.video_height,
            length=length,
            fps=cfg.local.video_fps,
            steps=cfg.local.video_steps,
            cfg=cfg.local.video_cfg,
            shift=cfg.local.video_shift,
            wait_timeout=cfg.local.video_timeout,
        )
        return {
            "path": str(path),
            "url": "/file?path=" + urllib.parse.quote(str(path)),
            "name": path.name,
        }

    from .jobs import REGISTRY

    return REGISTRY.submit("video", work)


def do_ingest(params: dict[str, Any]) -> dict[str, Any]:
    source = str(params.get("dir", "")).strip()
    if not source:
        raise ValueError("填写一个目录")
    products = scan(source)
    if not products:
        raise ValueError("这个目录里没找到图片")
    manifest = build_manifest(products, source)
    return {
        "count": len(products),
        "products": [
            {"name": p.name, "images": len(p.images), "has_body": bool(p.body),
             "has_tags": bool(p.tags), "title": p.title}
            for p in products
        ],
        "manifest": manifest,
    }


def do_analyze(params: dict[str, Any]) -> dict[str, Any]:
    from ..analyze import ProductBrief, analyze, render_markdown
    from ..fetch import FetchError, fetch

    cfg = load_config()
    brief = ProductBrief(
        name=str(params.get("name") or ""),
        url=str(params.get("url") or ""),
        price=str(params.get("price") or ""),
        description=str(params.get("desc") or ""),
        extra=str(params.get("extra") or ""),
    )

    note = ""
    if brief.url:
        try:
            page = fetch(brief.url)
            brief.site = page.site
            brief.fetch_note = page.note
            brief.name = brief.name or page.title
            brief.description = brief.description or page.description
            brief.price = brief.price or page.price
            note = page.note
        except FetchError as exc:
            note = str(exc)

    if not (brief.name or brief.description or brief.extra):
        raise ValueError("至少要填商品名或描述（链接多半抓不到）")

    result = analyze(brief, cfg)
    return {"result": result, "markdown": render_markdown(result, brief), "note": note}


def do_package(params: dict[str, Any]) -> dict[str, Any]:
    from ..listing import build_all

    cfg = load_config()
    manifest = params.get("manifest") or {}
    if not (manifest.get("products") or []):
        raise ValueError("先扫描目录")

    out = Path(str(params.get("out") or (ROOT / "output" / "上架包")))
    results = build_all(manifest, out, cfg)
    return {
        "out": str(out),
        "packages": [
            {"name": r.name, "dir": r.dir, "images": r.images, "files": r.files}
            for r in results
        ],
    }


def do_publish(params: dict[str, Any]) -> dict[str, Any]:
    cfg = load_config()
    products = (params.get("manifest") or {}).get("products") or []
    if not products:
        raise ValueError("先扫描目录")
    platforms = params.get("platforms") or cfg.platforms
    kind = params.get("kind") or "note"
    sau_cmd = resolve_sau(cfg.sau_cmd, cfg.sau_cwd)

    plans = []
    for product in products:
        for platform in platforms:
            account = cfg.accounts.get(platform)
            if not account:
                plans.append({"platform": platform, "name": product.get("name"),
                              "error": "没有配置账号（[publish.accounts]）"})
                continue
            try:
                plan = build_plan(product, platform, account=account,
                                  sau_cmd=cfg.sau_cmd, kind=kind,
                                  zhihu_category=cfg.zhihu_category)
            except (ValueError, FileNotFoundError) as exc:
                plans.append({"platform": platform, "name": product.get("name"), "error": str(exc)})
                continue
            plans.append({
                "platform": platform,
                "name": plan.product_name,
                "command": plan.command,
                "warnings": plan.warnings,
            })
    return {"plans": plans, "dry_run": cfg.dry_run}


# ------------------------------------------------------------------ HTTP


class Handler(BaseHTTPRequestHandler):
    server_version = "AIDianshang/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # 安静点
        return

    # ---- 响应helper ----

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj: Any, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    # ---- GET ----

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if route in ("/", "/index.html", "/ui.html"):
                self._send(200, UI_FILE.read_bytes(), "text/html; charset=utf-8")
                return

            if route == "/api/status":
                self._json(_status())
                return

            if route == "/api/candidates":
                self._json(_candidates_payload())
                return

            if route == "/api/job":
                from .jobs import REGISTRY

                job = REGISTRY.get((query.get("id") or [""])[0])
                self._json(job.to_dict() if job else {"error": "not found"}, 200 if job else 404)
                return

            if route == "/file":
                target = _safe_path((query.get("path") or [""])[0])
                if not target:
                    self._json({"error": "文件不存在或不允许访问"}, 404)
                    return
                ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                self._send(200, target.read_bytes(), ctype)
                return

            self._json({"error": "not found"}, 404)

        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json({"error": str(exc)}, 500)

    # ---- POST ----

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path

        try:
            if route == "/api/upload":
                raw = self._read_body()
                if not raw:
                    self._json({"error": "文件为空"}, 400)
                    return
                name = urllib.parse.unquote(self.headers.get("X-Filename") or "upload.png")
                name = Path(name).name or "upload.png"
                UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                target = UPLOAD_DIR / f"{int(time.time())}-{name}"
                target.write_bytes(raw)
                self._json({
                    "path": str(target),
                    "url": "/file?path=" + urllib.parse.quote(str(target)),
                    "name": target.name,
                })
                return

            payload = json.loads(self._read_body() or b"{}")

            if route == "/api/gen":
                job = start_gen(payload)
                self._json({"job": job.to_dict()})
                return

            if route == "/api/vid":
                job = start_vid(payload)
                self._json({"job": job.to_dict()})
                return

            if route == "/api/ingest":
                self._json(do_ingest(payload))
                return

            if route == "/api/publish":
                self._json(do_publish(payload))
                return

            if route == "/api/package":
                self._json(do_package(payload))
                return

            if route == "/api/analyze":
                self._json(do_analyze(payload))
                return

            self._json({"error": "not found"}, 404)

        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json({"error": str(exc)}, 500)


def serve(port: int = 8899, open_browser: bool = False) -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    url = f"http://127.0.0.1:{port}"

    print("=" * 56)
    print(" AI 电商综合体 · 本地工作台")
    print("=" * 56)
    print(f" 打开：{url}")
    print(" Ctrl+C 退出")
    print("=" * 56)

    if open_browser:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
    finally:
        httpd.server_close()
