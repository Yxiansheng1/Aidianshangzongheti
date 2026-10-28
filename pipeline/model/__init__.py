"""模型接口抽象层。

所有供应商（DeepSeek / 豆包 / 通义 / OpenAI / one-api 网关）都走同一个
OpenAI 兼容协议，所以这里只需要一个客户端。

换供应商 = 改 config.toml 里的 base_url / api_key / model 名。
上层代码永远不需要知道后面是哪家。
"""

from .client import ModelError, OpenAICompatible

__all__ = ["OpenAICompatible", "ModelError"]
