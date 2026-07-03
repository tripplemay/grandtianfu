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
    # 契约统一 (审计 P2): 校验失败 400 (与 legacy 端点一致), body 仍带 ok/errors。
    assert saved.status_code == 400
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


def test_legacy_save_geometry_rejected_after_baseline_migration(tmp_path, monkeypatch):
    client, root, original = _client(tmp_path, monkeypatch)
    client.post("/api/projects/D/baselines", json={"source_version_id": "v1"})
    root_geometry_before = (root / "D" / "geometry.json").read_bytes()
    edited = copy.deepcopy(original)
    edited["meta"]["name"] = "legacy root edit"

    legacy = client.post("/api/projects/D/save-geometry", json=edited)

    assert legacy.status_code == 409, legacy.text
    assert (root / "D" / "geometry.json").read_bytes() == root_geometry_before
    v2 = json.loads(
        (root / "D" / "baselines" / "v2" / "geometry.json").read_text(encoding="utf-8")
    )
    assert v2["meta"].get("name") != "legacy root edit"


def test_validate_baseline_rejected_under_geom_readonly(tmp_path, monkeypatch):
    # P0-2: validate 会写 validation.json 并可能触发首次迁移落盘, 只读会话必须 403 且不污染活数据。
    client, root, _original = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "GEOM_READONLY", True)

    res = client.post("/api/projects/D/baselines/v1/validate")

    assert res.status_code == 403, res.text
    assert not (root / "D" / "project.json").exists()
    assert not (root / "D" / "baselines").exists()


def test_confirm_idempotent_and_self_heals_two_confirmed(tmp_path, monkeypatch):
    # P0-3: 重复确认当前版本幂等; 残留的第二个 confirmed(崩溃遗留)在下次确认时被自愈降级。
    client, root, original = _client(tmp_path, monkeypatch)
    client.post("/api/projects/D/baselines", json={"source_version_id": "v1"})
    edited = copy.deepcopy(original)
    edited["meta"]["name"] = "V2 edited"
    client.post("/api/projects/D/baselines/v2/save-geometry", json=edited)
    assert client.post("/api/projects/D/baselines/v2/confirm").status_code == 200

    again = client.post("/api/projects/D/baselines/v2/confirm")
    assert again.status_code == 200, again.text
    assert again.json()["project"]["current_baseline_version_id"] == "v2"
    assert again.json()["baseline"]["status"] == "confirmed"

    v1_path = root / "D" / "baselines" / "v1" / "meta.json"
    v1_meta = json.loads(v1_path.read_text(encoding="utf-8"))
    v1_meta["status"] = "confirmed"  # 模拟崩溃残留的第二个 confirmed
    v1_path.write_text(json.dumps(v1_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    client.post("/api/projects/D/baselines/v2/confirm")
    healed = json.loads(v1_path.read_text(encoding="utf-8"))
    assert healed["status"] == "superseded"


def test_confirm_recovers_from_partial_commit(tmp_path, monkeypatch):
    # P0-3: 模拟 confirm 在「目标已 confirmed、指针未切」之间崩溃, 重试应把指针切到目标并降级旧版本。
    client, root, original = _client(tmp_path, monkeypatch)
    client.post("/api/projects/D/baselines", json={"source_version_id": "v1"})
    edited = copy.deepcopy(original)
    edited["meta"]["name"] = "V2 edited"
    client.post("/api/projects/D/baselines/v2/save-geometry", json=edited)

    v2_path = root / "D" / "baselines" / "v2" / "meta.json"
    v2_meta = json.loads(v2_path.read_text(encoding="utf-8"))
    v2_meta["status"] = "confirmed"  # 步1完成, 指针(v1)未切
    v2_path.write_text(json.dumps(v2_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    recovered = client.post("/api/projects/D/baselines/v2/confirm")

    assert recovered.status_code == 200, recovered.text
    project_meta = json.loads((root / "D" / "project.json").read_text(encoding="utf-8"))
    assert project_meta["current_baseline_version_id"] == "v2"
    v1_meta = json.loads((root / "D" / "baselines" / "v1" / "meta.json").read_text(encoding="utf-8"))
    assert v1_meta["status"] == "superseded"
    assert json.loads((root / "D" / "geometry.json").read_text(encoding="utf-8"))["meta"][
        "name"
    ] == "V2 edited"


def test_legacy_save_geometry_rejected_when_current_points_to_superseded(tmp_path, monkeypatch):
    # P0-3: 修复 legacy 门禁在 current 指向 superseded(confirm 崩溃楔死)时失效, 根几何被旧接口覆盖的漏洞。
    client, root, original = _client(tmp_path, monkeypatch)
    client.post("/api/projects/D/baselines", json={"source_version_id": "v1"})
    v1_path = root / "D" / "baselines" / "v1" / "meta.json"
    v1_meta = json.loads(v1_path.read_text(encoding="utf-8"))
    v1_meta["status"] = "superseded"  # 指针仍指 v1, 但 v1 已被降级 → 旧门禁会放行
    v1_path.write_text(json.dumps(v1_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    root_before = (root / "D" / "geometry.json").read_bytes()

    edited = copy.deepcopy(original)
    edited["meta"]["name"] = "legacy overwrite via hole"
    res = client.post("/api/projects/D/save-geometry", json=edited)

    assert res.status_code == 409, res.text
    assert (root / "D" / "geometry.json").read_bytes() == root_before


def test_new_project_starts_with_v1_draft_and_blocks_schemes_until_confirmed(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    monkeypatch.setattr(main, "DATA_DIR", str(root))
    monkeypatch.setattr(main, "GEOM_READONLY", False)
    client = TestClient(main.app)

    created = client.post("/api/projects", json={"id": "N", "name": "新项目"})
    assert created.status_code == 201, created.text
    project = client.get("/api/projects/N").json()
    baselines = client.get("/api/projects/N/baselines").json()
    assert project["current_baseline_version_id"] is None
    assert baselines[0]["id"] == "v1"
    assert baselines[0]["status"] == "draft"
    draft_geometry = client.get("/api/projects/N/baselines/v1/geometry").json()
    assert client.post("/api/projects/N/save-geometry", json=draft_geometry).status_code == 409
    assert client.post(
        "/api/projects/N/schemes",
        json={"id": "scheme_manual_001", "name": "方案 A", "source": "manual"},
    ).status_code == 409

    confirmed = client.post("/api/projects/N/baselines/v1/confirm")
    assert confirmed.status_code == 200, confirmed.text
    ok = client.post(
        "/api/projects/N/schemes",
        json={"id": "scheme_manual_001", "name": "方案 A", "source": "manual"},
    )
    assert ok.status_code == 201, ok.text
