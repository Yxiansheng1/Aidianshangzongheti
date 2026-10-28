"""本地 Web 界面。"""

from .jobs import REGISTRY, Job, JobRegistry
from .server import serve

__all__ = ["serve", "REGISTRY", "Job", "JobRegistry"]
