# -*- coding: utf-8 -*-
"""F — 共享后端基座: render 记录验收/确认状态 (status) + PATCH 路由 + _summary 按 mode 计数。

验收 (real-photo) 与轴测确认 (axon-photoreal) 共用记录上的 status 字段 (draft/accepted/
rejected), 读时默认 draft, 无迁移。stepper 的第 4/6/7 步 done 判定读 _summary 的三个计数。
"""
import json
from pathlib import Path

from fastapi.testclient import TestClient

import main
import schemes as scheme_store


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


def _make_scheme(client, scheme_id="s1"):
    res = client.post(
        "/api/projects/D/schemes",
        json={"id": scheme_id, "name": "A", "source": "manual"},
    )
    assert res.status_code == 201, res.text


def _seed_render(root, scheme_id, rid, mode, **extra):
    record = {
        "id": rid,
        "url": f"/api/artifacts/{rid}.png",
        "mode": mode,
        "scheme_id": scheme_id,
        "created_at": "2026-07-08T00:00:00Z",
        **extra,
    }
    scheme_store.append_render(str(root), "D", scheme_id, record)


def test_patch_render_status_accept_and_reject(tmp_path, monkeypatch):
    client, root = _client(tmp_path, monkeypatch)
    _make_scheme(client)
    _seed_render(root, "s1", "r_real_1", "real-photo")

    accepted = client.patch(
        "/api/projects/D/schemes/s1/renders/r_real_1", json={"status": "accepted"}
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"

    rejected = client.patch(
        "/api/projects/D/schemes/s1/renders/r_real_1",
        json={"status": "rejected", "feedback_reason": "structure"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["feedback_reason"] == "structure"

    # 持久化: 重新读列表应看到 rejected 状态。
    listed = client.get("/api/projects/D/schemes/s1/renders").json()
    assert listed[0]["status"] == "rejected"


def test_patch_render_status_invalid_and_missing(tmp_path, monkeypatch):
    client, root = _client(tmp_path, monkeypatch)
    _make_scheme(client)
    _seed_render(root, "s1", "r_real_1", "real-photo")

    bad = client.patch(
        "/api/projects/D/schemes/s1/renders/r_real_1", json={"status": "bogus"}
    )
    assert bad.status_code == 400, bad.text

    missing = client.patch(
        "/api/projects/D/schemes/s1/renders/does_not_exist", json={"status": "accepted"}
    )
    assert missing.status_code == 404, missing.text


def test_summary_render_counts_by_mode(tmp_path, monkeypatch):
    client, root = _client(tmp_path, monkeypatch)
    _make_scheme(client)
    _seed_render(root, "s1", "a1", "axon-photoreal")
    _seed_render(root, "s1", "r1", "real-photo")
    _seed_render(root, "s1", "r2", "real-photo")

    listed = client.get("/api/projects/D/schemes").json()
    summary = next(x for x in listed if x["id"] == "s1")
    assert summary["axon_render_count"] == 1
    assert summary["real_render_count"] == 2
    assert summary["has_accepted_real"] is False

    client.patch("/api/projects/D/schemes/s1/renders/r1", json={"status": "accepted"})
    listed2 = client.get("/api/projects/D/schemes").json()
    summary2 = next(x for x in listed2 if x["id"] == "s1")
    assert summary2["has_accepted_real"] is True


def test_summary_has_confirmed_axon(tmp_path, monkeypatch):
    """B4: 轴测出图被确认 (accepted) -> _summary.has_confirmed_axon=True。"""
    client, root = _client(tmp_path, monkeypatch)
    _make_scheme(client)
    _seed_render(root, "s1", "a1", "axon-photoreal")

    before = next(
        x for x in client.get("/api/projects/D/schemes").json() if x["id"] == "s1"
    )
    assert before["has_confirmed_axon"] is False

    client.patch("/api/projects/D/schemes/s1/renders/a1", json={"status": "accepted"})
    after = next(
        x for x in client.get("/api/projects/D/schemes").json() if x["id"] == "s1"
    )
    assert after["has_confirmed_axon"] is True
