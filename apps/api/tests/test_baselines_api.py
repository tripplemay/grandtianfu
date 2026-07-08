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


# ---- 删除户型版本 (级联软删) ---- #


def _confirm_new_version(client, original, source, target, name):
    """从 source(当前已确认) 建 target 草稿, 存改名几何并确认 (target=当前, source=历史)。"""
    assert client.post(
        "/api/projects/D/baselines", json={"source_version_id": source}
    ).status_code == 201
    edited = copy.deepcopy(original)
    edited["meta"]["name"] = name
    assert client.post(f"/api/projects/D/baselines/{target}/save-geometry", json=edited).status_code == 200
    assert client.post(f"/api/projects/D/baselines/{target}/confirm").status_code == 200


def _make_multi_version(client, original):
    """建 v2 并确认 (v2=当前, v1=历史), 供删除历史版本的用例复用。"""
    _confirm_new_version(client, original, "v1", "v2", "V2")


def test_delete_current_confirmed_version_rejected_409(tmp_path, monkeypatch):
    client, root, original = _client(tmp_path, monkeypatch)
    _make_multi_version(client, original)  # v2 当前, v1 历史

    resp = client.delete("/api/projects/D/baselines/v2")

    assert resp.status_code == 409, resp.text
    assert (root / "D" / "baselines" / "v2").is_dir()
    project_meta = json.loads((root / "D" / "project.json").read_text(encoding="utf-8"))
    assert project_meta["current_baseline_version_id"] == "v2"


def test_delete_v1_always_rejected_even_when_superseded(tmp_path, monkeypatch):
    # v1 与根几何硬绑定 (唯一被合成兜底的版本): 即使已 superseded 也永不可删,
    # 否则下次写操作经 migrate 用根几何把 v1 复活成 confirmed, 破坏 confirmed 唯一性。
    client, root, original = _client(tmp_path, monkeypatch)
    _make_multi_version(client, original)  # v2 当前, v1 superseded

    resp = client.delete("/api/projects/D/baselines/v1")

    assert resp.status_code == 409, resp.text
    assert (root / "D" / "baselines" / "v1").is_dir()
    # 后续建版本不会出现两个 confirmed (v1 未被删故不会经 migrate 复活)。
    client.post("/api/projects/D/baselines", json={"source_version_id": "v2"})
    statuses = {b["id"]: b["status"] for b in client.get("/api/projects/D/baselines").json()}
    assert list(statuses.values()).count("confirmed") == 1


def test_delete_last_remaining_version_rejected_409(tmp_path, monkeypatch):
    # 迁移出 v1 但不建新版本: v1 是唯一版本 (且为当前/v1 保护), 删除必须 409。
    client, root, _original = _client(tmp_path, monkeypatch)
    client.post("/api/projects/D/baselines")  # 触发迁移, 落 v1 目录

    resp = client.delete("/api/projects/D/baselines/v1")

    assert resp.status_code == 409, resp.text
    assert (root / "D" / "baselines" / "v1").is_dir()


def test_delete_superseded_version_soft_deletes_and_keeps_pointer(tmp_path, monkeypatch):
    client, root, original = _client(tmp_path, monkeypatch)
    _make_multi_version(client, original)  # v2 当前, v1 历史
    _confirm_new_version(client, original, "v2", "v3", "V3")  # v3 当前, v2 superseded

    before_next = json.loads((root / "D" / "project.json").read_text(encoding="utf-8"))["next_baseline_version"]
    resp = client.delete("/api/projects/D/baselines/v2")

    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    # 软删: v2 目录移出, .trash 下留副本; 当前指针不动; next 不回退。
    assert not (root / "D" / "baselines" / "v2").exists()
    trash = list((root / "D" / "baselines" / ".trash").glob("v2-*"))
    assert len(trash) == 1 and trash[0].is_dir()
    project_meta = json.loads((root / "D" / "project.json").read_text(encoding="utf-8"))
    assert project_meta["current_baseline_version_id"] == "v3"
    assert project_meta["next_baseline_version"] == before_next
    # list 不再含 v2
    ids = sorted(b["id"] for b in client.get("/api/projects/D/baselines").json())
    assert ids == ["v1", "v3"]


def test_delete_draft_version_soft_deletes(tmp_path, monkeypatch):
    client, root, _original = _client(tmp_path, monkeypatch)
    assert client.post("/api/projects/D/baselines", json={"source_version_id": "v1"}).status_code == 201  # v2 draft

    resp = client.delete("/api/projects/D/baselines/v2")

    assert resp.status_code == 200, resp.text
    assert not (root / "D" / "baselines" / "v2").exists()
    assert list((root / "D" / "baselines" / ".trash").glob("v2-*"))


