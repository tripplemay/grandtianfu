# -*- coding: utf-8 -*-
"""FurnitureScheme storage: legacy default compatibility, migration, isolation."""
import json
from pathlib import Path

import pytest

from schemes import (
    SchemeError,
    SchemeConflict,
    SchemeNotFound,
    archive_scheme,
    restore_scheme,
    migrate_scheme_status,
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
            "style_prompt": "",
            "status": "draft",
            "baseline_version_id": "v1",
            "preferred": False,
            "archived_at": None,
            "items": 1,
            "renders": 0,
            "latest_render_url": None,
            "latest_render_thumb_url": None,
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
    # Phase D (D-3): patch 只改 name; status/source/id 均忽略, 保持 draft/manual。
    assert patched["status"] == "draft"
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


def test_scheme_is_directly_writable_no_confirm_lock(tmp_path):
    # Phase D: 砍掉 confirm 锁 —— 方案恒可写, 无需先建调整副本。副本走 duplicate。
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
    # 直接改家具, 不再 409。
    write_furniture(root, "D", "scheme_manual_001", [{"t": "chair", "room_id": "r1"}])
    assert read_furniture(root, "D", "scheme_manual_001") == [{"t": "chair", "room_id": "r1"}]
    # 需要副本走 duplicate (adjust 已下线)。
    copy = duplicate_scheme(
        root, "D", "scheme_manual_001", {"id": "scheme_copy_001", "name": "副本"}
    )
    assert copy["source"] == "duplicate" and copy["status"] == "draft"
    assert copy["base_scheme_id"] == "scheme_manual_001"


def test_archive_restore_roundtrip(tmp_path):
    # Phase D (D-5): 归档=可逆暂存, restore 把 archived 恢复回 draft。
    root = _project(tmp_path)
    create_scheme(root, "D", {"id": "s1", "name": "A", "source": "manual", "furniture": []})
    archived = archive_scheme(root, "D", "s1")
    assert archived["status"] == "archived" and archived["archived_at"]
    with pytest.raises(SchemeConflict):  # 归档态禁写
        write_furniture(root, "D", "s1", [{"t": "chair"}])
    restored = restore_scheme(root, "D", "s1")
    assert restored["status"] == "draft" and restored["archived_at"] is None
    write_furniture(root, "D", "s1", [{"t": "chair", "room_id": "r1"}])  # 恢复后可写
    with pytest.raises(SchemeConflict):  # 非归档件不能 restore
        restore_scheme(root, "D", "s1")


def test_migrate_scheme_status_coerces_confirmed_to_draft(tmp_path):
    # D-1 迁移脚本: 磁盘上遗留 confirmed 归一化为 draft, 幂等。
    root = _project(tmp_path)
    create_scheme(root, "D", {"id": "s1", "name": "A", "source": "manual", "furniture": []})
    # 直接把磁盘 meta 篡为 confirmed (模拟线上遗留数据)。
    meta_path = root / "D" / "schemes" / "s1" / "meta.json"
    m = json.loads(meta_path.read_text("utf-8"))
    m["status"] = "confirmed"
    meta_path.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")

    result = migrate_scheme_status(root)
    assert "D/s1" in result["changed"] and result["count"] == 1
    assert json.loads(meta_path.read_text("utf-8"))["status"] == "draft"
    # 幂等: 再跑无改动。
    assert migrate_scheme_status(root)["count"] == 0


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
            "furniture": [
                {"t": "desk", "room_id": "missing_room"},
                {"t": "plant", "room_id": "r_live", "dcx": 99999, "dcy": 99999},
            ],
        },
    )
    # Move current baseline to v2 to make v1 schemes historical.
    import baselines

    baselines.create_baseline(root, "D", {"source_version_id": "v1"})
    baselines.confirm_baseline(root, "D", "v2")

    assert read_furniture(root, "D", "scheme_old") == [
        {"t": "desk", "room_id": "missing_room"},
        {"t": "plant", "room_id": "r_live", "dcx": 99999, "dcy": 99999},
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
    assert any("超出房间" in warning for warning in migrated["migration_warnings"])


def test_append_render_is_safe_under_concurrent_appends(tmp_path):
    """并发 append_render (JobManager 双 worker 场景) 不得互相覆盖丢历史。"""
    import threading

    root = _project(tmp_path)

    def _append(i: int) -> None:
        append_render(
            root, "D", "default", {"id": f"r{i}", "url": f"/api/artifacts/D/default/r{i}.png"}
        )

    threads = [threading.Thread(target=_append, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ids = {r["id"] for r in list_renders(root, "D", "default")}
    assert ids == {f"r{i}" for i in range(8)}


def test_append_render_rejects_unknown_mode(tmp_path):
    """审计 P1-2: mode 受控词表, 未知 mode 拒绝入历史。"""
    root = _project(tmp_path)
    with pytest.raises(SchemeError):
        append_render(root, "D", "default", {"id": "x", "url": "/a.png", "mode": "mystery"})
    # 合法 mode 与 legacy 无 mode 均可写。
    append_render(root, "D", "default", {"id": "a", "url": "/a.png", "mode": "axon-photoreal"})
    append_render(root, "D", "default", {"id": "b", "url": "/b.png"})
