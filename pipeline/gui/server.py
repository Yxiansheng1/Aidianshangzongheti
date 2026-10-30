"""本地 Web 界面。只用标准库，不需要 pip install 任何东西。"""

from __future__ import annotations

import json
import mimetypes
import subprocess
import sys
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


# ------------------------------------------------------------------ 能力契约
#
# 这张表是本项目对外的「能力目录」。任何编排工具（n8n / Langflow / 脚本）
# 照着这张表调 HTTP 就行，不需要知道内部实现。
#
# 加一个能力 = 加一条记录 + 加一个路由，不改别的。

CAPABILITIES: list[dict[str, Any]] = [
    {
        "name": "queue.list",
        "desc": "内容队列：列出所有条目和状态统计",
        "method": "GET",
        "path": "/api/queue",
        "inputs": {},
        "outputs": {"stats": "json", "items": "json"},
        "sync": True,
        "slow": False,
        "needs_model": False,
    },
    {
        "name": "queue.step",
        "desc": "对队列条目跑「AI 改写 + AI 审核」，按结果推进状态",
        "method": "POST",
        "path": "/api/queue/step",
        "inputs": {"id": "str?", "ids": "list?"},
        "outputs": {"done": "json", "failed": "json"},
        "sync": True,
        "slow": False,
        "needs_model": True,
    },
    {
        "name": "write.draft",
        "desc": "AI 改写：主题 → 各平台口吻的标题+正文+标签",
        "method": "POST",
        "path": "/api/write",
        "inputs": {"topic": "str", "platform": "str", "product": "str?", "extra": "str?", "tone": "str?", "review": "bool?"},
        "outputs": {"title": "str", "body": "str", "tags": "list", "review": "json?"},
        "sync": True,
        "slow": False,
        "needs_model": True,
    },
    {
        "name": "review.content",
        "desc": "AI 审核：规则禁词 + 断言级核查（属实/存疑/无法证实/夸大）",
        "method": "POST",
        "path": "/api/review",
        "inputs": {"text": "str", "platform": "str", "use_ai": "bool?"},
        "outputs": {"passed": "bool", "score": "int", "issues": "json", "claims_checked": "int"},
        "sync": True,
        "slow": False,
        "needs_model": True,
    },
    {
        "name": "trends.fetch",
        "desc": "抓热点菜单（国内热搜 + AI科技 + 国际 + 军事），标注哪些能蹭",
        "method": "GET",
        "path": "/api/trends?categories=国内热搜,AI与科技&save=1",
        "inputs": {"sources": "str?", "categories": "str?", "save": "bool?"},
        "outputs": {"total": "int", "matched": "int", "items": "json", "markdown": "str"},
        "sync": True,
        "slow": True,
        "needs_model": False,
    },
    {
        "name": "orchestrate.produce",
        "desc": "交给 n8n 全自动跑：出图 → 轮询 → 出视频 → 轮询",
        "method": "POST",
        "path": "/api/orchestrate",
        "inputs": {"source": "path", "prompt": "str", "videoPrompt": "str?", "size": "int?"},
        "outputs": {"webhook": "str", "n8n": "str"},
        "sync": True,
        "slow": False,
        "needs_model": False,
    },
    {
        "name": "analyze.product",
        "desc": "商品分析 + 生图/视频提示词 + 小红书文案",
        "method": "POST",
        "path": "/api/analyze",
        "inputs": {"name": "str", "url": "str?", "price": "str?", "desc": "str?", "extra": "str?"},
        "outputs": {"result": "json", "markdown": "str", "note": "str"},
        "sync": True,
        "slow": False,
        "needs_model": True,
    },
    {
        "name": "gen.image",
        "desc": "商品原图 → 场景主图（本地 ComfyUI）",
        "method": "POST",
        "path": "/api/gen",
        "inputs": {"source": "path", "prompt": "str", "size": "int?", "steps": "int?"},
        "outputs": {"job": "json"},
        "sync": False,
        "slow": True,
        "needs_model": False,
    },
    {
        "name": "gen.video",
        "desc": "起始图 → 短视频（本地 Wan2.2）",
        "method": "POST",
        "path": "/api/vid",
        "inputs": {"source": "path", "prompt": "str", "length": "int?"},
        "outputs": {"job": "json"},
        "sync": False,
        "slow": True,
        "needs_model": False,
    },
    {
        "name": "job.status",
        "desc": "查询异步任务状态（gen.image / gen.video 用）",
        "method": "GET",
        "path": "/api/job?id=<job_id>",
        "inputs": {"id": "str"},
        "outputs": {"status": "queued|running|done|error", "result": "json", "error": "str"},
        "sync": True,
        "slow": False,
        "needs_model": False,
    },
    {
        "name": "file.get",
        "desc": "取产物文件（图片/视频），只允许读仓库目录内",
        "method": "GET",
        "path": "/file?path=<abs_path>",
        "inputs": {"path": "path"},
        "outputs": {"bytes": "binary"},
        "sync": True,
        "slow": False,
        "needs_model": False,
    },
    {
        "name": "manifest.scan",
        "desc": "扫描素材目录，生成上架/发布清单",
        "method": "POST",
        "path": "/api/ingest",
        "inputs": {"dir": "dir"},
        "outputs": {"count": "int", "products": "json", "manifest": "json"},
        "sync": True,
        "slow": False,
        "needs_model": False,
    },
    {
        "name": "package.listing",
        "desc": "生成上架资料包（主图重命名 + 标题/卖点/详情/属性表）",
        "method": "POST",
        "path": "/api/package",
        "inputs": {"manifest": "json"},
        "outputs": {"out": "dir", "packages": "json"},
        "sync": True,
        "slow": False,
        "needs_model": False,
    },
    {
        "name": "publish.plan",
        "desc": "生成各平台发布命令（只生成不执行）",
        "method": "POST",
        "path": "/api/publish",
        "inputs": {"manifest": "json", "platforms": "list", "kind": "note|video"},
        "outputs": {"plans": "json", "dry_run": "bool"},
        "sync": True,
        "slow": False,
        "needs_model": False,
    },
]



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


