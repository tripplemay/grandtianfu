# -*- coding: utf-8 -*-
"""进程内异步任务管理 (MVP, 无 Redis)。

为何异步: spike 实测生成耗时 90-225s, 同步请求会被 nginx/浏览器超时打断。
端点提交任务即返 job_id, 前端轮询 /api/ai/jobs/{id}。
并发模型: Dockerfile 固定单 uvicorn worker -> 单进程内存 registry 即可 (多 worker 不共享)。
重启丢在途任务 (已完成产物已落盘 artifacts, 不丢); 规模化再换 Redis/RQ。
"""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable


class JobManager:
    def __init__(self, max_workers: int = 2, max_jobs: int = 512):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="aijob")
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._max_jobs = max_jobs

    def _prune_locked(self) -> None:
        """超出上限时按 created 最旧的 done/error 任务先淘汰 (调用方须持 self._lock)。

        防 registry 无界增长 (长跑内存泄漏); 在途 (queued/running) 任务永不淘汰。
        """
        if len(self._jobs) <= self._max_jobs:
            return
        finished = sorted(
            (j for j in self._jobs.values() if j["status"] in ("done", "error")),
            key=lambda j: j["created"],
        )
        for job in finished:
            if len(self._jobs) <= self._max_jobs:
                break
            self._jobs.pop(job["id"], None)

    def submit(self, fn: Callable[[], Any], *, meta: dict | None = None) -> str:
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "status": "queued",
                "result": None,
                "error": None,
                "meta": meta or {},
                "created": time.time(),
                "updated": time.time(),
            }
            self._prune_locked()
        self._executor.submit(self._run, job_id, fn)
        return job_id

    def _set(self, job_id: str, **kw: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.update(kw)
                job["updated"] = time.time()

    def _run(self, job_id: str, fn: Callable[[], Any]) -> None:
        self._set(job_id, status="running")
        try:
            result = fn()
            self._set(job_id, status="done", result=result)
        except Exception as exc:  # noqa: BLE001 — 任务边界: 任何异常落到 job.error, 不崩 worker
            self._set(
                job_id,
                status="error",
                error=str(exc),
                traceback=traceback.format_exc()[:2000],
            )

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None