def test_delete_version_cascades_bound_schemes_to_trash(tmp_path, monkeypatch):
    client, root, original = _client(tmp_path, monkeypatch)
    _make_multi_version(client, original)  # v2 当前, v1 历史
    # 方案绑定当前版本 v2
    assert client.post(
        "/api/projects/D/schemes",
        json={"id": "scheme_manual_001", "name": "方案 A", "source": "manual"},
    ).status_code == 201
    # 建 v3 并确认 -> v3 当前, v2 变历史, 方案仍绑 v2
    assert client.post("/api/projects/D/baselines", json={"source_version_id": "v2"}).status_code == 201
    edited = copy.deepcopy(original)
    edited["meta"]["name"] = "V3"
    assert client.post("/api/projects/D/baselines/v3/save-geometry", json=edited).status_code == 200
    assert client.post("/api/projects/D/baselines/v3/confirm").status_code == 200

    resp = client.delete("/api/projects/D/baselines/v2")

    assert resp.status_code == 200, resp.text
    assert resp.json()["schemes_trashed"] == ["scheme_manual_001"]
    # 版本目录与绑定方案都进各自 .trash, 方案原位消失
    assert not (root / "D" / "baselines" / "v2").exists()
    assert not (root / "D" / "schemes" / "scheme_manual_001").exists()
    assert list((root / "D" / "schemes" / ".trash").glob("scheme_manual_001-*"))
    # default 方案不被级联 (仍在原位)
    assert (root / "D" / "schemes" / "default").exists() or not (
        root / "D" / "schemes" / "default"
    ).exists()  # default 视迁移而定, 只断言未误进 .trash
    assert not list((root / "D" / "schemes" / ".trash").glob("default-*"))


def test_delete_version_repins_bound_default_to_current(tmp_path, monkeypatch):
    # default 若 pin 到被删版本 → 重 pin 到 current (不留悬空导致渲染读错几何/500)。
    client, root, original = _client(tmp_path, monkeypatch)
    _make_multi_version(client, original)  # v2 当前, v1 历史
    assert client.get("/api/projects/D/schemes").status_code == 200  # materialize default
    default_meta_path = root / "D" / "schemes" / "default" / "meta.json"
    # 模拟 default pin 到将被删的 v2 (fresh-project 路径可自然产生此态; 迁移路径 pin v1)。
    dm = json.loads(default_meta_path.read_text(encoding="utf-8"))
    dm["baseline_version_id"] = "v2"
    default_meta_path.write_text(json.dumps(dm, ensure_ascii=False, indent=2), encoding="utf-8")
    _confirm_new_version(client, original, "v2", "v3", "V3")  # v3 当前, v2 superseded

    resp = client.delete("/api/projects/D/baselines/v2")

    assert resp.status_code == 200, resp.text
    # default 未被级联进 .trash, 而是重 pin 到 current(v3)。
    assert (root / "D" / "schemes" / "default").is_dir()
    assert not list((root / "D" / "schemes" / ".trash").glob("default-*"))
    repinned = json.loads(default_meta_path.read_text(encoding="utf-8"))
    assert repinned["baseline_version_id"] == "v3"


def test_delete_version_rejected_under_geom_readonly(tmp_path, monkeypatch):
    client, root, original = _client(tmp_path, monkeypatch)
    _make_multi_version(client, original)
    monkeypatch.setattr(main, "GEOM_READONLY", True)

    resp = client.delete("/api/projects/D/baselines/v1")

    assert resp.status_code == 403, resp.text
    assert (root / "D" / "baselines" / "v1").is_dir()


def test_delete_nonexistent_version_404(tmp_path, monkeypatch):
    client, _root, original = _client(tmp_path, monkeypatch)
    _make_multi_version(client, original)

    resp = client.delete("/api/projects/D/baselines/v9")

    assert resp.status_code == 404, resp.text


# ---- 家具下沉基线 (Phase A: 家具随户型版本锁定) ---- #

_ROOT_FURN = [{"t": "sofa", "room_id": "r_live"}]  # 与 _write_project 写入的根 furniture 一致


def test_baseline_v1_furniture_falls_back_to_root(tmp_path, monkeypatch):
    # 遗留项目未物化 v1 furniture 时, 读回退到根 furniture.json (= 初始方案家具)。
    client, root, _original = _client(tmp_path, monkeypatch)
    r = client.get("/api/projects/D/baselines/v1/furniture")
    assert r.status_code == 200, r.text
    assert r.json() == _ROOT_FURN
    assert not (root / "D" / "baselines" / "v1" / "furniture.json").exists()  # 未物化


