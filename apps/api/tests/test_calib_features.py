# -*- coding: utf-8 -*-
"""calib-cure-b1 F008: 特征点池派生 + 共面 PnP 求解 + points 模式端点。

特征点范式: 点从模型上拿 (自带世界坐标), 对应关系由构造保证正确; ≥4 点冗余使粗差
表现为大残差被 assess 硬门拦截 —— 消灭专家模式 2 锚点的静默吸收空间 (case A)。
"""

from pathlib import Path

import main
import numpy as np
import pytest
from aigc import calib_features, calib_heal, perspective
from floorplan_core import geometry as fp_geometry
from test_calibration_quality import _synthetic_cam
from test_render_real_geometry import _stub_accept, _upload_photo, _wait

_CAL = "/api/projects/D/baselines/v1/photos/{pid}/calibration"

# 与合成相机 (缺陷核查实验一同款) 视野匹配、均过 2% 边距的 5 个地面特征点 (数值预验证)。
_PNP_WORLDS = (
    (12150.0, 14100.0),
    (12150.0, 9500.0),
    (10000.0, 14100.0),
    (9500.0, 10500.0),
    (8800.0, 13000.0),
)


def _pnp_points(project, shift_px=0.0, n=5):
    return [
        {"world": [x, y, 0], "px": [project((x, y, 0))[0] + shift_px, project((x, y, 0))[1]]}
        for x, y in _PNP_WORLDS[:n]
    ]


def _seed_geometry():
    return fp_geometry.load("data/projects/D/geometry.json")


# ---- 特征点池派生 -----------------------------------------------------------------


def test_derive_features_merge_members_and_door_jambs():
    G = _seed_geometry()
    feats, members = calib_features.derive_features(G, "r_foyer")
    assert members == ["r_foyer", "r_live"]
    d02 = next(op for op in G["openings"] if op.get("id") == "d02")
    wall = d02["wall"]
    mm = G["meta"]["mm_per_px"]
    expected = {
        (wall["at"] * mm, wall["span"][0] * mm),
        (wall["at"] * mm, wall["span"][1] * mm),
    }
    jambs = {
        (f["world"][0], f["world"][1])
        for f in feats
        if f["kind"] == "door_jamb" and f["id"].startswith("door:d02")
    }
    assert jambs == expected  # 门框竖边×地面交点世界坐标精确 (z=0 无需高度数据)
    # F002: 地面 kind z=0; 异面 kind z>0 (ceiling_corner=2700 / door_head=2050 / window_head=2700)。
    ground_kinds = {"wall_corner", "door_jamb", "window_floor"}
    assert all(f["world"][2] == 0.0 for f in feats if f["kind"] in ground_kinds)
    assert all(f["world"][2] > 0.0 for f in feats if f["kind"] not in ground_kinds)
    # 每个门框地面交点必有同 (x,y) 的门顶点 (z=_DOOR_HEAD_MM)。
    heads = {
        (f["world"][0], f["world"][1], f["world"][2])
        for f in feats
        if f["kind"] == "door_head" and f["id"].startswith("doorhead:d02")
    }
    assert heads == {(w[0], w[1], calib_features._DOOR_HEAD_MM) for w in expected}
    assert [f["id"] for f in feats] == sorted(f["id"] for f in feats)  # id 稳定有序


def test_derive_features_drops_shared_open_boundary_corners():
    """跨成员重复坐标 = 开放边界虚拟角 (f4d 病灶: 门厅虚拟角只能瞎猜), 双方剔除。"""
    G = {
        "meta": {"mm_per_px": 10},
        "rooms": [
            {"id": "a", "rect": [0, 0, 100, 100], "merge": "m", "label": {"zh": "甲"}},
            {"id": "b", "rect": [0, 100, 100, 100], "merge": "m", "label": {"zh": "乙"}},
        ],
        "openings": [],
    }
    feats, members = calib_features.derive_features(G, "a")
    assert members == ["a", "b"]
    worlds = {(f["world"][0], f["world"][1]) for f in feats}
    # 开放边界 y=100 上的两个共享角 (0,1000)/(1000,1000) 被剔除, 余 4 个外圈实体角。
    assert (0.0, 1000.0) not in worlds and (1000.0, 1000.0) not in worlds
    assert worlds == {(0.0, 0.0), (1000.0, 0.0), (0.0, 2000.0), (1000.0, 2000.0)}


