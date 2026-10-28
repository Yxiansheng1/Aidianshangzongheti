"""后台任务。

生成一张图要几分钟，生成一段视频要几十分钟。HTTP 请求不能挂在那里等，
所以统一丢进线程池，前端轮询状态。
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"  # queued / running / done / error
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None

    def to_dict(self) -> dict[str, Any]:
        base = self.finished or time.time()
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "elapsed": round(base - (self.started or self.created), 1),
        }


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def recent(self, limit: int = 20) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created, reverse=True)[:limit]

    def submit(self, kind: str, fn: Callable[[Job], dict[str, Any] | None]) -> Job:
        job = Job(id=uuid.uuid4().hex, kind=kind)
        with self._lock:
            self._jobs[job.id] = job
            # 只留最近 50 个，避免长时间开着占内存
            if len(self._jobs) > 50:
                for old in sorted(self._jobs.values(), key=lambda j: j.created)[:10]:
                    if old.status in ("done", "error"):
                        self._jobs.pop(old.id, None)

        def runner() -> None:
            job.status = "running"
            job.started = time.time()
            try:
                job.result = fn(job) or {}
                job.status = "done"
            except Exception as exc:  # noqa: BLE001 —— 后台线程必须兜住所有异常
                job.status = "error"
                job.error = str(exc)
            finally:
                job.finished = time.time()

        threading.Thread(target=runner, daemon=True, name=f"job-{kind}").start()
        return job


REGISTRY = JobRegistry()
