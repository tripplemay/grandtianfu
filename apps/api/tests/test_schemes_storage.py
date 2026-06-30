# -*- coding: utf-8 -*-
"""FurnitureScheme storage: legacy default compatibility, migration, isolation."""
import json
from pathlib import Path

import pytest

from schemes import (
    SchemeError,
    SchemeConflict,
    SchemeNotFound,
    adjust_scheme,
    archive_scheme,
    confirm_scheme,
    create_scheme,
    delete_scheme,
    duplicate_scheme,
    get_scheme,
    list_renders,
    list_schemes,
    migrate_scheme,
    patch_scheme,
    read_furniture,
    append_render,
    set_preferred,
    write_furniture,
)


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    d = root / "D"
    d.mkdir(parents=True)
    (d / "geometry.json").write_text('{"meta":{"name":"D"}}', encoding="utf-8")
    (d / "furniture.json").write_text(
        json.dumps([{"t": "sofa", "room_id": "r1"}], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return root


def test_list_schemes_synthesizes_default_without_migration(tmp_path):
    root = _project(tmp_path)

    schemes = list_schemes(root, "D")

    assert schemes == [
        {
            "id": "default",
            "name": "初始方案",
            "source": "legacy",
            "status": "draft",
            "baseline_version_id": "v1",
            "preferred": False,
            "archived_at": None,
            "items": 1,
            "renders": 0,
            "updated_at": None,
        }
    ]
    assert not (root / "D" / "schemes").exists()


def test_read_default_furniture_uses_root_before_migration(tmp_path):
    root = _project(tmp_path)

    assert read_furniture(root, "D", "default") == [{"t": "sofa", "room_id": "r1"}]


def test_first_non_default_create_migrates_default_and_keeps_root(tmp_path):
    root = _project(tmp_path)

    created = create_scheme(
        root,
        "D",
        {
            "id": "scheme_manual_001",
            "name": "方案 A",
            "source": "manual",
            "base_scheme_id": "default",
            "furniture": [{"t": "chair", "room_id": "r1"}],
        },
    )

    assert created["id"] == "scheme_manual_001"
    assert read_furniture(root, "D", "default") == [{"t": "sofa", "room_id": "r1"}]
    assert read_furniture(root, "D", "scheme_manual_001") == [
        {"t": "chair", "room_id": "r1"}
    ]
    assert json.loads((root / "D" / "furniture.json").read_text(encoding="utf-8")) == [
        {"t": "sofa", "room_id": "r1"}
    ]
    assert (root / "D" / "schemes" / "default" / "meta.json").exists()


def test_writing_default_syncs_root_furniture(tmp_path):
    root = _project(tmp_path)

    write_furniture(root, "D", "default", [{"t": "table", "room_id": "r1"}])

    assert read_furniture(root, "D", "default") == [{"t": "table", "room_id": "r1"}]
    assert json.loads((root / "D" / "furniture.json").read_text(encoding="utf-8")) == [
        {"t": "table", "room_id": "r1"}
    ]


def test_writing_non_default_does_not_sync_root_furniture(tmp_path):
    root = _project(tmp_path)
    create_scheme(
        root,
        "D",
        {
            "id": "scheme_manual_001",
            "name": "方案 A",
            "source": "manual",
            "furniture": [],
        },
    )

    write_furniture(root, "D", "scheme_manual_001", [{"t": "desk", "room_id": "r1"}])

    assert read_furniture(root, "D", "scheme_manual_001") == [
        {"t": "desk", "room_id": "r1"}
    ]
    assert json.loads((root / "D" / "furniture.json").read_text(encoding="utf-8")) == [
        {"t": "sofa", "room_id": "r1"}
    ]


def test_duplicate_scheme_copies_furniture_and_metadata(tmp_path):
    root = _project(tmp_path)
    create_scheme(
        root,
        "D",
        {
            "id": "scheme_manual_001",
            "name": "方案 A",
            "source": "manual",
            "furniture": [{"t": "desk", "room_id": "r1"}],
        },
    )

    copied = duplicate_scheme(
        root,
        "D",
        "scheme_manual_001",
        {"id": "scheme_copy_001", "name": "方案 A 副本"},
    )

    assert copied["id"] == "scheme_copy_001"
    assert copied["source"] == "duplicate"
    assert copied["base_scheme_id"] == "scheme_manual_001"
    assert read_furniture(root, "D", "scheme_copy_001") == [
        {"t": "desk", "room_id": "r1"}
    ]


def test_patch_scheme_updates_name_and_status_only(tmp_path):
    root = _project(tmp_path)
    create_scheme(
        root,
        "D",
        {
            "id": "scheme_manual_001",
            "name": "方案 A",
            "source": "manual",
            "furniture": [],
        },
    )

    patched = patch_scheme(
        root,
        "D",
        "scheme_manual_001",
        {"id": "evil", "name": "方案 B", "status": "confirmed", "source": "ai"},
    )

    assert patched["id"] == "scheme_manual_001"
    assert patched["name"] == "方案 B"
    assert patched["status"] == "confirmed"
    assert patched["source"] == "manual"


def test_delete_default_is_rejected_and_non_default_is_soft_deleted(tmp_path):
    root = _project(tmp_path)
    create_scheme(
        root,
        "D",
        {
            "id": "scheme_manual_001",
            "name": "方案 A",
            "source": "manual",
            "furniture": [],
        },
    )

    with pytest.raises(SchemeError):
        delete_scheme(root, "D", "default")

    result = delete_scheme(root, "D", "scheme_manual_001")

    assert result["ok"] is True
    assert result["trashed"].startswith("scheme_manual_001-")
    with pytest.raises(SchemeNotFound):
        get_scheme(root, "D", "scheme_manual_001")
    assert any((root / "D" / "schemes" / ".trash").iterdir())


def test_render_history_is_scheme_scoped(tmp_path):
    root = _project(tmp_path)
    create_scheme(
        root,
        "D",
        {
            "id": "scheme_manual_001",
            "name": "方案 A",
            "source": "manual",
            "furniture": [],
        },
    )

    append_render(root, "D", "default", {"id": "r0", "url": "/api/artifacts/D/default.png"})
    append_render(
        root,
        "D",
        "scheme_manual_001",
        {"id": "r1", "url": "/api/artifacts/D/scheme_manual_001.png"},
    )

    assert [r["id"] for r in list_renders(root, "D", "default")] == ["r0"]
    assert [r["id"] for r in list_renders(root, "D", "scheme_manual_001")] == ["r1"]


def test_confirmed_scheme_requires_adjust_copy_for_furniture_changes(tmp_path):
    root = _project(tmp_path)
    create_scheme(
        root,
        "D",
        {
            "id": "scheme_manual_001",
            "name": "方案 A",
            "source": "manual",
            "furniture": [{"t": "desk", "room_id": "r1"}],
        },
    )

    confirmed = confirm_scheme(root, "D", "scheme_manual_001")

    assert confirmed["status"] == "confirmed"
    with pytest.raises(SchemeConflict):
        write_furniture(root, "D", "scheme_manual_001", [{"t": "chair"}])

    adjusted = adjust_scheme(
        root,
        "D",
        "scheme_manual_001",
        {"id": "scheme_adjust_001", "name": "方案 A - 调整版"},
    )

    assert adjusted["source"] == "duplicate"
    assert adjusted["status"] == "draft"
    assert adjusted["base_scheme_id"] == "scheme_manual_001"
    assert adjusted["baseline_version_id"] == "v1"
    assert read_furniture(root, "D", "scheme_adjust_001") == [{"t": "desk", "room_id": "r1"}]
    assert list_renders(root, "D", "scheme_adjust_001") == []


def test_preferred_is_unique_per_baseline_and_archive_excludes_default_list(tmp_path):
    root = _project(tmp_path)
    create_scheme(root, "D", {"id": "scheme_a", "name": "方案 A", "source": "manual"})
    create_scheme(root, "D", {"id": "scheme_b", "name": "方案 B", "source": "manual"})

    set_preferred(root, "D", "scheme_a")
    set_preferred(root, "D", "scheme_b")

    assert get_scheme(root, "D", "scheme_a")["preferred"] is False
    assert get_scheme(root, "D", "scheme_b")["preferred"] is True

    archived = archive_scheme(root, "D", "scheme_b")
    assert archived["status"] == "archived"
    assert archived["preferred"] is False
    listed = list_schemes(root, "D")
    assert "scheme_b" not in [item["id"] for item in listed]
    listed_with_archived = list_schemes(root, "D", include_archived=True)
    assert "scheme_b" in [item["id"] for item in listed_with_archived]


def test_historical_baseline_scheme_is_readable_but_not_writable_and_can_migrate(tmp_path):
    root = _project(tmp_path)
    repo_root = Path(__file__).resolve().parents[3]
    (root / "D" / "geometry.json").write_text(
        (repo_root / "data" / "projects" / "D" / "geometry.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    create_scheme(
        root,
        "D",
        {
            "id": "scheme_old",
            "name": "旧方案",
            "source": "manual",
            "furniture": [{"t": "desk", "room_id": "missing_room"}],
        },
    )
    # Move current baseline to v2 to make v1 schemes historical.
    import baselines

    baselines.create_baseline(root, "D", {"source_version_id": "v1"})
    baselines.confirm_baseline(root, "D", "v2")

    assert read_furniture(root, "D", "scheme_old") == [
        {"t": "desk", "room_id": "missing_room"}
    ]
    with pytest.raises(SchemeConflict):
        write_furniture(root, "D", "scheme_old", [{"t": "desk"}])
    with pytest.raises(SchemeConflict):
        append_render(root, "D", "scheme_old", {"id": "r-old"})

    migrated = migrate_scheme(
        root,
        "D",
        "scheme_old",
        {
            "target_baseline_version_id": "v2",
            "id": "scheme_new",
            "name": "旧方案 - V2",
        },
    )

    assert migrated["baseline_version_id"] == "v2"
    assert migrated["status"] == "draft"
    assert migrated["source"] == "migrated"
    assert "missing_room" in migrated["migration_warnings"][0]
