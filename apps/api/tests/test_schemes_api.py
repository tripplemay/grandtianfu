# -*- coding: utf-8 -*-
"""Scheme API routes: CRUD, furniture, render, and legacy default behavior."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

import main


def _write_project(root: Path, project_id: str = "D") -> None:
    project = root / project_id
    project.mkdir(parents=True)
    repo_root = Path(__file__).resolve().parents[3]
    geometry = json.loads(
        (repo_root / "data" / "projects" / "D" / "geometry.json").read_text(
            encoding="utf-8"
        )
    )
    (project / "geometry.json").write_text(
        json.dumps(geometry, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (project / "furniture.json").write_text(
        json.dumps(
            [{"t": "sofa", "w": 100, "h": 80, "room_id": "r_live", "dx": 10, "dy": 10}],
            indent=1,
        ),
        encoding="utf-8",
    )


def _client(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    _write_project(root)
    monkeypatch.setattr(main, "DATA_DIR", str(root))
    return TestClient(main.app), root


def test_scheme_crud_and_furniture_routes(tmp_path, monkeypatch):
    client, root = _client(tmp_path, monkeypatch)

    listed = client.get("/api/projects/D/schemes")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == "default"
    assert listed.json()[0]["name"] == "初始方案"
    assert listed.json()[0]["baseline_version_id"] == "v1"

    created = client.post(
        "/api/projects/D/schemes",
        json={
            "id": "scheme_manual_001",
            "name": "方案 A",
            "source": "manual",
            "base_scheme_id": "default",
            "furniture": [{"t": "desk", "w": 120, "h": 60, "room_id": "r_live", "dx": 20, "dy": 20}],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["id"] == "scheme_manual_001"
    assert (root / "D" / "schemes" / "default" / "furniture.json").exists()

    furniture = client.get("/api/projects/D/schemes/scheme_manual_001/furniture")
    assert furniture.status_code == 200
    assert furniture.json() == [{"t": "desk", "w": 120, "h": 60, "room_id": "r_live", "dx": 20, "dy": 20}]

    saved = client.post(
        "/api/projects/D/schemes/scheme_manual_001/save-furniture",
        json=[{"t": "chair", "w": 50, "h": 50, "room_id": "r_live", "dx": 30, "dy": 30}],
    )
    assert saved.status_code == 200
    assert client.get("/api/projects/D/schemes/scheme_manual_001/furniture").json() == [
        {"t": "chair", "w": 50, "h": 50, "room_id": "r_live", "dx": 30, "dy": 30}
    ]
    assert client.get("/api/projects/D/furniture").json() == [
        {"t": "sofa", "w": 100, "h": 80, "room_id": "r_live", "dx": 10, "dy": 10}
    ]

    patched = client.patch(
        "/api/projects/D/schemes/scheme_manual_001",
        json={"name": "方案 B", "source": "ai"},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "方案 B"
    assert patched.json()["source"] == "manual"

    copied = client.post(
        "/api/projects/D/schemes/scheme_manual_001/duplicate",
        json={"id": "scheme_copy_001", "name": "方案 B 副本"},
    )
    assert copied.status_code == 201
    assert copied.json()["base_scheme_id"] == "scheme_manual_001"
    assert client.get("/api/projects/D/schemes/scheme_copy_001/furniture").json() == [
        {"t": "chair", "w": 50, "h": 50, "room_id": "r_live", "dx": 30, "dy": 30}
    ]

    assert client.delete("/api/projects/D/schemes/default").status_code in (400, 409)
    deleted = client.delete("/api/projects/D/schemes/scheme_copy_001")
    assert deleted.status_code == 200
    assert client.get("/api/projects/D/schemes/scheme_copy_001").status_code == 404


def test_default_scheme_save_keeps_legacy_endpoint_in_sync(tmp_path, monkeypatch):
    client, _root = _client(tmp_path, monkeypatch)

    res = client.post(
        "/api/projects/D/schemes/default/save-furniture",
        json=[{"t": "table", "w": 80, "h": 80, "room_id": "r_live", "dx": 0, "dy": 0}],
    )

    assert res.status_code == 200
    assert client.get("/api/projects/D/furniture").json() == [
        {"t": "table", "w": 80, "h": 80, "room_id": "r_live", "dx": 0, "dy": 0}
    ]


def test_scheme_render_uses_selected_furniture(tmp_path, monkeypatch):
    client, _root = _client(tmp_path, monkeypatch)
    client.post(
        "/api/projects/D/schemes",
        json={
            "id": "scheme_manual_001",
            "name": "方案 A",
            "source": "manual",
            "furniture": [{"t": "plant", "room_id": "r_live", "dcx": 140, "dcy": 120, "r": 18}],
        },
    )

    legacy = client.get("/api/projects/D/render?mode=plan2d")
    scheme = client.get("/api/projects/D/schemes/scheme_manual_001/render?mode=plan2d")

    assert legacy.status_code == 200, legacy.text
    assert scheme.status_code == 200, scheme.text
    assert legacy.content != scheme.content


def test_scheme_routes_validate_ids(tmp_path, monkeypatch):
    client, _root = _client(tmp_path, monkeypatch)

    assert client.get("/api/projects/../D/schemes").status_code in (400, 404)
    assert client.get("/api/projects/D/schemes/../evil/furniture").status_code in (400, 404)


def test_scheme_lifecycle_confirm_adjust_preferred_archive(tmp_path, monkeypatch):
    client, _root = _client(tmp_path, monkeypatch)
    client.post(
        "/api/projects/D/schemes",
        json={
            "id": "scheme_manual_001",
            "name": "现代轻奢方案",
            "source": "manual",
            "furniture": [{"t": "desk", "room_id": "r_live", "dx": 20, "dy": 20, "w": 120, "h": 60}],
        },
    )
    client.post(
        "/api/projects/D/schemes",
        json={"id": "scheme_manual_002", "name": "原木方案", "source": "manual"},
    )

    confirmed = client.post("/api/projects/D/schemes/scheme_manual_001/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    assert (
        client.post(
            "/api/projects/D/schemes/scheme_manual_001/save-furniture",
            json=[{"t": "chair", "room_id": "r_live", "dx": 10, "dy": 10}],
        ).status_code
        == 409
    )

    adjusted = client.post(
        "/api/projects/D/schemes/scheme_manual_001/adjust",
        json={"id": "scheme_adjust_001", "name": "现代轻奢方案 - 调整版"},
    )
    assert adjusted.status_code == 201, adjusted.text
    assert adjusted.json()["status"] == "draft"
    assert adjusted.json()["base_scheme_id"] == "scheme_manual_001"
    assert client.get("/api/projects/D/schemes/scheme_adjust_001/renders").json() == []

    preferred = client.post("/api/projects/D/schemes/scheme_manual_002/set-preferred")
    assert preferred.status_code == 200, preferred.text
    assert preferred.json()["preferred"] is True
    assert client.get("/api/projects/D/schemes/scheme_manual_001").json()["preferred"] is False

    archived = client.post("/api/projects/D/schemes/scheme_manual_002/archive")
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"
    listed = client.get("/api/projects/D/schemes").json()
    assert "scheme_manual_002" not in [s["id"] for s in listed]
    listed_with_archived = client.get("/api/projects/D/schemes?include_archived=true").json()
    assert "scheme_manual_002" in [s["id"] for s in listed_with_archived]


def test_historical_baseline_scheme_api_is_readonly_and_migrates(tmp_path, monkeypatch):
    client, _root = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/projects/D/schemes",
        json={
            "id": "scheme_legacy_v1",
            "name": "V1 方案",
            "source": "manual",
            "furniture": [{"t": "desk", "room_id": "r_live", "dx": 20, "dy": 20, "w": 120, "h": 60}],
        },
    )
    assert created.status_code == 201, created.text
    assert client.post("/api/projects/D/baselines", json={"source_version_id": "v1"}).status_code == 201
    assert client.post("/api/projects/D/baselines/v2/confirm").status_code == 200

    assert (
        client.post(
            "/api/projects/D/schemes/scheme_legacy_v1/save-furniture",
            json=[{"t": "chair", "room_id": "r_live", "dx": 10, "dy": 10}],
        ).status_code
        == 409
    )
    assert client.post("/api/projects/D/schemes/scheme_legacy_v1/render-ai").status_code in (
        409,
        503,
    )

    listed_current = client.get("/api/projects/D/schemes").json()
    assert "scheme_legacy_v1" not in [s["id"] for s in listed_current]
    listed_v1 = client.get("/api/projects/D/schemes?baseline_version_id=v1").json()
    assert "scheme_legacy_v1" in [s["id"] for s in listed_v1]

    migrated = client.post(
        "/api/projects/D/schemes/scheme_legacy_v1/migrate",
        json={
            "target_baseline_version_id": "v2",
            "id": "scheme_v2",
            "name": "V1 方案 - V2",
        },
    )
    assert migrated.status_code == 201, migrated.text
    assert migrated.json()["baseline_version_id"] == "v2"
    assert migrated.json()["status"] == "draft"


def test_scheme_render_uses_bound_baseline_after_project_current_changes(tmp_path, monkeypatch):
    client, root = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/projects/D/schemes",
        json={
            "id": "scheme_v1",
            "name": "V1 方案",
            "source": "manual",
            "furniture": [{"t": "plant", "room_id": "r_live", "dcx": 140, "dcy": 120, "r": 18}],
        },
    )
    assert created.status_code == 201, created.text
    before = client.get("/api/projects/D/schemes/scheme_v1/render?mode=plan2d")
    assert before.status_code == 200, before.text

    assert client.post("/api/projects/D/baselines", json={"source_version_id": "v1"}).status_code == 201
    assert client.post("/api/projects/D/baselines/v2/confirm").status_code == 200
    root_geometry_path = root / "D" / "geometry.json"
    root_geometry = json.loads(root_geometry_path.read_text(encoding="utf-8"))
    root_geometry["rooms"][0]["rect"][0] += 200
    root_geometry_path.write_text(
        json.dumps(root_geometry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    after = client.get("/api/projects/D/schemes/scheme_v1/render?mode=plan2d")
    assert after.status_code == 200, after.text
    assert after.content == before.content


def test_save_furniture_rejects_malformed_items(tmp_path, monkeypatch):
    """审计 P1-3: 写边界 400+定位, 坏件不再延迟到渲染期 KeyError->500。"""
    client, _root = _client(tmp_path, monkeypatch)

    no_t = client.post(
        "/api/projects/D/schemes/default/save-furniture",
        json=[{"room_id": "r_live", "dx": 1, "dy": 1}],
    )
    assert no_t.status_code == 400 and "furniture[0]" in no_t.json()["error"]

    absolute_legacy = client.post(
        "/api/projects/D/schemes/default/save-furniture",
        json=[{"t": "sofa", "x": 10, "y": 10, "w": 100, "h": 80}],
    )
    assert absolute_legacy.status_code == 400
    assert "room_id" in absolute_legacy.json()["error"]

    no_coords = client.post(
        "/api/projects/D/schemes/default/save-furniture",
        json=[{"t": "sofa", "room_id": "r_live"}],
    )
    assert no_coords.status_code == 400

    unknown_type_no_size = client.post(
        "/api/projects/D/schemes/default/save-furniture",
        json=[{"t": "spaceship", "room_id": "r_live", "dx": 1, "dy": 1}],
    )
    assert unknown_type_no_size.status_code == 400

    ok = client.post(
        "/api/projects/D/schemes/default/save-furniture",
        json=[{"t": "sofa", "room_id": "r_live", "dx": 1, "dy": 1}],  # 尺寸由目录补
    )
    assert ok.status_code == 200, ok.text
