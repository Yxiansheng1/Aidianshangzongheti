"""OpenAI 兼容接口的最小客户端（仅标准库）。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class ModelError(RuntimeError):
    """模型调用失败。所有网络/协议错误都收敛成这一种。"""


@dataclass
class OpenAICompatible:
    base_url: str
    api_key: str
    timeout: int = 60
    text_model: str = ""

    def __post_init__(self) -> None:
        url = self.base_url.rstrip("/")
        if not url.endswith("/v1"):
            url += "/v1"
        self.base_url = url
        # HTTP 头只能是 latin-1，key 里有中文会在最底层炸出看不懂的错，提前拦住
        if self.api_key and not self.api_key.isascii():
            raise ModelError("api_key 含非 ASCII 字符，多半是占位符没替换成真实 key")

    # ---- 底层 ----

    def _request(self, path: str, payload: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data: bytes | None = None

        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            url, data=data, headers=headers, method="POST" if data else "GET"
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:400]
            raise ModelError(f"HTTP {exc.code} ← {url}\n{body}") from exc
        except urllib.error.URLError as exc:
            raise ModelError(f"连不上 {url}：{exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise ModelError(f"返回的不是 JSON：{url}") from exc

    # ---- 能力 ----

    def list_models(self) -> list[str]:
        data = self._request("/models")
        items = data.get("data", []) if isinstance(data, dict) else []
        return [str(m.get("id", "")) for m in items if isinstance(m, dict)]

    def chat(self, model: str, messages: list[dict], **kwargs: Any) -> str:
        payload: dict[str, Any] = {"model": model, "messages": messages, **kwargs}
        data = self._request("/chat/completions", payload)
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelError(f"响应结构异常：{str(data)[:300]}") from exc

    def ask(self, prompt: str, system: str = "") -> str:
        """单轮问答的快捷方式。"""
        if not self.text_model:
            raise ModelError("config.toml 里没有配置 model.text_model")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(self.text_model, messages)
