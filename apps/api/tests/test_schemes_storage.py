# -*- coding: utf-8 -*-
"""FurnitureScheme storage: legacy default compatibility, migration, isolation."""
import json
from pathlib import Path

import pytest

from schemes import (
    SchemeError,
    SchemeNotFound,
    create_scheme,
    delete_scheme,
    duplicate_scheme,
    get_scheme,
    list_renders,
    list_schemes,
    patch_scheme,
    read_furniture,
    append_render,
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
            "name": "默认方案",
            "source": "legacy",
            "status": "confirmed",
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
