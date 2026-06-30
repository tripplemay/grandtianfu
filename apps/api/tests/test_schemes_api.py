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
        json={"name": "方案 B", "status": "confirmed", "source": "ai"},
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
