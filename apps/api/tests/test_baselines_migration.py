# -*- coding: utf-8 -*-
"""Stage 0 baseline migration: dry-run, idempotence, and byte preservation."""
import json
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

    assert not (root / "D" / ".project.lock").exists()


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


def test_project_lock_breaks_stale_lock(tmp_path):
    """持锁进程 kill -9 残留的陈旧锁不应永久阻塞项目 (按锁龄自愈破锁)。"""
    import os as _os
    import time

    root = tmp_path / "projects"
    _write_project(root)
    stale = root / "D" / ".project.lock"
    stale.write_text("pid=99999 created_at=old\n", encoding="utf-8")
    old = time.time() - 3600
    _os.utime(stale, (old, old))

    with project_lock(root, "D", timeout_s=1, stale_s=120):
        pass

    assert not stale.exists()


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
