# -*- coding: utf-8 -*-
"""Baseline API routes: version creation, draft saving, validation, confirm gates."""
import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

import main


def _write_project(root: Path, project_id: str = "D") -> dict:
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
        json.dumps([{"t": "sofa", "room_id": "r_live"}], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return geometry


def _client(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    geometry = _write_project(root)
    monkeypatch.setattr(main, "DATA_DIR", str(root))
    monkeypatch.setattr(main, "GEOM_READONLY", False)
    return TestClient(main.app), root, geometry


def test_project_and_baselines_read_legacy_without_writing(tmp_path, monkeypatch):
    client, root, _geometry = _client(tmp_path, monkeypatch)

    project = client.get("/api/projects/D")
    baselines = client.get("/api/projects/D/baselines")
    geometry = client.get("/api/projects/D/baselines/v1/geometry")

    assert project.status_code == 200
    assert project.json()["current_baseline_version_id"] == "v1"
    assert baselines.status_code == 200
    assert baselines.json()[0]["id"] == "v1"
    assert baselines.json()[0]["status"] == "confirmed"
    assert geometry.status_code == 200
    assert not (root / "D" / "project.json").exists()
    assert not (root / "D" / "baselines").exists()


def test_create_draft_baseline_saves_only_draft_and_confirm_updates_pointer(tmp_path, monkeypatch):
    client, root, original = _client(tmp_path, monkeypatch)

    created = client.post("/api/projects/D/baselines", json={"source_version_id": "v1"})
    assert created.status_code == 201, created.text
    assert created.json()["id"] == "v2"
    assert created.json()["status"] == "draft"
    assert (root / "D" / "baselines" / "v2" / "geometry.json").exists()

    rejected = client.post(
        "/api/projects/D/baselines/v1/save-geometry",
        json=original,
    )
    assert rejected.status_code == 409

    edited = copy.deepcopy(original)
    edited["meta"]["name"] = "V2 edited"
    saved = client.post("/api/projects/D/baselines/v2/save-geometry", json=edited)
    assert saved.status_code == 200, saved.text
    assert saved.json()["ok"] is True
    assert json.loads((root / "D" / "geometry.json").read_text(encoding="utf-8"))["meta"].get(
        "name"
    ) != "V2 edited"

    confirmed = client.post("/api/projects/D/baselines/v2/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["project"]["current_baseline_version_id"] == "v2"
    assert json.loads((root / "D" / "geometry.json").read_text(encoding="utf-8"))["meta"][
        "name"
    ] == "V2 edited"
    v1_meta = json.loads((root / "D" / "baselines" / "v1" / "meta.json").read_text(encoding="utf-8"))
    v2_meta = json.loads((root / "D" / "baselines" / "v2" / "meta.json").read_text(encoding="utf-8"))
    assert v1_meta["status"] == "superseded"
    assert v2_meta["status"] == "confirmed"


def test_confirm_invalid_draft_does_not_change_current_pointer_or_root_geometry(tmp_path, monkeypatch):
    client, root, original = _client(tmp_path, monkeypatch)
    client.post("/api/projects/D/baselines", json={"source_version_id": "v1"})
    root_geometry_before = (root / "D" / "geometry.json").read_bytes()

    invalid = copy.deepcopy(original)
    invalid["rooms"] = []
    saved = client.post("/api/projects/D/baselines/v2/save-geometry", json=invalid)
    assert saved.status_code == 200
    assert saved.json()["ok"] is False

    # Simulate a corrupt draft that bypassed save validation; confirm must revalidate.
    (root / "D" / "baselines" / "v2" / "geometry.json").write_text(
        json.dumps(invalid, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    confirmed = client.post("/api/projects/D/baselines/v2/confirm")

    assert confirmed.status_code == 400
    project_meta = json.loads((root / "D" / "project.json").read_text(encoding="utf-8"))
    assert project_meta["current_baseline_version_id"] == "v1"
    assert (root / "D" / "geometry.json").read_bytes() == root_geometry_before
    v1_meta = json.loads((root / "D" / "baselines" / "v1" / "meta.json").read_text(encoding="utf-8"))
    v2_meta = json.loads((root / "D" / "baselines" / "v2" / "meta.json").read_text(encoding="utf-8"))
    assert v1_meta["status"] == "confirmed"
    assert v2_meta["status"] == "draft"


def test_legacy_save_geometry_still_updates_root_not_draft_baseline(tmp_path, monkeypatch):
    client, root, original = _client(tmp_path, monkeypatch)
    client.post("/api/projects/D/baselines", json={"source_version_id": "v1"})
    edited = copy.deepcopy(original)
    edited["meta"]["name"] = "legacy root edit"

    legacy = client.post("/api/projects/D/save-geometry", json=edited)

    assert legacy.status_code == 200, legacy.text
    assert json.loads((root / "D" / "geometry.json").read_text(encoding="utf-8"))["meta"][
        "name"
    ] == "legacy root edit"
    v2 = json.loads(
        (root / "D" / "baselines" / "v2" / "geometry.json").read_text(encoding="utf-8")
    )
    assert v2["meta"].get("name") != "legacy root edit"