def test_migration_seeds_v1_furniture_and_create_copies_to_new_version(tmp_path, monkeypatch):
    client, root, _original = _client(tmp_path, monkeypatch)
    # 建 v2 触发迁移: v1 furniture 物化 = 根; v2 草稿从 v1 拷贝家具。
    assert client.post("/api/projects/D/baselines", json={"source_version_id": "v1"}).status_code == 201

    v1f = root / "D" / "baselines" / "v1" / "furniture.json"
    assert v1f.is_file()
    assert json.loads(v1f.read_text("utf-8")) == _ROOT_FURN
    v2f = root / "D" / "baselines" / "v2" / "furniture.json"
    assert v2f.is_file()
    assert client.get("/api/projects/D/baselines/v2/furniture").json() == _ROOT_FURN


def test_save_baseline_furniture_draft_only_and_root_unchanged(tmp_path, monkeypatch):
    client, root, _original = _client(tmp_path, monkeypatch)
    client.post("/api/projects/D/baselines", json={"source_version_id": "v1"})  # v2 draft
    new_furn = [
        {"t": "sofa", "room_id": "r_live", "dx": 10, "dy": 10},
        {"t": "plant", "room_id": "r_live", "dx": 20, "dy": 20},
    ]

    ok = client.post("/api/projects/D/baselines/v2/save-furniture", json=new_furn)
    assert ok.status_code == 200, ok.text
    assert ok.json()["ok"] is True and ok.json()["count"] == 2
    assert client.get("/api/projects/D/baselines/v2/furniture").json() == new_furn

    # v1 已确认 -> 拒写; 根 furniture.json 从不被基线保存改动 (golden 字节安全)。
    locked = client.post("/api/projects/D/baselines/v1/save-furniture", json=new_furn)
    assert locked.status_code == 409, locked.text
    assert json.loads((root / "D" / "furniture.json").read_text("utf-8")) == _ROOT_FURN


def test_save_baseline_furniture_rejected_under_geom_readonly(tmp_path, monkeypatch):
    client, _root, _original = _client(tmp_path, monkeypatch)
    client.post("/api/projects/D/baselines", json={"source_version_id": "v1"})
    monkeypatch.setattr(main, "GEOM_READONLY", True)
    r = client.post("/api/projects/D/baselines/v2/save-furniture", json=[{"t": "sofa", "room_id": "r_live"}])
    assert r.status_code == 403, r.text


def test_save_baseline_furniture_rejects_non_array(tmp_path, monkeypatch):
    client, _root, _original = _client(tmp_path, monkeypatch)
    client.post("/api/projects/D/baselines", json={"source_version_id": "v1"})
    r = client.post("/api/projects/D/baselines/v2/save-furniture", json={"not": "array"})
    assert r.status_code == 422, r.text  # FastAPI list=Body 校验 (同 save-geometry dict=Body)


def test_save_baseline_furniture_rejects_malformed_items(tmp_path, monkeypatch):
    # 逐件写边界护栏 (与方案端点一致): 缺坐标/room_id 的坏件在写入口 400, 不落盘。
    client, root, _original = _client(tmp_path, monkeypatch)
    client.post("/api/projects/D/baselines", json={"source_version_id": "v1"})  # v2 draft
    bad = [{"t": "sofa", "room_id": "r_live"}]  # 缺 dx/dy 或 dcx/dcy
    r = client.post("/api/projects/D/baselines/v2/save-furniture", json=bad)
    assert r.status_code == 400, r.text
    # v2 家具仍是从 v1 拷来的原样 (坏件未落盘)
    assert client.get("/api/projects/D/baselines/v2/furniture").json() == _ROOT_FURN


def test_baseline_furniture_root_fallback_for_unmaterialized_version(tmp_path, monkeypatch):
    # 复现用户报告: 从 Phase-A-前创建(无 furniture.json)的旧户型版本复制出的新版本家具为空。
    # 修复后: 缺 furniture.json 的版本读回退根; 复制时也从根拷, 新版本不为空。
    client, root, _original = _client(tmp_path, monkeypatch)
    _make_multi_version(client, _original)  # v2 当前确认 (含 furniture), v1 历史
    # 模拟旧版本: 抹掉 v2 的 furniture.json。
    (root / "D" / "baselines" / "v2" / "furniture.json").unlink()
    # v2 读不再空, 回退根 (= 初始方案家具)。
    assert client.get("/api/projects/D/baselines/v2/furniture").json() == _ROOT_FURN
    # 从 v2(当前) 复制 v3 -> v3 含家具 (从根拷), 且已物化。
    assert client.post(
        "/api/projects/D/baselines", json={"source_version_id": "v2"}
    ).status_code == 201
    v3 = client.get("/api/projects/D/baselines/v3/furniture")
    assert v3.status_code == 200 and v3.json() == _ROOT_FURN
    assert (root / "D" / "baselines" / "v3" / "furniture.json").is_file()
