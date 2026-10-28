"""选品打分模块。

只做判断，不做采集。数据来源：你从 1688 / 淘宝 / 小红书看到的公开信息。
"""

from .score import LABELS, VETO_LABELS, WEIGHTS, Candidate, rank
from .store import DEFAULT_FILE, init, load, save

__all__ = [
    "Candidate",
    "rank",
    "WEIGHTS",
    "LABELS",
    "VETO_LABELS",
    "load",
    "save",
    "init",
    "DEFAULT_FILE",
]
