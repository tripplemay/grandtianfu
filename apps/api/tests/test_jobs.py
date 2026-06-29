# -*- coding: utf-8 -*-
"""异步任务管理: 成功落 result、异常落 error、未知 id 返 None。"""
import time

from aigc.jobs import JobManager


def _wait(mgr, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = mgr.get(job_id)
        if job and job["status"] in ("done", "error"):
            return job
        time.sleep(0.02)
    raise AssertionError("job 未在超时内完成")


def test_success_sets_result():
    mgr = JobManager()
    jid = mgr.submit(lambda: {"path": "x.png"}, meta={"kind": "render"})
    job = _wait(mgr, jid)
    assert job["status"] == "done"
    assert job["result"] == {"path": "x.png"}
    assert job["meta"]["kind"] == "render"


def test_exception_sets_error():
    mgr = JobManager()

    def boom():
        raise RuntimeError("provider down")

    jid = mgr.submit(boom)
    job = _wait(mgr, jid)
    assert job["status"] == "error"
    assert "provider down" in job["error"]


def test_unknown_job_is_none():
    assert JobManager().get("nope") is None
