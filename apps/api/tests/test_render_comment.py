# -*- coding: utf-8 -*-
"""render-note-b1 F001 — 效果图记录单条可编辑备注 (comment)。

PATCH /schemes/{scheme_id}/renders/{render_id} 偏更新: comment 与验收 status/feedback_reason
正交独立。set/改/清(空串→None)/404/非法类型 400/超长 400/default 双账本回退/GET 透出。
既有 status 路径零回归由 test_render_status.py 守护。产物全指向 tmp。
"""
import json
from pathlib import Path

import main
import pytest
import schemes as scheme_store
from aigc.records import RenderLog
from fastapi.testclient import TestClient


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


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    _write_project(root)
    # legacy 账本指向 tmp, 绝不碰真实 artifacts_dir。
    legacy = RenderLog(str(tmp_path / "art"))
    monkeypatch.setattr(main, "DATA_DIR", str(root))
    monkeypatch.setattr(main, "_renders", legacy)
    return TestClient(main.app), root, legacy


def _make_scheme(client, scheme_id="s1"):
    res = client.post(
        "/api/projects/D/schemes",
        json={"id": scheme_id, "name": "A", "source": "manual"},
    )
    assert res.status_code == 201, res.text


def _seed_render(root, scheme_id, rid, mode="real-photo", **extra):
    record = {
        "id": rid,
        "url": f"/api/artifacts/{rid}.png",
        "mode": mode,
        "scheme_id": scheme_id,
        "created_at": "2026-07-16T00:00:00Z",
        **extra,
    }
    scheme_store.append_render(str(root), "D", scheme_id, record)


def _patch(client, rid, body, scheme_id="s1"):
    return client.patch(f"/api/projects/D/schemes/{scheme_id}/renders/{rid}", json=body)


def _listed(client, scheme_id="s1"):
    return client.get(f"/api/projects/D/schemes/{scheme_id}/renders").json()


def test_comment_set_update_clear(client):
    c, root, _ = client
    _make_scheme(c)
    _seed_render(root, "s1", "r1")

    # set
    r = _patch(c, "r1", {"comment": "沙发偏大，窗帘要落地"})
    assert r.status_code == 200, r.text
    assert r.json()["comment"] == "沙发偏大，窗帘要落地"
    # 持久化 + detail=0 列表读侧透出 (非 heavy key, 不被 _shape 剥离)
    assert _listed(c)[0]["comment"] == "沙发偏大，窗帘要落地"

    # update (覆盖)
    r = _patch(c, "r1", {"comment": "改好了，这版沙发合适"})
    assert r.status_code == 200
    assert r.json()["comment"] == "改好了，这版沙发合适"

    # clear via 空串 -> None
    r = _patch(c, "r1", {"comment": ""})
    assert r.status_code == 200
    assert r.json()["comment"] is None
    assert _listed(c)[0]["comment"] is None

    # 纯空白 strip -> None
    _patch(c, "r1", {"comment": "有内容"})
    r = _patch(c, "r1", {"comment": "   \n  "})
    assert r.status_code == 200
    assert r.json()["comment"] is None

    # clear via null
    _patch(c, "r1", {"comment": "再写一句"})
    r = _patch(c, "r1", {"comment": None})
    assert r.status_code == 200
    assert r.json()["comment"] is None


def test_comment_invalid_type_400(client):
    c, root, _ = client
    _make_scheme(c)
    _seed_render(root, "s1", "r1")
    r = _patch(c, "r1", {"comment": 123})
    assert r.status_code == 400, r.text
    # 未写入: 记录仍无 comment
    assert _listed(c)[0].get("comment") is None


def test_comment_too_long_400(client):
    c, root, _ = client
    _make_scheme(c)
    _seed_render(root, "s1", "r1")
    r = _patch(c, "r1", {"comment": "字" * 2001})
    assert r.status_code == 400, r.text
    # 边界: 恰好 2000 合法
    ok = _patch(c, "r1", {"comment": "字" * 2000})
    assert ok.status_code == 200
    assert len(ok.json()["comment"]) == 2000


def test_comment_missing_render_404(client):
    c, root, _ = client
    _make_scheme(c)
    _seed_render(root, "s1", "r1")
    r = _patch(c, "does_not_exist", {"comment": "x"})
    assert r.status_code == 404, r.text


def test_patch_empty_payload_400(client):
    c, root, _ = client
    _make_scheme(c)
    _seed_render(root, "s1", "r1")
    r = _patch(c, "r1", {})
    assert r.status_code == 400, r.text


def test_comment_orthogonal_to_status(client):
    c, root, _ = client
    _make_scheme(c)
    _seed_render(root, "s1", "r1")

    # 先 status, 再 comment: 两者共存互不覆盖
    assert _patch(c, "r1", {"status": "accepted"}).status_code == 200
    assert _patch(c, "r1", {"comment": "细节很好"}).status_code == 200
    rec = _listed(c)[0]
    assert rec["status"] == "accepted"
    assert rec["comment"] == "细节很好"

    # 同一请求同时改 status + comment
    r = _patch(c, "r1", {"status": "rejected", "feedback_reason": "structure", "comment": "重来"})
    assert r.status_code == 200, r.text
    rec = _listed(c)[0]
    assert rec["status"] == "rejected"
    assert rec["feedback_reason"] == "structure"
    assert rec["comment"] == "重来"


def test_comment_default_legacy_ledger(client):
    """default 老出图仅在 legacy 账本 (方案级 renders.json 无) -> 写备注回退 legacy。"""
    c, root, legacy = client
    rec = {
        "id": "legacy_r1",
        "url": "/api/artifacts/legacy_r1.png",
        "mode": "real-photo",
        "scheme_id": "default",
    }
    legacy.append("D", rec)  # 仅 legacy, 不 seed 方案级 default renders.json

    r = c.patch(
        "/api/projects/D/schemes/default/renders/legacy_r1", json={"comment": "老图留言"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["comment"] == "老图留言"
    # legacy 账本落盘含 comment
    persisted = legacy.list("D")
    assert persisted[0]["comment"] == "老图留言"
