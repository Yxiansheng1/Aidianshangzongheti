"""ComfyUI 适配层。

把本地 ComfyUI 当成又一个「模型供应商」。上层只认 generate()，
后面想在本地和云端之间切换，只改 config.toml。

当前支持：Qwen-Image-Edit（图生图 / 参考图编辑），
就是做商品图最需要的那种——保住商品原样，只换背景和场景。
"""

from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ComfyError(RuntimeError):
    """ComfyUI 调用失败。"""


@dataclass
class ComfyClient:
    base_url: str = "http://127.0.0.1:8188"
    timeout: int = 30

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")

    # ---------- 基础请求 ----------

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ComfyError(f"连不上 ComfyUI（{url}）：{exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise ComfyError(f"ComfyUI 返回的不是 JSON：{path}") from exc

    def _post_json(self, path: str, payload: dict) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:800]
            raise ComfyError(f"HTTP {exc.code} ← {path}\n{body}") from exc
        except urllib.error.URLError as exc:
            raise ComfyError(f"连不上 ComfyUI（{url}）：{exc.reason}") from exc

    # ---------- 能力 ----------

    def is_up(self) -> bool:
        try:
            self._get("/system_stats")
            return True
        except ComfyError:
            return False

    def stats(self) -> dict:
        return self._get("/system_stats")

    def node_options(self, node: str, field: str) -> list[str]:
        """查某个加载节点能看到哪些模型文件，用来验证配置写对了没有。"""
        info = self._get(f"/object_info/{node}")
        try:
            values = info[node]["input"]["required"][field][0]
        except (KeyError, IndexError, TypeError):
            return []
        return list(values) if isinstance(values, list) else []


    def upload_image(self, path: Path | str) -> str:
        """上传一张图到 ComfyUI 的 input 目录，返回它内部的文件名。"""
        path = Path(path)
        if not path.is_file():
            raise ComfyError(f"找不到图片：{path}")

        boundary = f"----comfy{uuid.uuid4().hex}"
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = b"".join([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'.encode(),
            f"Content-Type: {mime}\r\n\r\n".encode(),
            path.read_bytes(),
            f"\r\n--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n',
            f"--{boundary}--\r\n".encode(),
        ])

        req = urllib.request.Request(
            f"{self.base_url}/upload/image",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                info = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ComfyError(f"上传失败：{exc}") from exc

        name = info.get("name") or path.name
        subfolder = info.get("subfolder") or ""
        return f"{subfolder}/{name}" if subfolder else name

    def queue(self, workflow: dict) -> str:
        """提交工作流，返回 prompt_id。"""
        result = self._post_json(
            "/prompt", {"prompt": workflow, "client_id": uuid.uuid4().hex}
        )
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise ComfyError(f"提交被拒绝：{json.dumps(result, ensure_ascii=False)[:600]}")
        return str(prompt_id)

    def wait(self, prompt_id: str, timeout: int = 900, interval: float = 2.0) -> dict:
        """等任务跑完，返回 history 条目。超时抛异常。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            history = self._get(f"/history/{prompt_id}")
            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    messages = status.get("messages", [])
                    raise ComfyError(f"执行出错：{json.dumps(messages, ensure_ascii=False)[:600]}")
                return entry
            time.sleep(interval)
        raise ComfyError(f"等超时（{timeout} 秒），任务可能还在跑，去 {self.base_url} 看看队列")

    def download(self, image_info: dict) -> bytes:
        query = urllib.parse.urlencode({
            "filename": image_info.get("filename", ""),
            "subfolder": image_info.get("subfolder", ""),
            "type": image_info.get("type", "output"),
        })
        try:
            with urllib.request.urlopen(f"{self.base_url}/view?{query}", timeout=120) as resp:
                return resp.read()
        except urllib.error.URLError as exc:
            raise ComfyError(f"下载结果失败：{exc}") from exc

    @staticmethod
    def output_images(entry: dict) -> list[dict]:
        images: list[dict] = []
        for node_output in entry.get("outputs", {}).values():
            images.extend(node_output.get("images", []) or [])
        return images

    @staticmethod
    def output_files(entry: dict) -> list[dict]:
        """把 outputs 里所有带 filename 的条目都捞出来。

        SaveImage 放在 images 下，SaveVideo/SaveWEBM 不一定，
        所以不猜键名，直接按形状找。
        """
        found: list[dict] = []
        for node_output in entry.get("outputs", {}).values():
            for value in node_output.values():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and item.get("filename"):
                            found.append(item)
        return found


# ---------------------------------------------------------------- 工作流

def build_qwen_edit(
    image_name: str,
    prompt: str,
    *,
    unet: str,
    clip: str,
    vae: str,
    negative: str = "",
    width: int = 1024,
    height: int = 1024,
    steps: int = 20,
    cfg: float = 2.5,
    shift: float = 3.1,
    seed: int = 0,
    filename_prefix: str = "ecom",
) -> dict:
    """Qwen-Image-Edit 的图生图工作流。

    参数以本项目实测的节点签名为准（UnetLoaderGGUF / CLIPLoader type=qwen_image /
    TextEncodeQwenImageEditPlus）。改模型只需要改 unet / clip / vae 三个字符串。
    """
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": unet}},
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": clip, "type": "qwen_image", "device": "default"},
        },
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "5": {
            "class_type": "ModelSamplingAuraFlow",
            "inputs": {"model": ["1", 0], "shift": shift},
        },
        "6": {
            "class_type": "TextEncodeQwenImageEditPlus",
            "inputs": {
                "clip": ["2", 0],
                "prompt": prompt,
                "vae": ["3", 0],
                "image1": ["4", 0],
            },
        },
        "7": {
            "class_type": "TextEncodeQwenImageEditPlus",
            "inputs": {
                "clip": ["2", 0],
                "prompt": negative,
                "vae": ["3", 0],
                "image1": ["4", 0],
            },
        },
        "8": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["5", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["8", 0],
                "denoise": 1.0,
            },
        },
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
        "11": {
            "class_type": "SaveImage",
            "inputs": {"images": ["10", 0], "filename_prefix": filename_prefix},
        },
    }


def generate(
    client: ComfyClient,
    image: Path | str,
    prompt: str,
    out_path: Path | str,
    **kwargs: Any,
) -> Path:
    """上传图 → 生成 → 落盘。返回输出文件路径。"""
    wait_timeout = int(kwargs.pop("wait_timeout", 900))

    uploaded = client.upload_image(image)
    workflow = build_qwen_edit(uploaded, prompt, **kwargs)
    prompt_id = client.queue(workflow)

    print(f"已提交任务 {prompt_id[:8]}…，等待生成（8GB 显存首次加载模型会比较慢）")
    entry = client.wait(prompt_id, timeout=wait_timeout)

    images = client.output_images(entry)
    if not images:
        raise ComfyError("任务完成但没有产出图片")

    data = client.download(images[0])
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out


# ---------------------------------------------------------------- 视频（Wan2.2 I2V）

# Wan 官方推荐的负向提示词，直接沿用
WAN_NEGATIVE = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，"
    "最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，"
    "画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，"
    "杂乱的背景，三条腿，背景人很多，倒着走"
)


def build_wan_i2v(
    image_name: str,
    prompt: str,
    *,
    unet_high: str,
    unet_low: str,
    clip: str,
    vae: str,
    clip_vision: str,
    negative: str = WAN_NEGATIVE,
    width: int = 480,
    height: int = 832,
    length: int = 33,
    fps: int = 16,
    steps: int = 20,
    cfg: float = 3.5,
    shift: float = 8.0,
    seed: int = 0,
    filename_prefix: str = "ecom-video",
) -> dict:
    """Wan2.2 图生视频工作流。

    和普通模型的根本区别：它拆成 HighNoise / LowNoise 两个 14B 模型，
    分两段采样接力。第一段只跑到一半步数，把带噪声的 latent 交给第二段。
    中间漏掉 return_with_leftover_noise=enable 就会出纯噪点。

    length 必须是 4n+1（33 / 49 / 65 / 81），这是 Wan 的帧数约束。
    """
    half = max(1, steps // 2)

    return {
        # 两个 14B 模型
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": unet_high}},
        "2": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": unet_low}},
        # 公共资产
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": clip, "type": "wan", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "5": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": clip_vision}},
        # 输入图
        "6": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "7": {"class_type": "ImageScale", "inputs": {
            "image": ["6", 0], "upscale_method": "lanczos",
            "width": width, "height": height, "crop": "center",
        }},
        "8": {"class_type": "CLIPVisionEncode", "inputs": {
            "clip_vision": ["5", 0], "image": ["7", 0], "crop": "none",
        }},
        # 文本条件
        "9": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": prompt}},
        "10": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": negative}},
        # 采样偏移
        "11": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": shift}},
        "12": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["2", 0], "shift": shift}},
        # 拼装 latent（同时输出改写后的正负条件）
        "13": {"class_type": "WanImageToVideo", "inputs": {
            "positive": ["9", 0], "negative": ["10", 0], "vae": ["4", 0],
            "width": width, "height": height, "length": length, "batch_size": 1,
            "clip_vision_output": ["8", 0], "start_image": ["7", 0],
        }},
        # 第一段：高噪，跑前半程，留下噪声
        "14": {"class_type": "KSamplerAdvanced", "inputs": {
            "model": ["11", 0], "add_noise": "enable", "noise_seed": seed,
            "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "simple",
            "positive": ["13", 0], "negative": ["13", 1], "latent_image": ["13", 2],
            "start_at_step": 0, "end_at_step": half, "return_with_leftover_noise": "enable",
        }},
        # 第二段：低噪，接后半程，不再加噪
        "15": {"class_type": "KSamplerAdvanced", "inputs": {
            "model": ["12", 0], "add_noise": "disable", "noise_seed": seed,
            "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "simple",
            "positive": ["13", 0], "negative": ["13", 1], "latent_image": ["14", 0],
            "start_at_step": half, "end_at_step": 10000, "return_with_leftover_noise": "disable",
        }},
        "16": {"class_type": "VAEDecode", "inputs": {"samples": ["15", 0], "vae": ["4", 0]}},
        "17": {"class_type": "CreateVideo", "inputs": {"images": ["16", 0], "fps": float(fps)}},
        "18": {"class_type": "SaveVideo", "inputs": {
            "video": ["17", 0], "filename_prefix": filename_prefix,
            "format": "mp4", "codec": "h264",
        }},
    }


def generate_video(
    client: ComfyClient,
    image: Path | str,
    prompt: str,
    out_path: Path | str,
    **kwargs: Any,
) -> Path:
    """图生视频。8GB 显存上很慢，做好等半小时的准备。"""
    wait_timeout = int(kwargs.pop("wait_timeout", 2400))

    uploaded = client.upload_image(image)
    workflow = build_wan_i2v(uploaded, prompt, **kwargs)
    prompt_id = client.queue(workflow)

    print(f"已提交视频任务 {prompt_id[:8]}…")
    print("Wan2.2 是双模型接力（HighNoise → LowNoise），8GB 显存下会非常慢，先去做别的")
    entry = client.wait(prompt_id, timeout=wait_timeout)

    files = client.output_files(entry)
    if not files:
        raise ComfyError("任务完成但没有产出视频")

    data = client.download(files[0])
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out

