# -*- coding: utf-8 -*-
"""第6步 空房照片: 上传/列表/标注/删除, 绑定户型版本; 新版本复制引用; 只读护栏。"""
import json
from pathlib import Path

from fastapi.testclient import TestClient

import main
from aigc.artifacts import ArtifactStore

import io

from PIL import Image


def _real_png(size=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 180, 160)).save(buf, format="PNG")
    return buf.getvalue()


_PNG = _real_png()


def _write_project(root: Path, project_id: str = "D") -> None:
    project = root / project_id
    project.mkdir(parents=True)
    repo_root = Path(__file__).resolve().parents[3]
    geometry = json.loads(
        (repo_root / "data" / "projects" / "D" / "geometry.json").read_text(encoding="utf-8")
    )
    (project / "geometry.json").write_text(
        json.dumps(geometry, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (project / "furniture.json").write_text("[]", encoding="utf-8")


def _client(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    _write_project(root)
    monkeypatch.setattr(main, "DATA_DIR", str(root))
    monkeypatch.setattr(main, "GEOM_READONLY", False)
    monkeypatch.setattr(main, "_uploads", ArtifactStore(str(tmp_path / "uploads")))
    return TestClient(main.app), root


def _upload(client, room_id=None):
    data = {}
    if room_id:
        data["room_id"] = room_id
    return client.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("room.png", _PNG, "image/png")},
        data=data,
    )


def test_upload_list_annotate_delete_photo(tmp_path, monkeypatch):
    client, root = _client(tmp_path, monkeypatch)

    created = _upload(client, room_id="r_live")
    assert created.status_code == 201, created.text
    photo = created.json()
    assert photo["room_id"] == "r_live"
    assert photo["url"].startswith("/api/uploads/D/empty/")
    # 归一化元数据 (审计 P0-2): 宽高/统一 JPEG/sha256。
    assert (photo["width"], photo["height"]) == (64, 48)
    assert photo["mime"] == "image/jpeg"
    assert len(photo["sha256"]) == 64

    listed = client.get("/api/projects/D/baselines/v1/photos")
    assert listed.status_code == 200
    assert [p["id"] for p in listed.json()] == [photo["id"]]

    # 文件确实可经 /api/uploads 取回
    fetched = client.get(photo["url"])
    assert fetched.status_code == 200

    patched = client.patch(
        f"/api/projects/D/baselines/v1/photos/{photo['id']}",
        json={"direction": "N", "note": "客厅朝北"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["direction"] == "N"

    deleted = client.delete(f"/api/projects/D/baselines/v1/photos/{photo['id']}")
    assert deleted.status_code == 200
    assert client.get("/api/projects/D/baselines/v1/photos").json() == []
    # 删除只移除引用, 文件保留 (历史成果不受影响)。
    assert client.get(photo["url"]).status_code == 200


def test_photo_writes_blocked_by_geom_readonly(tmp_path, monkeypatch):
    client, root = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "GEOM_READONLY", True)

    assert _upload(client).status_code == 403
    assert client.patch(
        "/api/projects/D/baselines/v1/photos/x", json={"note": "n"}
    ).status_code == 403
    assert client.delete("/api/projects/D/baselines/v1/photos/x").status_code == 403
    assert not (root / "D" / "baselines").exists()


def test_new_baseline_copies_photo_references(tmp_path, monkeypatch):
    client, root = _client(tmp_path, monkeypatch)
    photo = _upload(client, room_id="r_live").json()

    created = client.post("/api/projects/D/baselines", json={"source_version_id": "v1"})
    assert created.status_code == 201, created.text

    v2_photos = client.get("/api/projects/D/baselines/v2/photos").json()
    assert [p["id"] for p in v2_photos] == [photo["id"]]
    # v1/v2 引用独立: 删 v2 不影响 v1。
    client.delete(f"/api/projects/D/baselines/v2/photos/{photo['id']}")
    assert client.get("/api/projects/D/baselines/v1/photos").json() != []


def test_photo_writes_blocked_on_superseded_baseline(tmp_path, monkeypatch):
    client, root = _client(tmp_path, monkeypatch)
    _upload(client, room_id="r_live")
    client.post("/api/projects/D/baselines", json={"source_version_id": "v1"})
    assert client.post("/api/projects/D/baselines/v2/confirm").status_code == 200

    # v1 已 superseded: 照片写操作 409, 读仍可。
    resp = _upload(client)
    assert resp.status_code == 409
    assert client.get("/api/projects/D/baselines/v1/photos").status_code == 200


def test_photo_patch_unknown_id_404_and_bad_field_400(tmp_path, monkeypatch):
    client, _root = _client(tmp_path, monkeypatch)
    photo = _upload(client).json()

    assert client.patch(
        "/api/projects/D/baselines/v1/photos/nope", json={"note": "n"}
    ).status_code == 404
    assert client.patch(
        f"/api/projects/D/baselines/v1/photos/{photo['id']}", json={"room_id": 123}
    ).status_code == 400


def test_photo_quota_blocks_at_cap(tmp_path, monkeypatch):
    """审计 P2-2: 每户型版本照片配额 —— uploads 不再是无界磁盘增长向量。"""
    import baselines as baseline_store

    client, _root = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(baseline_store, "MAX_PHOTOS_PER_BASELINE", 2)

    assert _upload(client).status_code == 201
    assert _upload(client).status_code == 201
    blocked = _upload(client)
    assert blocked.status_code == 409
    assert "上限" in blocked.json()["error"]
