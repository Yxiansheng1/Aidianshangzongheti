"""L3：本地 API 薄壳。

只暴露两个路由，业务逻辑一律不在这里：
    GET /api/health  进程活着没有
    GET /api/tools   把 L2 的工具注册表原样透出

启动：python -m pipeline.api
"""

from .app import API_VERSION, create_app

__all__ = ["API_VERSION", "create_app"]