def do_orchestrate(params: dict[str, Any]) -> dict[str, Any]:
    """把任务交给 n8n：POST 到它的 webhook，立刻返回，真正的活由 n8n 异步跑。"""
    import urllib.error
    import urllib.request

    cfg = load_config()
    url = (cfg.orchestrate_webhook or "").strip()
    if not url:
        raise ValueError("config.toml 里没有配置 [orchestrate] webhook_url")

    raw_source = str(params.get("source") or "").strip()
    if not raw_source:
        raise ValueError("先选一张商品原图")
    source = Path(raw_source)
    if not source.is_file():
        raise ValueError(f"图片不存在：{source}")

    payload = {
        # n8n 在 Windows 上对反斜杠转义容易出问题，统一用正斜杠
        "source": str(source.resolve()).replace("\\", "/"),
        "imagePrompt": str(params.get("prompt") or "").strip(),
        "videoPrompt": str(params.get("videoPrompt") or "").strip(),
        "size": int(params.get("size") or 1024),
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if exc.code == 404:
            raise RuntimeError(
                "n8n 说这个 webhook 没注册。通常是工作流没启用，"
                "或者改过之后没重新启用——去 n8n 里把工作流关掉再打开一次。"
            ) from exc
        raise RuntimeError(f"n8n 返回 {exc.code}：{detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"连不上 n8n（{url}）：{exc.reason}。先双击 启动n8n.bat"
        ) from exc

    return {"webhook": url, "n8n": body.strip(), "payload": payload}


def do_queue_source(params: dict[str, Any]) -> dict[str, Any]:
    """设商品原图（AI 出图的输入）。"""
    from .. import queue

    path = str(params.get("path") or "").strip().strip('"')
    if not path:
        raise ValueError("给一个图片路径")
    target = Path(path)
    if not target.is_file():
        raise ValueError(f"文件不存在：{path}")

    item = queue.update(str(params.get("id") or ""), source=str(target))
    return {"item": item.as_dict()}


def do_queue_gen(params: dict[str, Any]) -> dict[str, Any]:
    """对队列条目跑 AI 出图。慢，走后台任务。"""
    from .. import queue
    from ..model.comfyui import ComfyClient, ComfyError, generate
    from .jobs import REGISTRY

    cfg = load_config()
    item = queue.get(str(params.get("id") or ""))
    if item is None:
        raise KeyError(f"没有这条：{params.get('id')}")
    if not item.source or not Path(item.source).is_file():
        raise ValueError("先上传商品原图（AI 出图需要参考图）")

    prompt = str(params.get("prompt") or "").strip()
    if not prompt:
        prompt = (
            f"把商品放在干净的生活场景里，自然侧光，浅景深，背景轻微虚化，"
            f"构图留白，商品保持原样不变形。主题参考：{item.title or item.topic}"
        )

    size = int(params.get("size") or cfg.local.width or 1024)
    item_id = item.id

    def work(job):
        client = ComfyClient(cfg.local.comfyui_url)
        if not client.is_up():
            raise ComfyError("ComfyUI 没在跑，先启动 启动工作台.bat")

        job.message = "AI 出图中，8GB 显存约 7 分钟"
        out = OUTPUT_DIR / f"queue-{item_id}-{int(time.time())}.png"
        path = generate(
            client, item.source, prompt, out,
            unet=cfg.local.unet, clip=cfg.local.clip, vae=cfg.local.vae,
            width=size, height=size,
            steps=cfg.local.steps, cfg=cfg.local.cfg, shift=cfg.local.shift,
            wait_timeout=cfg.local.wait_timeout,
        )
        queue.update(item_id, images=[str(path)])
        return {"path": str(path), "url": "/file?path=" + urllib.parse.quote(str(path))}

    return {"job": REGISTRY.submit("queue-gen", work).to_dict()}


def do_queue_pub(params: dict[str, Any]) -> dict[str, Any]:
    """直接执行发布（真的发出去）。"""
    from .. import queue
    from ..publish.sau import build_plan, resolve_sau

    cfg = load_config()
    item = queue.get(str(params.get("id") or ""))
    if item is None:
        raise KeyError(f"没有这条：{params.get('id')}")
    if not item.images:
        raise ValueError("还没有图，先跑 AI 出图")
    if not item.body.strip():
        raise ValueError("还没有正文")

    account = cfg.accounts.get(item.platform, "main")
    product = {
        "name": item.title or item.topic,
        "title": item.title,
        "body": item.body,
        "tags": item.tags,
        "images": item.images,
    }
    plan = build_plan(
        product, item.platform, account=account,
        sau_cmd=resolve_sau(cfg.sau_cmd, cfg.sau_cwd),
        kind="note", headed=True,
    )

    try:
        result = subprocess.run(
            plan.argv,
            cwd=cfg.sau_cwd or None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "command": plan.command,
                "output": "超过 300 秒没结束。可能卡住了，去 logs 看。"}

    output = (result.stdout or "") + (result.stderr or "")
    ok = result.returncode == 0 and "发布成功" in output

    if ok:
        queue.update(item.id, status="published")

    return {
        "ok": ok,
        "returncode": result.returncode,
        "command": plan.command,
        "output": output[-1500:],
    }


def do_queue_image(params: dict[str, Any]) -> dict[str, Any]:
    from .. import queue

    path = str(params.get("path") or "").strip().strip('"')
    if not path:
        raise ValueError("给一个图片路径")
    target = Path(path)
    if not target.is_file():
        raise ValueError(f"文件不存在：{path}")

    item = queue.update(str(params.get("id") or ""), images=[str(target)], video="")
    return {"item": item.as_dict()}


def do_queue_cmd(params: dict[str, Any]) -> dict[str, Any]:
    """给队列条目生成 sau 发布命令（只生成，不执行）。"""
    from .. import queue
    from ..publish.sau import build_plan, resolve_sau

    cfg = load_config()
    item = queue.get(str(params.get("id") or ""))
    if item is None:
        raise KeyError(f"没有这条：{params.get('id')}")
    if not item.images:
        raise ValueError("这条还没配图，先点「配图」")
    if not item.body.strip():
        raise ValueError("这条还没写正文")

    account = cfg.accounts.get(item.platform, "main")
    product = {
        "name": item.title or item.topic,
        "title": item.title,
        "body": item.body,
        "tags": item.tags,
        "images": item.images,
    }
    plan = build_plan(
        product,
        item.platform,
        account=account,
        sau_cmd=resolve_sau(cfg.sau_cmd, cfg.sau_cwd),
        kind="note",
        headed=True,
    )
    return {"command": plan.command, "warnings": plan.warnings, "platform": item.platform}


def do_content_video(params: dict[str, Any]) -> dict[str, Any]:
    """把一次生成的配图拼成竖版轮播视频。秒级完成。"""
    from ..content.video import info, slideshow

    images = params.get("images") or []
    if not images:
        raise ValueError("没有图片可拼")

    out_dir = Path(str(params.get("dir") or (OUTPUT_DIR / "内容" / "video")))
    out = out_dir / f"video-{int(time.time())}.mp4"

    path = slideshow(
        images, out,
        seconds_per_image=float(params.get("seconds") or 3),
    )
    return {
        "path": str(path),
        "url": "/file?path=" + urllib.parse.quote(str(path)),
        "info": info(path),
    }


def do_content_pub(params: dict[str, Any]) -> dict[str, Any]:
    """生成发布命令；execute=true 时直接发。"""
    from ..content import publish as pub

    cfg = load_config()
    platform = str(params.get("platform") or "")
    if not platform:
        raise ValueError("没指定平台")

    payload = {
        "title": str(params.get("title") or ""),
        "body": str(params.get("body") or ""),
        "tags": list(params.get("tags") or []),
        "images": list(params.get("images") or []),
        "video": str(params.get("video") or ""),
        "account": str(params.get("account") or ""),
    }

    flag = params.get("execute")
    if flag is True or str(flag or "").lower() in ("1", "true", "yes"):
        result = pub.execute(platform, cfg, **payload)
        return {
            "executed": True,
            "ok": result.ok,
            "command": result.command,
            "output": result.output,
        }

    return {"executed": False, **pub.build(platform, cfg=cfg, **payload)}


def _sau_python(cfg: Any) -> str:
    """sau 装在哪个 venv，就用那个 venv 的 python（patchright 在里面）。"""
    from ..publish.sau import resolve_sau

    exe = Path(resolve_sau(cfg.sau_cmd, cfg.sau_cwd))
    candidate = exe.with_name("python.exe")
    return str(candidate if candidate.is_file() else Path(sys.executable))


def do_content_headline(params: dict[str, Any]) -> dict[str, Any]:
    """头条号：工具填稿，人点发布。开一个新控制台跑，看得见它干了什么。

    三种 action：
        login  扫码登录某个账号
        fill   把稿子填进某个账号的编辑器
        both   一稿两版：A 版给账号1、B 版给账号2（避免两号发同一篇被判重复）
    """
    from ..content import headline

    cfg = load_config()
    action = str(params.get("action") or "fill")
    account = "".join(ch for ch in str(params.get("account") or "main") if ch.isalnum() or ch in "-_") or "main"
    label = str(params.get("label") or account)
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

    def spawn(args_: list[str]) -> None:
        subprocess.Popen(args_, cwd=str(ROOT), creationflags=flags)

    def write_draft(acc: str, t: str, b: str) -> Path:
        headline.STATE_DIR.mkdir(parents=True, exist_ok=True)
        path = headline.STATE_DIR / f"toutiao-draft-{acc}.json"
        path.write_text(json.dumps({
            "title": t,
            "body": b,
            "images": list(params.get("images") or []),
            "url": str(params.get("url") or ""),
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    py = _sau_python(cfg)

    if action == "login":
        spawn([py, "-m", "pipeline.content.headline", "login", "--account", account])
        return {
            "started": True, "action": action, "account": account,
            "message": f"已打开浏览器（{label}），扫码登录这个头条号；登录后窗口自动关闭，下次填稿不用再扫。",
        }

    title = str(params.get("title") or "").strip()
    body = str(params.get("body") or "").strip()
    if not title or not body:
        raise ValueError("没有标题或正文，先生成一篇")

    if action == "both":
        from ..content.variants import make_variant

        platform = str(params.get("platform") or "头条")
        second = make_variant(title, body, cfg, platform=platform)

        first_path = write_draft("main", title, body)
        second_path = write_draft("second", second["title"], second["body"])

        spawn([py, "-m", "pipeline.content.headline", "fill",
               "--draft", str(first_path), "--account", "main"])
        spawn([py, "-m", "pipeline.content.headline", "fill",
               "--draft", str(second_path), "--account", "second"])

        return {
            "started": True, "action": action,
            "first_title": title,
            "second_title": second["title"],
            "message": (f"两个窗口都开了。账号1 放第一版，账号2 放第二版"
                        f"（「{second['title'][:22]}」）。各自检查后自己点发布。"),
        }

    draft_path = write_draft(account, title, body)
    spawn([py, "-m", "pipeline.content.headline", "fill",
           "--draft", str(draft_path), "--account", account])
    return {
        "started": True, "action": action, "account": account,
        "message": f"已在浏览器里填稿（{label}）。填完它会停下等你——检查、选封面、点发布，最后按回车关窗口。",
    }


def _persona_dirs() -> list[Path]:
    """候选人设目录：老的一批（output/人设）+ 新闻方向那批（output/人设-新闻）。"""
    out: list[Path] = []
    for base in (ROOT / "output" / "人设", ROOT / "output" / "人设-新闻"):
        if not base.is_dir():
            continue
        out.extend(sorted(p for p in base.iterdir() if p.is_dir() and (p / "人设卡.md").is_file()))
    return out


def do_content_personas() -> dict[str, Any]:
    """有哪些候选人设、现在用的是哪个。"""
    from ..content.rewrite import PERSONA_FILE

    items = []
    for folder in _persona_dirs():
        avatars = sorted(folder.glob("avatar-*.png"))
        items.append({
            "key": folder.name,
            "name": folder.name.split("-", 1)[-1],
            "avatars": ["/file?path=" + urllib.parse.quote(str(a)) for a in avatars],
        })

    current = ""
    if PERSONA_FILE.is_file():
        first = PERSONA_FILE.read_text(encoding="utf-8").strip().splitlines()
        current = first[0].lstrip("# ").strip() if first else ""
    return {"personas": items, "current": current}


def do_content_persona_set(params: dict[str, Any]) -> dict[str, Any]:
    """把某份人设卡设为当前人设；key 传空 = 清掉，回到没人设。"""
    from ..content.rewrite import PERSONA_FILE

    key = str(params.get("key") or "").strip()
    if not key:
        if PERSONA_FILE.is_file():
            PERSONA_FILE.unlink()
        return {"current": ""}

    src = next((folder / "人设卡.md" for folder in _persona_dirs() if folder.name == key), None)
    if src is None:
        raise ValueError(f"没有这份人设卡：{key}")

    PERSONA_FILE.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return {"current": key.split("-", 1)[-1], "key": key}


def do_content_accounts() -> dict[str, Any]:
    """所有平台的账号清单与登录态。界面据此渲染下拉，避免发错号。"""
    from ..content.accounts import login_state

    return login_state()


def do_content_meta() -> dict[str, Any]:
    from ..content.rewrite import list_modes, list_skills
    from ..content import publish as pub

    skills = list_skills()
    persona = ""
    from ..content.rewrite import PERSONA_FILE
    if PERSONA_FILE.is_file():
        head = PERSONA_FILE.read_text(encoding="utf-8").strip().splitlines()
        persona = head[0].lstrip("# ").strip() if head else ""

    return {
        "skills": skills,
        "default": "小红书",
        "persona": persona,
        "modes": list_modes(),
        # 每个平台能发什么形态，界面据此决定显示哪些按钮
        "publish": {name: pub.kinds(name) for name in skills},
        "no_publish": {k: v for k, v in pub.NO_PUBLISH_REASON.items() if k in skills},
    }


def start_content(params: dict[str, Any]) -> dict[str, Any]:
    """内容流水线：抓文章 → 改写 → 审核 → 配图。慢，走后台任务。"""
    from ..content import pipeline as content_pipeline
    from .jobs import REGISTRY

    cfg = load_config()

    url = str(params.get("url") or "").strip()
    raw_text = str(params.get("text") or "").strip()
    title = str(params.get("title") or "").strip()
    platform = str(params.get("platform") or "小红书")
    mode = str(params.get("mode") or "")
    images = int(params.get("images") or 2)

    if not url and not raw_text and not title:
        raise ValueError("给一个文章链接，或者直接粘贴正文，或者至少给一个主题")

    article = None
    if raw_text:
        article = {
            "title": title or "未命名",
            "text": raw_text,
        }
    elif not url and title:
        # 只有主题、没有链接和正文：照样能写，但改写时会把「哪句没依据」标出来
        article = {"title": title, "text": ""}

    def work(job):
        job.message = "抓原文中…" if (url and not raw_text) else "写作中…"
        result = content_pipeline.run(
            url, cfg, platform=platform, mode=mode, images=images,
            draw=bool(params.get("draw", True)), article=article,
        )

        if not result.get("ok"):
            step = result.get("steps", {})
            reason = ""
            for name in ("fetch", "rewrite"):
                if step.get(name) and not step[name].get("ok"):
                    reason = step[name].get("reason", "")
                    break
            raise RuntimeError(reason or "流水线失败")

        draft = result["draft"]
        visual = result.get("steps", {}).get("visual", {})
        files = visual.get("files") or []
        fetch_step = result.get("steps", {}).get("fetch", {}) or {}

        return {
            "draft": draft,
            "images": [
                {"path": f, "url": "/file?path=" + urllib.parse.quote(f)}
                for f in files
            ],
            "source_images": [
                {"path": p, "url": "/file?path=" + urllib.parse.quote(p)}
                for p in (fetch_step.get("images") or [])
            ],
            "source_image_note": fetch_step.get("image_note", ""),
            "review": result.get("steps", {}).get("review", {}),
            "chars": fetch_step.get("chars", 0),
            "dir": result.get("dir", ""),
        }

    return {"job": REGISTRY.submit("content", work).to_dict()}


def do_content_skill(params: dict[str, Any]) -> dict[str, Any]:
    """读 / 写 skill 文件，让用户可以在界面里改。"""
    from ..content.rewrite import SKILL_DIR, list_skills, load_skill

    name = str(params.get("platform") or "小红书")
    action = str(params.get("action") or "read")

    if action == "read":
        return {"platform": name, "content": load_skill(name), "skills": list_skills()}

    if action == "write":
        content = str(params.get("content") or "")
        if len(content) < 200:
            raise ValueError("内容太短了，确认是要覆盖整份 skill 吗？")
        target = SKILL_DIR / f"{name}.md"
        target.write_text(content, encoding="utf-8")
        return {"platform": name, "saved": True, "chars": len(content)}

    raise ValueError(f"未知操作：{action}")


def do_queue_list() -> dict[str, Any]:
    from .. import queue

    items = queue.all_items()
    return {
        "stats": queue.stats(),
        "statuses": queue.STATUS_FLOW,
        "items": [i.as_dict() for i in items],
    }


def do_queue_add(params: dict[str, Any]) -> dict[str, Any]:
    from .. import queue

    item = queue.add(
        str(params.get("topic") or ""),
        str(params.get("platform") or "xiaohongshu"),
        product=str(params.get("product") or ""),
        extra=str(params.get("extra") or ""),
        tone=str(params.get("tone") or ""),
        source_url=str(params.get("source_url") or ""),
        source_text=str(params.get("source_text") or ""),
    )
    return {"item": item.as_dict()}


def do_queue_refetch(params: dict[str, Any]) -> dict[str, Any]:
    """按 source_url 抓原文，存进 source_text。"""
    from .. import queue
    from ..article import ArticleError, fetch

    cfg = load_config()
    item = queue.get(str(params.get("id") or ""))
    if item is None:
        raise KeyError(f"没有这条：{params.get('id')}")
    if not item.source_url:
        raise ValueError("这条没有原文链接，先补一个 source_url")

    article = fetch(item.source_url, proxy=cfg.trends.proxy or None)
    if not article.ok:
        raise ArticleError(article.note or "没抓到正文")

    updated = queue.update(item.id, source_text=article.text)
    return {
        "item": updated.as_dict(),
        "chars": article.chars,
        "title": article.title,
    }


def do_queue_step(params: dict[str, Any]) -> dict[str, Any]:
    """对一条或多条跑「写 + 审」。单条失败不影响其他。"""
    from .. import queue

    cfg = load_config()
    ids = params.get("ids")
    if not ids:
        one = params.get("id")
        ids = [one] if one else [i.id for i in queue.all_items("pending")]

    done, failed = [], []
    for item_id in ids:
        try:
            item = queue.step(str(item_id), cfg)
            done.append(item.as_dict())
        except Exception as exc:  # noqa: BLE001
            failed.append({"id": item_id, "error": str(exc)})

    return {"done": done, "failed": failed, "stats": queue.stats()}


def do_queue_set(params: dict[str, Any]) -> dict[str, Any]:
    from .. import queue

    item_id = str(params.get("id") or "")
    status = str(params.get("status") or "")
    if status not in queue.STATUS_FLOW:
        raise ValueError(f"未知状态：{status}")
    item = queue.update(item_id, status=status)
    return {"item": item.as_dict(), "stats": queue.stats()}


def do_queue_remove(params: dict[str, Any]) -> dict[str, Any]:
    from .. import queue

    ok = queue.remove(str(params.get("id") or ""))
    return {"removed": ok, "stats": queue.stats()}


def do_write(params: dict[str, Any]) -> dict[str, Any]:
    from ..writer import render_markdown, write

    cfg = load_config()
    result = write(
        str(params.get("topic") or ""),
        str(params.get("platform") or "xiaohongshu"),
        cfg,
        product=str(params.get("product") or ""),
        extra=str(params.get("extra") or ""),
        tone=str(params.get("tone") or ""),
    )
    payload = dict(result)
    payload["markdown"] = render_markdown(result)

    if str(params.get("review") or "").lower() in ("1", "true", "yes") or params.get("review") is True:
        from ..review import review

        combined = f"{result['title']}\n\n{result['body']}"
        outcome = review(combined, result["platform"], cfg)
        payload["review"] = outcome.as_dict()

    return payload


def do_review(params: dict[str, Any]) -> dict[str, Any]:
    from ..review import render_markdown, review

    cfg = load_config()
    text = str(params.get("text") or "")
    if not text.strip():
        raise ValueError("没有内容可审")

    outcome = review(
        text,
        str(params.get("platform") or "xiaohongshu"),
        cfg,
        use_ai=str(params.get("use_ai", "1")) not in ("0", "false", "no"),
    )
    payload = outcome.as_dict()
    payload["markdown"] = render_markdown(outcome)
    return payload


def do_trends_meta() -> dict[str, Any]:
    from ..trends import CATEGORIES, SOURCES

    grouped: dict[str, list[dict[str, str]]] = {}
    for source in SOURCES:
        grouped.setdefault(source.category, []).append({"key": source.key, "name": source.name})

    return {
        "categories": [c for c in CATEGORIES if c in grouped],
        "sources": grouped,
        "total_sources": len(SOURCES),
    }


def do_trends(params: dict[str, Any]) -> dict[str, Any]:
    from ..trends import collect, render_markdown, save

    cfg = load_config()
    raw_sources = params.get("sources")
    raw_cats = params.get("categories")
    sources = [s.strip() for s in raw_sources.split(",")] if raw_sources else None
    categories = [c.strip() for c in raw_cats.split(",")] if raw_cats else None

    result = collect(
        sources=sources,
        keywords=cfg.trends.keywords or None,
        proxy=cfg.trends.proxy or None,
        categories=categories,
    )
    payload = result.as_dict()
    payload["markdown"] = render_markdown(result)

    if str(params.get("save") or "").lower() in ("1", "true", "yes") or params.get("save") is True:
        path = save(result, ROOT / "output" / "热点")
        payload["saved"] = str(path)

    return payload


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


def _fix_mojibake(text: str) -> str:
    """修复「原始 UTF-8 字节被当成 latin-1 解码」的经典乱码。

    http.server 按 latin-1 解析请求行，所以直接拼接中文查询参数会变成乱码。
    这里尝试还原；还原不了就原样返回。
    """
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


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

            if route == "/api/tools":
                port = self.server.server_address[1]
                self._json({
                    "base_url": f"http://127.0.0.1:{port}",
                    "tools": CAPABILITIES,
                    "note": "异步能力先提交拿 job.id，再轮询 /api/job?id=... 直到 status=done",
                })
                return

            if route == "/api/candidates":
                self._json(_candidates_payload())
                return

            if route == "/api/queue":
                self._json(do_queue_list())
                return

            if route == "/api/trends/categories":
                self._json(do_trends_meta())
                return

            if route == "/api/content/meta":
                self._json(do_content_meta())
                return

            if route == "/api/content/personas":
                self._json(do_content_personas())
                return

            if route == "/api/content/accounts":
                self._json(do_content_accounts())
                return

            if route == "/api/trends":
                params = {k: _fix_mojibake(v[0]) for k, v in query.items() if v}
                self._json(do_trends(params))
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

            if route == "/api/orchestrate":
                self._json(do_orchestrate(payload))
                return

            if route == "/api/write":
                self._json(do_write(payload))
                return

            if route == "/api/review":
                self._json(do_review(payload))
                return

            if route == "/api/queue/add":
                self._json(do_queue_add(payload))
                return

            if route == "/api/queue/step":
                self._json(do_queue_step(payload))
                return

            if route == "/api/queue/set":
                self._json(do_queue_set(payload))
                return

            if route == "/api/queue/remove":
                self._json(do_queue_remove(payload))
                return

            if route == "/api/queue/image":
                self._json(do_queue_image(payload))
                return

            if route == "/api/queue/source":
                self._json(do_queue_source(payload))
                return

            if route == "/api/queue/gen":
                self._json(do_queue_gen(payload))
                return

            if route == "/api/queue/pub":
                self._json(do_queue_pub(payload))
                return

            if route == "/api/queue/cmd":
                self._json(do_queue_cmd(payload))
                return

            if route == "/api/queue/refetch":
                self._json(do_queue_refetch(payload))
                return

            if route == "/api/content/run":
                self._json(start_content(payload))
                return

            if route == "/api/content/skill":
                self._json(do_content_skill(payload))
                return

            if route == "/api/content/persona":
                self._json(do_content_persona_set(payload))
                return

            if route == "/api/content/video":
                self._json(do_content_video(payload))
                return

            if route == "/api/content/pub":
                self._json(do_content_pub(payload))
                return

            if route == "/api/content/headline":
                self._json(do_content_headline(payload))
                return

            self._json({"error": "not found"}, 404)

        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json({"error": str(exc)}, 500)


def serve(port: int = 8899, open_browser: bool = False) -> None:
    # 控制台不是 UTF-8 时（例如从别的终端拉起），print 中文会直接抛
    # UnicodeEncodeError 把服务带崩。这里先兜住。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

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
