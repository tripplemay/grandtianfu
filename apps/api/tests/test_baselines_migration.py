# -*- coding: utf-8 -*-
"""Stage 0 baseline migration: dry-run, idempotence, and byte preservation."""
import json
import os
from pathlib import Path

import pytest

from baselines import BaselineConflict, migrate_project, project_lock


def _write_project(root: Path, *, with_scheme: bool = False) -> Path:
    project = root / "D"
    project.mkdir(parents=True)
    repo_root = Path(__file__).resolve().parents[3]
    geometry_bytes = (repo_root / "data" / "projects" / "D" / "geometry.json").read_bytes()
    (project / "geometry.json").write_bytes(geometry_bytes)
    (project / "furniture.json").write_text(
        json.dumps([{"t": "sofa", "room_id": "r_live"}], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    if with_scheme:
        scheme = project / "schemes" / "scheme_manual_001"
        scheme.mkdir(parents=True)
        (scheme / "meta.json").write_text(
            json.dumps(
                {
                    "id": "scheme_manual_001",
                    "name": "现代轻奢方案",
                    "source": "manual",
                    "status": "confirmed",
                    "created_at": "2026-06-01T00:00:00Z",
                    "updated_at": "2026-06-01T00:00:00Z",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (scheme / "furniture.json").write_text(
            json.dumps([{"t": "chair", "room_id": "r_live"}], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        (scheme / "renders.json").write_text(
            json.dumps([{"id": "r1", "url": "/api/artifacts/D/scheme/r1.png"}]),
            encoding="utf-8",
        )
    return project


def test_migrate_project_dry_run_reports_without_writing(tmp_path):
    root = tmp_path / "projects"
    project = _write_project(root)
    before = sorted(p.relative_to(project).as_posix() for p in project.rglob("*"))

    report = migrate_project(root, "D", dry_run=True, now="2026-06-30T00:00:00Z")

    after = sorted(p.relative_to(project).as_posix() for p in project.rglob("*"))
    assert report["dry_run"] is True
    assert report["changed"] is True
    assert before == after
    assert not (project / ".project.lock").exists()
    assert any(op["action"] == "create-project-meta" for op in report["operations"])
    assert any(op["action"] == "copy-baseline-geometry" for op in report["operations"])


def test_migrate_project_apply_creates_baseline_structure_and_preserves_root_bytes(tmp_path):
    root = tmp_path / "projects"
    project = _write_project(root)
    root_geometry_before = (project / "geometry.json").read_bytes()
    root_furniture_before = (project / "furniture.json").read_bytes()

    report = migrate_project(root, "D", dry_run=False, now="2026-06-30T00:00:00Z")

    assert report["changed"] is True
    assert (project / "geometry.json").read_bytes() == root_geometry_before
    assert (project / "furniture.json").read_bytes() == root_furniture_before
    assert (project / "baselines" / "v1" / "geometry.json").read_bytes() == root_geometry_before
    project_meta = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert project_meta["current_baseline_version_id"] == "v1"
    assert project_meta["next_baseline_version"] == 2
    baseline_meta = json.loads((project / "baselines" / "v1" / "meta.json").read_text(encoding="utf-8"))
    assert baseline_meta["status"] == "confirmed"
    default_meta = json.loads((project / "schemes" / "default" / "meta.json").read_text(encoding="utf-8"))
    assert default_meta["name"] == "初始方案"
    assert default_meta["baseline_version_id"] == "v1"
    assert default_meta["preferred"] is False
    assert default_meta["archived_at"] is None
    assert (project / "schemes" / "default" / "furniture.json").read_bytes() == root_furniture_before


def test_migrate_project_is_idempotent_after_apply(tmp_path):
    root = tmp_path / "projects"
    project = _write_project(root, with_scheme=True)

    first = migrate_project(root, "D", dry_run=False, now="2026-06-30T00:00:00Z")
    second = migrate_project(root, "D", dry_run=False, now="2026-07-01T00:00:00Z")

    assert first["changed"] is True
    assert second["changed"] is False
    assert second["operations"] == []
    scheme_meta = json.loads(
        (project / "schemes" / "scheme_manual_001" / "meta.json").read_text(encoding="utf-8")
    )
    assert scheme_meta["name"] == "现代轻奢方案"
    assert scheme_meta["status"] == "confirmed"
    assert scheme_meta["baseline_version_id"] == "v1"
    assert scheme_meta["preferred"] is False
    assert scheme_meta["archived_at"] is None
    assert json.loads(
        (project / "schemes" / "scheme_manual_001" / "renders.json").read_text(encoding="utf-8")
    ) == [{"id": "r1", "url": "/api/artifacts/D/scheme/r1.png"}]


def test_project_lock_rejects_concurrent_acquire(tmp_path):
    root = tmp_path / "projects"
    _write_project(root)

    with project_lock(root, "D"):
        with pytest.raises(BaselineConflict):
            with project_lock(root, "D", timeout_s=0):
                pass

    # flock: 锁文件持久保留 (复用句柄, 不 unlink), 但锁已释放 -> 可再次获取。
    assert (root / "D" / ".project.lock").exists()
    with project_lock(root, "D", timeout_s=1):
        pass


def test_migration_backup_excludes_project_lock(tmp_path):
    root = tmp_path / "projects"
    _write_project(root)

    report = migrate_project(
        root,
        "D",
        dry_run=False,
        backup=True,
        now="2026-06-30T00:00:00Z",
    )

    backup_path = Path(report["backup_path"])
    assert backup_path.exists()
    assert not (backup_path / ".project.lock").exists()
    assert (backup_path / "geometry.json").exists()


def test_project_lock_leftover_file_does_not_block(tmp_path):
    """flock: 崩溃残留的锁文件 (无进程持 flock) 不阻塞获取 —— 取代旧 mtime 陈旧检测/破锁。"""
    root = tmp_path / "projects"
    _write_project(root)
    leftover = root / "D" / ".project.lock"
    leftover.write_text("pid=99999 acquired_at=old\n", encoding="utf-8")
    # 原持有者已死亡 -> 内核早已释放其 flock; 残留文件不阻塞新获取, 无需 stale 等待。
    with project_lock(root, "D", timeout_s=1):
        pass


@pytest.mark.skipif(not hasattr(os, "fork"), reason="需 POSIX fork")
def test_project_lock_released_when_holder_dies(tmp_path):
    """flock: 持锁进程被 SIGKILL 后内核自动释放锁, 其它进程可获取 (无陈旧残留死锁)。"""
    import signal
    import time

    root = tmp_path / "projects"
    _write_project(root)
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:  # 子进程: 获取锁并阻塞 (不主动释放), 管道通知父进程已持锁
        os.close(r)
        try:
            with project_lock(root, "D", timeout_s=5):
                os.write(w, b"x")
                time.sleep(30)
        finally:
            os._exit(0)
    try:
        os.close(w)
        assert os.read(r, 1) == b"x", "子进程未能获取锁"
        os.close(r)
        with pytest.raises(BaselineConflict):  # 子进程持锁 -> 父进程冲突
            with project_lock(root, "D", timeout_s=0):
                pass
        os.kill(pid, signal.SIGKILL)  # kill -9 -> 内核释放 flock
        os.waitpid(pid, 0)
        with project_lock(root, "D", timeout_s=2):  # 现在应能获取
            pass
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except (ProcessLookupError, ChildProcessError):
            pass


def test_remigration_does_not_demote_confirmed_default_scheme(tmp_path):
    """审计 P2 legacy 收口: migrate_project 重跑不得把已确认/已绑 v2 的 default 改回 draft+v1。"""
    root = tmp_path / "projects"
    _write_project(root)
    migrate_project(root, "D", dry_run=False)
    meta_path = root / "D" / "schemes" / "default" / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["status"] = "confirmed"
    meta["baseline_version_id"] = "v2"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    migrate_project(root, "D", dry_run=False)

    after = json.loads(meta_path.read_text(encoding="utf-8"))
    assert after["status"] == "confirmed"
    assert after["baseline_version_id"] == "v2"
    assert after["name"] == "初始方案"