def test_derive_features_window_only_full_type():
    G = {
        "meta": {"mm_per_px": 10},
        "rooms": [{"id": "a", "rect": [0, 0, 100, 100], "label": {"zh": "甲"}}],
        "openings": [
            {"kind": "window", "wtype": "full", "id": "w1",
             "wall": {"axis": "h", "at": 0, "span": [20, 60]}},
            {"kind": "window", "wtype": "normal", "id": "w2",
             "wall": {"axis": "h", "at": 100, "span": [20, 60]}},
        ],
    }
    feats, _members = calib_features.derive_features(G, "a")
    kinds = {f["id"]: f["kind"] for f in feats if f["kind"] == "window_floor"}
    assert set(kinds) == {"window:w1:a", "window:w1:b"}  # normal 窗台高度无数据, 不出点
    # F002: 落地窗(full)出窗顶点(z=2700); normal 窗不出地面点故也无顶点。
    winheads = {f["id"] for f in feats if f["kind"] == "window_head"}
    assert winheads == {"winhead:w1:a", "winhead:w1:b"}
    assert all(f["world"][2] == calib_features.perspective._REAL_CEILING_MM
               for f in feats if f["kind"] == "window_head")


def test_derive_features_adds_coplanar_breaking_noncoplanar_points():
    """F002: 每个存活墙角出同 (x,y) 天花板角(z=2700), 破共面退化的关键异面供给。"""
    G = {
        "meta": {"mm_per_px": 10},
        "rooms": [{"id": "a", "rect": [0, 0, 100, 100], "label": {"zh": "甲"}}],
        "openings": [],
    }
    feats, _ = calib_features.derive_features(G, "a")
    grounds = {(f["world"][0], f["world"][1]) for f in feats if f["kind"] == "wall_corner"}
    ceils = {(f["world"][0], f["world"][1]) for f in feats if f["kind"] == "ceiling_corner"}
    assert grounds == ceils  # 天花板角与地面角一一对应, 同 (x,y)
    assert len(ceils) == 4
    assert all(f["world"][2] == calib_features.perspective._REAL_CEILING_MM
               for f in feats if f["kind"] == "ceiling_corner")
    # 异面: 存在两个不同高度 -> 通用 PnP 良态 (共面单应的退化条件被打破)。
    heights = {f["world"][2] for f in feats}
    assert heights == {0.0, float(calib_features.perspective._REAL_CEILING_MM)}


# ---- solve_pnp --------------------------------------------------------------------


def test_solve_pnp_recovers_synthetic_camera():
    """合成真值往返: 残差 <2px, 焦距 ±2%, 相机位置 <30mm, 天花投影一致 (r3 符号被钉住)。"""
    cam_true, project = _synthetic_cam()
    pts = [((x, y, 0.0), tuple(project((x, y, 0.0)))) for x, y in _PNP_WORLDS]
    cam = calib_features.solve_pnp(pts, img_wh=(2048, 1536))
    errs = [
        np.hypot(*(np.array(cam.project(x, y, 0.0)) - np.array(project((x, y, 0.0)))))
        for x, y in _PNP_WORLDS
    ]
    assert max(errs) < 2.0
    assert abs(cam.focal - cam_true.focal) / cam_true.focal < 0.02
    C = -cam.R.T @ cam.t
    assert np.linalg.norm(C - np.array([7500.0, 6500.0, 1400.0])) < 30.0
    # 天花点 (z=2700) 只有 r3 参与 —— 断言它与真值一致, 钉死左手系 z 列符号。
    got = np.array(cam.project(10000.0, 12000.0, 2700.0))
    want = np.array(project((10000.0, 12000.0, 2700.0)))
    assert np.hypot(*(got - want)) < 5.0


def test_solve_pnp_tolerates_click_noise():
    cam_true, project = _synthetic_cam()
    rng = np.random.default_rng(7)
    pts = [
        ((x, y, 0.0), tuple(np.array(project((x, y, 0.0))) + rng.normal(0, 3.0, 2)))
        for x, y in _PNP_WORLDS
    ]
    cam = calib_features.solve_pnp(pts, img_wh=(2048, 1536))
    anchors = [{"world": [x, y, 0], "px": list(p)} for (x, y, _z), p in pts]
    q = perspective.assess_calibration_quality(cam, anchors, img_wh=(2048, 1536))
    assert q["ok"] is True  # σ=3px 点击噪声下仍过硬门


def test_solve_pnp_rejects_degenerate_input():
    cam_true, project = _synthetic_cam()
    three = [((x, y, 0.0), tuple(project((x, y, 0.0)))) for x, y in _PNP_WORLDS[:3]]
    with pytest.raises(ValueError):
        calib_features.solve_pnp(three, img_wh=(2048, 1536))
    lifted = [((x, y, 100.0), tuple(project((x, y, 0.0)))) for x, y in _PNP_WORLDS]
    with pytest.raises(ValueError):
        calib_features.solve_pnp(lifted, img_wh=(2048, 1536))


# ---- 端点层 -----------------------------------------------------------------------


