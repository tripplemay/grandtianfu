# -*- coding: utf-8 -*-
"""render-note-b1 F001 — Evaluator 独立对抗测试 (非 generator 编写)。

覆盖 generator 主测未显式验证的边界:
- 部分写入防护: {status + 超长 comment} 一次请求, comment 非法 -> 400 且 status 未被写 (先纯校验)。
- 双字段 + render 缺失 -> 404, 两账本均无写入。
- 字段保全: 写 comment 不得抹掉同记录既有 status/feedback_reason/其他字段, 也不得丢失同列表其它记录。
- detail=1 详情读侧同样透出 comment。
- 幂等清除: 已 None 再清仍 200/None。
- normalize_render_comment 纯函数边界 (直接单测, 无 I/O)。
全部指向 tmp, 不碰真实 data/artifacts。
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


def _seed(root, scheme_id, rid, **extra):
    scheme_store.append_render(
        str(root),
        "D",
        scheme_id,
        {
            "id": rid,
            "url": f"/api/artifacts/{rid}.png",
            "mode": "real-photo",
            "scheme_id": scheme_id,
            "created_at": "2026-07-16T00:00:00Z",
            **extra,
        },
    )


def _patch(client, rid, body, scheme_id="s1"):
    return client.patch(f"/api/projects/D/schemes/{scheme_id}/renders/{rid}", json=body)


def _listed(client, scheme_id="s1", detail=0):
    return client.get(
        f"/api/projects/D/schemes/{scheme_id}/renders?detail={detail}"
    ).json()


def test_partial_write_guard_invalid_comment_does_not_write_status(client):
    """一次请求同时带 status + 超长 comment: 必须整请求 400, status 不得被落盘 (先纯校验 comment)。"""
    c, root, _ = client
    _make_scheme(c)
    _seed(root, "s1", "r1")  # 初始无 status
    r = _patch(c, "r1", {"status": "accepted", "comment": "字" * 2001})
    assert r.status_code == 400, r.text
    rec = _listed(c)[0]
    # status 未被写 (缺省), comment 未被写
    assert rec.get("status") in (None, "draft") or "status" not in rec
    assert rec.get("comment") is None


def test_partial_write_guard_invalid_type_does_not_write_status(client):
    c, root, _ = client
    _make_scheme(c)
    _seed(root, "s1", "r1")
    r = _patch(c, "r1", {"status": "accepted", "comment": 123})
    assert r.status_code == 400, r.text
    rec = _listed(c)[0]
    assert rec.get("status") in (None, "draft") or "status" not in rec
    assert rec.get("comment") is None


def test_both_fields_missing_render_404_no_write(client):
    c, root, legacy = client
    _make_scheme(c)
    _seed(root, "s1", "r1")
    r = _patch(c, "nope", {"status": "accepted", "comment": "x"})
    assert r.status_code == 404, r.text
    # 既有 r1 未受影响
    rec = _listed(c)[0]
    assert rec.get("comment") is None
    assert rec.get("status") in (None, "draft") or "status" not in rec


def test_comment_preserves_other_fields_and_records(client):
    """写 comment 不得抹掉同记录既有字段, 也不得丢失列表其它记录 (immutable dict 复制 + 全列表回写)。"""
    c, root, _ = client
    _make_scheme(c)
    _seed(root, "s1", "r_old", model="gpt-image-2", low_accuracy=True)
    _seed(root, "s1", "r_new", model="gpt-image-2")
    # 先给 r_old 打 status + feedback_reason
    assert _patch(c, "r_old", {"status": "rejected", "feedback_reason": "structure"}).status_code == 200
    # 再给 r_old 写 comment
    r = _patch(c, "r_old", {"comment": "沙发偏大"})
    assert r.status_code == 200, r.text
    body = r.json()
    # 同记录其它字段全保全
    assert body["status"] == "rejected"
    assert body["feedback_reason"] == "structure"
    assert body["model"] == "gpt-image-2"
    assert body["low_accuracy"] is True
    assert body["comment"] == "沙发偏大"
    # 列表仍有两条 (r_new 未丢)
    listed = _listed(c)
    ids = {x["id"] for x in listed}
    assert ids == {"r_old", "r_new"}


def test_comment_visible_detail_1(client):
    c, root, _ = client
    _make_scheme(c)
    _seed(root, "s1", "r1")
    assert _patch(c, "r1", {"comment": "详情读侧也应有"}).status_code == 200
    assert _listed(c, detail=1)[0]["comment"] == "详情读侧也应有"


def test_idempotent_clear_when_already_none(client):
    c, root, _ = client
    _make_scheme(c)
    _seed(root, "s1", "r1")
    # 从未写过 comment, 直接清
    r = _patch(c, "r1", {"comment": ""})
    assert r.status_code == 200
    assert r.json()["comment"] is None
    r2 = _patch(c, "r1", {"comment": None})
    assert r2.status_code == 200
    assert r2.json()["comment"] is None


def test_normalize_render_comment_pure_boundaries():
    n = scheme_store.normalize_render_comment
    assert n(None) is None
    assert n("") is None
    assert n("   \n\t ") is None
    assert n("  hi  ") == "hi"
    assert n("x" * 2000) == "x" * 2000
    with pytest.raises(scheme_store.SchemeValidationError):
        n("x" * 2001)
    with pytest.raises(scheme_store.SchemeValidationError):
        n(123)  # type: ignore[arg-type]
    with pytest.raises(scheme_store.SchemeValidationError):
        n(["list"])  # type: ignore[arg-type]
