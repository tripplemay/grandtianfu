# -*- coding: utf-8 -*-
"""预算护栏: 预扣/释放、每项目与当日上限、跨天归零、落盘持久、token 计量。"""
import json

import pytest

from aigc.budget import BudgetGuard
from aigc.config import Settings
from aigc.errors import BudgetExceeded


def _settings(tmp_path, **over):
    base = dict(
        provider="openai", base_url="https://x/v1", api_key="k", model="gpt-image-2",
        proxy=None, request_timeout_s=300.0,
        artifacts_dir=str(tmp_path), uploads_dir=str(tmp_path / "up"),
        max_images_per_project=3, daily_image_cap=5,
    )
    base.update(over)
    return Settings(**base)


def _guard(tmp_path, **over):
    return BudgetGuard(_settings(tmp_path, **over), path=str(tmp_path / "_budget.json"))


def test_reserve_increments_and_status(tmp_path):
    g = _guard(tmp_path)
    g.reserve("D")
    g.reserve("D")
    st = g.status()
    assert st["daily_count"] == 2
    assert st["per_project_cap"] == 3


def test_per_project_cap_blocks(tmp_path):
    g = _guard(tmp_path, max_images_per_project=2)
    g.reserve("D")
    g.reserve("D")
    with pytest.raises(BudgetExceeded):
        g.reserve("D")
    # 其他项目不受影响
    g.reserve("E")


def test_daily_cap_blocks_across_projects(tmp_path):
    g = _guard(tmp_path, daily_image_cap=2, max_images_per_project=100)
    g.reserve("A")
    g.reserve("B")
    with pytest.raises(BudgetExceeded):
        g.reserve("C")


def test_release_decrements_and_is_floored(tmp_path):
    g = _guard(tmp_path)
    g.reserve("D")
    g.release("D")
    g.release("D")  # 幂等不为负
    assert g.status()["daily_count"] == 0


def test_cross_day_resets_daily_not_project(tmp_path, monkeypatch):
    import aigc.budget as budget_mod
    monkeypatch.setattr(budget_mod, "_today", lambda: "2026-06-29")
    g = _guard(tmp_path, daily_image_cap=1, max_images_per_project=10)
    g.reserve("D")
    with pytest.raises(BudgetExceeded):
        g.reserve("D")  # 当日已满
    monkeypatch.setattr(budget_mod, "_today", lambda: "2026-06-30")
    g.reserve("D")  # 次日当日计数归零, 放行
    assert g.status()["daily_count"] == 1


def test_persists_across_instances(tmp_path):
    _guard(tmp_path).reserve("D")
    again = _guard(tmp_path)
    assert again.status()["daily_count"] == 1


def test_record_tokens_accumulates(tmp_path):
    g = _guard(tmp_path)
    g.record_tokens({"total_tokens": 100})
    g.record_tokens({"total_tokens": 50})
    assert g.status()["total_tokens"] == 150


def test_corrupt_budget_file_recovers(tmp_path):
    (tmp_path / "_budget.json").write_text("{ not json", encoding="utf-8")
    g = _guard(tmp_path)
    g.reserve("D")  # 损坏文件回退默认, 不崩
    assert json.loads((tmp_path / "_budget.json").read_text())["daily_count"] == 1


def test_concurrent_reserve_no_oversell(tmp_path):
    """50 线程争抢 cap=20: 恰好放行 20 张, 不超卖 (验证 _LOCK 覆盖 read-modify-write)。"""
    import threading

    g = _guard(tmp_path, daily_image_cap=20, max_images_per_project=100)
    ok: list[int] = []
    barrier = threading.Barrier(50)

    def worker():
        barrier.wait()  # 尽量同时冲闸, 放大竞态窗口
        try:
            g.reserve("D")
            ok.append(1)
        except BudgetExceeded:
            pass

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ok) == 20
    assert g.status()["daily_count"] == 20


def test_furnish_daily_cap_blocks_and_status_reports(tmp_path):
    g = _guard(tmp_path, furnish_daily_cap=2)
    g.reserve_furnish()
    g.reserve_furnish()
    with pytest.raises(BudgetExceeded):
        g.reserve_furnish()
    st = g.status()
    assert st["furnish_daily_count"] == 2
    assert st["furnish_daily_cap"] == 2