def test_calibration_features_endpoint(client_fal):
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c, room_id="r_foyer")
    r = c.get(f"/api/projects/D/baselines/v1/photos/{photo['id']}/calibration-features")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["room_ids"] == ["r_foyer", "r_live"]
    kinds = {f["kind"] for f in body["features"]}
    assert "wall_corner" in kinds and "door_jamb" in kinds
    # F002: 端点同时透出异面点 (天花板角/门顶) 供多高度点选。
    assert "ceiling_corner" in kinds and "door_head" in kinds
    ground_kinds = {"wall_corner", "door_jamb", "window_floor"}
    assert all(f["world"][2] == 0.0 for f in body["features"] if f["kind"] in ground_kinds)
    assert all(f["world"][2] > 0.0 for f in body["features"] if f["kind"] not in ground_kinds)


def test_calibration_features_requires_room(client_fal):
    c, _relay, _fal, _set = client_fal
    r0 = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("room.png", __import__("test_render_real_geometry")._PNG, "image/png")},
    )
    assert r0.status_code == 201
    r = c.get(f"/api/projects/D/baselines/v1/photos/{r0.json()['id']}/calibration-features")
    assert r.status_code == 400 and "标注房间" in r.json()["error"]


def test_points_mode_save_and_render_chain(client_fal, monkeypatch):
    """points 保存 -> 存盘含 mode/points/anchors 镜像/quality/openings_hash -> 几何锁定出图跑通。"""
    c, relay, _fal, _set = client_fal
    _stub_accept(monkeypatch, [{"ok": True, "score": 1.0, "fail_reasons": [], "checks": {}}])
    monkeypatch.setattr(main.perspective, "guide_sanity_issues", lambda *a, **k: [])
    _cam_true, project = _synthetic_cam()
    photo = _upload_photo(c)
    payload = {"mode": "points", "points": _pnp_points(project), "img_wh": [2048, 1536]}
    r = c.post(_CAL.format(pid=photo["id"]), json=payload)
    assert r.status_code == 200, r.text
    cal = r.json()["calibration"]
    assert cal["mode"] == "points" and len(cal["points"]) == 5
    assert len(cal["anchors"]) == 5  # F005/heal 兼容镜像
    assert cal["reprojection_error"] < 2.0
    assert cal["quality"]["level"] in ("good", "suspect")
    assert cal["binding"]["openings_hash"]
    rr = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    assert rr.status_code == 200, rr.text
    job = _wait(c, rr.json()["job_id"])  # 200-path 约定: 排空后台 job
    assert job["status"] == "done", job
    assert job["result"]["method"] == "geometry-lock"
    assert len(relay.calls) == 1


def test_points_mode_dry_run_previews_without_persist(client_fal):
    c, _relay, _fal, _set = client_fal
    _cam_true, project = _synthetic_cam()
    photo = _upload_photo(c, room_id="r_foyer")
    photos_path = next(Path(main.DATA_DIR, "D").rglob("photos.json"))
    before = photos_path.read_bytes()
    payload = {"mode": "points", "points": _pnp_points(project), "img_wh": [2048, 1536]}
    r = c.post(_CAL.format(pid=photo["id"]) + "?dry_run=1", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["quality"] is not None and body["wireframe"]
    assert photos_path.read_bytes() == before


def test_points_mode_rejects_too_few_points(client_fal):
    c, _relay, _fal, _set = client_fal
    _cam_true, project = _synthetic_cam()
    photo = _upload_photo(c)
    payload = {"mode": "points", "points": _pnp_points(project, n=3), "img_wh": [2048, 1536]}
    r = c.post(_CAL.format(pid=photo["id"]), json=payload)
    assert r.status_code == 400 and "4" in r.json()["error"]


def test_points_calibration_heal_skips_gracefully():
    """calib_heal 对 points 载荷 (无 x/y_lines) -> skipped_no_inputs, 不崩不改写 (spec §D2)。"""
    photo = {
        "id": "p1",
        "calibration": {
            "mode": "points",
            "points": [{"world": [0, 0, 0], "px": [10, 10]}] * 4,
            "anchors": [{"world": [0, 0, 0], "px": [10, 10]}] * 4,
            "img_wh": [2048, 1536],
            "camera": {"K": np.eye(3).tolist(), "R": np.eye(3).tolist(), "t": [0, 0, 0]},
        },
    }
    out, report = calib_heal.heal_photos([photo])
    assert out[0] is photo  # 原样透传
    assert report[0]["status"] == "skipped_no_inputs"


def test_openings_change_marks_points_calibration_stale():
    import copy

    G = _seed_geometry()
    photo = {"id": "p1", "room_id": "r_live", "width": 2048, "height": 1536}
    cal = {
        "camera": {},
        "binding": {
            **main._calibration_binding(G, "r_live", photo),
            "created_from_baseline_version_id": "v1",
            "openings_hash": main._stable_hash(G.get("openings", [])),
        },
    }
    assert main._calibration_stale_reason(cal, G, photo) is None
    g2 = copy.deepcopy(G)
    g2["openings"][0]["wall"]["span"][0] += 5  # 挪一扇门
    reason = main._calibration_stale_reason(cal, g2, photo)
    assert reason is not None and "门窗" in reason
