# -*- coding: utf-8 -*-
"""calib-cure-b1 F003: assess_calibration_quality 单一真源 + 保存硬门 400 BAD_CALIBRATION。

负样本 = 生产两案标定 payload 逐字内联 (spec §6, 纯数值无 PIPL): 798 书房 (近竖直墙线 +
图角锚点, reproj≈2353px) 与 f4d 客餐厅 (门厅虚拟角, reproj≈112px + 相机高 399mm)。
沙箱种子几何与生产 baseline 允许分叉 (F001 偏差报告), 端点断言只锚定对几何不敏感的
硬门 (reproj / 相机高), 不断言离房软信号的具体数值。
"""

import json
from pathlib import Path

import main
import numpy as np
import pytest
from aigc import perspective
from test_render_real_geometry import (
    _PNG,
    _calib_payload,
    _calibrated_photo,
    _stub_accept,
    _upload_photo,
    _wait,
)

_CAL = "/api/projects/D/baselines/v1/photos/{pid}/calibration"


# ---- 生产病例 payload (spec §6 内联数值) ----------------------------------------


def _payload_798():
    """书房: x_lines 画成右缘近竖直短线 + SW 锚点点在图像角 -> 位姿垃圾 (reproj≈2353px)。"""
    return {
        "img_wh": [2048, 1536],
        "x_lines": [[[2039, 1214], [2042, 1484]], [[2032, 82], [2020, 9]]],
        "y_lines": [[[1017, 970], [2042, 1202]], [[1026, 442], [2039, 67]]],
        "anchors": [
            {"world": [18150, 2500, 0], "px": [1019, 980]},
            {"world": [15150, 5800, 0], "px": [6, 1533]},
        ],
    }


def _payload_f4d():
    """客餐厅: 门厅 merge 开放边界虚拟角凭感觉点 -> 相机高 399mm + reproj≈112px。"""
    return {
        "img_wh": [2048, 1536],
        "x_lines": [[[1009, 878], [45, 1009]], [[1007, 649], [43, 488]]],
        "y_lines": [[[40, 1014], [1, 1236]], [[40, 483], [0, 184]]],
        "anchors": [
            {"world": [4950, 2500, 0], "px": [1908, 945]},
            {"world": [6750, 5800, 0], "px": [43, 1013]},
        ],
    }


# ---- 单元层: 合成真值相机 (标定功能缺陷核查 20260717 实验一同款构造) --------------


def _synthetic_cam(f=1450.0, eye=(7500.0, 6500.0, 1400.0), W=2048, H=1536):
    """朝南偏东 30°、俯 8.5° 的手持相机; 返回 (Camera, 精确投影函数)。"""
    psi, p = np.radians(30), np.radians(8.5)
    fwd = np.array([np.sin(psi) * np.cos(p), np.cos(psi) * np.cos(p), -np.sin(p)])
    right = np.array([-np.cos(psi), np.sin(psi), 0.0])
    down = -np.cross(fwd, right)
    down /= np.linalg.norm(down)
    M = np.vstack([right, down, fwd])
    K = np.array([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1.0]])
    C = np.array(eye, float)
    cam = perspective.Camera(K=K, R=M, t=-M @ C)

    def project(w):
        u, v = cam.project(float(w[0]), float(w[1]), float(w[2]))
        return [u, v]

    return cam, project


_ANCHOR_WORLDS = ((4950.0, 14100.0, 0.0), (12150.0, 14100.0, 0.0), (12150.0, 9500.0, 0.0))


def _anchors(project, shift_px=0.0):
    return [
        {"world": list(w), "px": [project(w)[0] + shift_px, project(w)[1]]}
        for w in _ANCHOR_WORLDS
    ]


_ROOM_AROUND_EYE = ((4950.0, 5800.0, 12150.0, 14100.0),)  # 相机在内 -> dist=0


def test_assess_good_camera_passes_all_gates():
    cam, project = _synthetic_cam()
    q = perspective.assess_calibration_quality(
        cam, _anchors(project), room_rects_mm=_ROOM_AROUND_EYE, img_wh=(2048, 1536)
    )
    assert q["ok"] is True and q["level"] == "good" and q["reasons"] == []
    m = q["metrics"]
    assert m["reproj_px"] < 1.0
    assert m["camera_z_mm"] == pytest.approx(1400.0, abs=1.0)
    assert m["camera_room_dist_mm"] == 0.0
    assert 60.0 < m["hfov_deg"] < 71.0  # f=1450 @ W=2048 -> ~70.5°


def test_assess_reproj_hard_gate_and_env_escape_hatch(monkeypatch):
    """锚点整体偏 60px: 默认阈值 50 -> bad; env 放宽到 100 -> 放行但 suspect (>25)。"""
    cam, project = _synthetic_cam()
    bad = perspective.assess_calibration_quality(
        cam, _anchors(project, shift_px=60.0), room_rects_mm=_ROOM_AROUND_EYE, img_wh=(2048, 1536)
    )
    assert bad["ok"] is False and bad["level"] == "bad"
    assert any("重投影误差" in r for r in bad["reasons"])
    monkeypatch.setenv("CALIB_MAX_REPROJ_PX", "100")
    ok = perspective.assess_calibration_quality(
        cam, _anchors(project, shift_px=60.0), room_rects_mm=_ROOM_AROUND_EYE, img_wh=(2048, 1536)
    )
    assert ok["ok"] is True and ok["level"] == "suspect"


def test_assess_camera_height_gate():
    cam, project = _synthetic_cam(eye=(7500.0, 6500.0, 300.0))  # 膝下 (f4d 病灶 399mm 同族)
    q = perspective.assess_calibration_quality(
        cam, _anchors(project), room_rects_mm=_ROOM_AROUND_EYE, img_wh=(2048, 1536)
    )
    assert q["ok"] is False and any("相机高度" in r for r in q["reasons"])


def test_assess_hfov_gate():
    cam, project = _synthetic_cam(f=600.0)  # HFOV ≈ 119.4° > 110°
    q = perspective.assess_calibration_quality(
        cam, _anchors(project), room_rects_mm=_ROOM_AROUND_EYE, img_wh=(2048, 1536)
    )
    assert q["ok"] is False and any("视场角" in r for r in q["reasons"])


def test_assess_room_distance_is_soft_signal_not_gate():
    """离房 >1500mm 只降 suspect + 提示确认绑定, 不 fail (2026-07-17 pre-impl 裁决)。"""
    cam, project = _synthetic_cam()
    far_room = ((20000.0, 20000.0, 23000.0, 23000.0),)
    q = perspective.assess_calibration_quality(
        cam, _anchors(project), room_rects_mm=far_room, img_wh=(2048, 1536)
    )
    assert q["ok"] is True and q["level"] == "suspect"
    assert any("房间绑定" in r for r in q["reasons"])
    assert q["metrics"]["camera_room_dist_mm"] > 1500


def test_assess_missing_anchors_fails_closed():
    cam, _project = _synthetic_cam()
    q = perspective.assess_calibration_quality(cam, [], room_rects_mm=(), img_wh=(2048, 1536))
    assert q["ok"] is False and any("锚点" in r for r in q["reasons"])
    assert q["metrics"]["reproj_px"] is None


# ---- 求解器+assess 层: 生产 payload 逐字重放 (绕过 F004 端点校验, 钉住 assess 结论) ----


def _solve_production(payload):
    to_line = lambda ln: (tuple(ln[0]), tuple(ln[1]))  # noqa: E731
    cam = perspective.calibrate(
        [to_line(ln) for ln in payload["x_lines"]],
        [to_line(ln) for ln in payload["y_lines"]],
        [(tuple(a["world"]), tuple(a["px"])) for a in payload["anchors"]],
        img_wh=tuple(payload["img_wh"]),
    )
    return cam


def test_production_798_assess_catches_garbage_pose():
    """798 存量重放: reproj≈2353px 越硬门 (即 F005 渲染门对存量的判定结论)。"""
    p = _payload_798()
    cam = _solve_production(p)
    q = perspective.assess_calibration_quality(cam, p["anchors"], img_wh=tuple(p["img_wh"]))
    assert q["ok"] is False and q["level"] == "bad"
    assert any("重投影误差" in r for r in q["reasons"])
    assert q["metrics"]["reproj_px"] > 1000


def test_production_f4d_assess_catches_knee_high_camera():
    """f4d 存量重放: reproj≈112px + 相机高 399mm 两条硬门齐中。"""
    p = _payload_f4d()
    cam = _solve_production(p)
    q = perspective.assess_calibration_quality(cam, p["anchors"], img_wh=tuple(p["img_wh"]))
    assert q["ok"] is False
    assert any("重投影误差" in r for r in q["reasons"])
    assert any("相机高度" in r for r in q["reasons"])
    assert q["metrics"]["camera_z_mm"] < 800


# ---- 端点层: F004 语义校验在前、F003 assess 硬门在后的分层拦截 --------------------


def test_save_rejects_production_case_798_at_semantic_layer(client_fal):
    """798 payload 在解算之前就被 F004 拦: 近竖直『水平线』= 消失点必退化。"""
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c, room_id="r_guest2")
    r = c.post(_CAL.format(pid=photo["id"]), json=_payload_798())
    assert r.status_code == 400, r.text
    assert "近竖直" in r.json()["error"]
    entry = next(p for p in c.get("/api/projects/D/baselines/v1/photos").json() if p["id"] == photo["id"])
    assert "calibration" not in entry


def test_save_rejects_production_case_f4d_at_semantic_layer(client_fal):
    """f4d payload 的 y_lines 也是左缘近竖直短线 ([40,1014]-[1,1236]) -> 同被方向规则拦。"""
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c, room_id="r_foyer")
    r = c.post(_CAL.format(pid=photo["id"]), json=_payload_f4d())
    assert r.status_code == 400, r.text
    assert "近竖直" in r.json()["error"]


def test_save_rejects_two_anchor_payload(client_fal):
    """线全合法但只有 2 锚点 -> F004 ≥3 规则拦 (角标互换粗差 2 锚点不可检, case A)。"""
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c)
    p = _calib_payload()
    p["anchors"] = p["anchors"][:2]
    r = c.post(_CAL.format(pid=photo["id"]), json=p)
    assert r.status_code == 400, r.text
    assert "≥3" in r.json()["error"]


def test_save_rejects_bad_quality_with_code(client_fal, monkeypatch):
    """语义合法但 assess 不过 -> 400 BAD_CALIBRATION (用 env 收紧阈值使好样本越线)。"""
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c)
    monkeypatch.setenv("CALIB_MAX_REPROJ_PX", "-1")  # 新 fixture reproj 精确=0.0, 用负阈值使其必然越线
    r = c.post(_CAL.format(pid=photo["id"]), json=_calib_payload())
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["code"] == "BAD_CALIBRATION"
    assert any("重投影误差" in x for x in body["reasons"])
    entry = next(p for p in c.get("/api/projects/D/baselines/v1/photos").json() if p["id"] == photo["id"])
    assert "calibration" not in entry


def test_save_stores_quality_snapshot(client_fal):
    """好标定照常入库, calibration 载荷带 quality 快照 (level/reasons/metrics)。"""
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c)
    r = c.post(_CAL.format(pid=photo["id"]), json=_calib_payload())
    assert r.status_code == 200, r.text
    q = r.json()["calibration"]["quality"]
    assert q["level"] in ("good", "suspect")
    assert q["metrics"]["reproj_px"] < 5.0
    assert "ok" not in q  # 快照只存 level/reasons/metrics (ok 由渲染门现算)


def test_dry_run_returns_200_with_bad_quality_for_preview(client_fal, monkeypatch):
    """spec §D4: 语义合法、可解算但质量 bad -> dry-run 仍 200, 前端用线框画出"有多歪"。"""
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c)
    monkeypatch.setenv("CALIB_MAX_REPROJ_PX", "-1")  # 新 fixture reproj 精确=0.0, 用负阈值使其必然越线
    r = c.post(_CAL.format(pid=photo["id"]) + "?dry_run=1", json=_calib_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True  # 顶层 ok = 解算成功
    assert body["quality"]["ok"] is False and body["quality"]["level"] == "bad"
    assert isinstance(body["wireframe"], list) and body["wireframe"]


# ---- F004 语义校验单项 (线/锚点退化拦截) ------------------------------------------


def _post_cal(c, payload, room_id="r_live"):
    photo = _upload_photo(c, room_id=room_id)
    return c.post(_CAL.format(pid=photo["id"]), json=payload)


def test_semantic_rejects_short_line(client_fal):
    c, _relay, _fal, _set = client_fal
    p = _calib_payload()
    p["x_lines"][0] = [[100, 100], [150, 100]]  # 50px < 图幅5%=102.4px
    r = _post_cal(c, p)
    assert r.status_code == 400 and "太短" in r.json()["error"]


def test_semantic_rejects_coincident_lines_in_group(client_fal):
    c, _relay, _fal, _set = client_fal
    p = _calib_payload()
    a, b = p["x_lines"][0]
    p["x_lines"][1] = [[a[0] + 5, a[1] + 5], [b[0] + 5, b[1] + 5]]  # 同线画两遍
    r = _post_cal(c, p)
    assert r.status_code == 400 and "重合" in r.json()["error"]


def test_semantic_rejects_anchor_near_image_edge(client_fal):
    """798 病灶之二: SW 锚点点在图像角 (6,1533) 属贴边猜测。"""
    c, _relay, _fal, _set = client_fal
    p = _calib_payload()
    p["anchors"][0]["px"] = [10, 700]  # < 2% 图幅边距 (2048*0.02=41)
    r = _post_cal(c, p)
    assert r.status_code == 400 and "贴近图像边缘" in r.json()["error"]


def test_semantic_rejects_anchor_pixels_too_close(client_fal):
    c, _relay, _fal, _set = client_fal
    p = _calib_payload()
    u, v = p["anchors"][0]["px"]
    p["anchors"][1]["px"] = [u + 20, v]  # < 2% 对角线 (51.2px)
    r = _post_cal(c, p)
    assert r.status_code == 400 and "过近" in r.json()["error"]


def test_semantic_rejects_duplicate_world_corner(client_fal):
    c, _relay, _fal, _set = client_fal
    p = _calib_payload()
    p["anchors"][1]["world"] = list(p["anchors"][0]["world"])  # 两锚点同一世界角
    r = _post_cal(c, p)
    assert r.status_code == 400 and "同一个世界墙角" in r.json()["error"]


def test_semantic_rejects_collinear_world_anchors(client_fal):
    """三点全在 y=14000 一条墙线上 = 有效锚点只有 2 个。"""
    c, _relay, _fal, _set = client_fal
    p = _calib_payload()
    p["anchors"][2]["world"] = [8500, 14000, 0]
    p["anchors"][2]["px"] = [630, 763]  # 像素合法 (过边距/间距检查), 共线性由世界坐标判
    r = _post_cal(c, p)
    assert r.status_code == 400 and "共线" in r.json()["error"]


# ---- F005 渲染入口存量质量复查 (409 硬拦, 用户裁决#3) ------------------------------


_RENDER = "/api/projects/D/schemes/default/render-real"
_OK_VERDICT = [{"ok": True, "score": 1.0, "fail_reasons": [], "checks": {}}]


def _mutate_stored_calibration(photo_id, mutate):
    """直接改 photos.json 里的存量标定 (F003/F004 后坏标定已无法经端点入库, 只能注入)。"""
    photos_path = next(Path(main.DATA_DIR, "D").rglob("photos.json"))
    photos = json.loads(photos_path.read_text())
    entry = next(p for p in photos if p["id"] == photo_id)
    mutate(entry)
    photos_path.write_text(json.dumps(photos, ensure_ascii=False))


def test_render_blocks_bad_stored_calibration_409(client_fal, monkeypatch):
    """798 同款存量 (无 binding=fresh) -> 出图 409 BAD_CALIBRATION, provider 未被调。"""
    c, relay, fal, _set = client_fal
    _stub_accept(monkeypatch, list(_OK_VERDICT))
    photo = _calibrated_photo(c)
    p798 = _payload_798()
    cam = _solve_production(p798)

    def _swap(entry):
        entry["calibration"] = {
            "x_lines": p798["x_lines"], "y_lines": p798["y_lines"],
            "anchors": p798["anchors"], "img_wh": p798["img_wh"],
            "camera": cam.to_dict(), "reprojection_error": 2353.4,
        }

    _mutate_stored_calibration(photo["id"], _swap)
    r = c.post(_RENDER, json={"photo_id": photo["id"]})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["code"] == "BAD_CALIBRATION"
    assert any("重投影误差" in x for x in body["reasons"])
    assert len(relay.calls) == 0 and len(fal.calls) == 0, "坏标定不得烧 AI 预算"


def test_render_blocks_malformed_stored_calibration_409_not_500(client_fal, monkeypatch):
    """缺 camera/anchors 的畸形存量 -> 409 提示重标, 不落 500。"""
    c, relay, fal, _set = client_fal
    _stub_accept(monkeypatch, list(_OK_VERDICT))
    photo = _calibrated_photo(c)
    _mutate_stored_calibration(photo["id"], lambda e: e.__setitem__("calibration", {"img_wh": [2048, 1536]}))
    r = c.post(_RENDER, json={"photo_id": photo["id"]})
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "BAD_CALIBRATION"
    assert len(relay.calls) == 0 and len(fal.calls) == 0


def test_render_stale_takes_priority_over_quality(client_fal, monkeypatch):
    """同时 stale + 坏质量 -> 先报 STALE_CALIBRATION (先修绑定再谈质量, 门序结构保证)。"""
    c, relay, fal, _set = client_fal
    _stub_accept(monkeypatch, list(_OK_VERDICT))
    photo = _calibrated_photo(c)
    p798 = _payload_798()
    cam = _solve_production(p798)

    def _swap_keep_binding(entry):
        binding = entry["calibration"].get("binding")
        entry["calibration"] = {
            "x_lines": p798["x_lines"], "y_lines": p798["y_lines"],
            "anchors": p798["anchors"], "img_wh": p798["img_wh"],
            "camera": cam.to_dict(), "binding": binding,
        }

    _mutate_stored_calibration(photo["id"], _swap_keep_binding)
    pr = c.patch(f"/api/projects/D/baselines/v1/photos/{photo['id']}", json={"room_id": "r_master"})
    assert pr.status_code == 200, pr.text
    r = c.post(_RENDER, json={"photo_id": photo["id"]})
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "STALE_CALIBRATION"


def test_render_allows_two_anchor_good_legacy_calibration(client_fal, monkeypatch):
    """渲染门只查质量不查锚点数 (spec §D2): 存量 n=2 好标定照常出图。"""
    c, relay, fal, _set = client_fal
    _stub_accept(monkeypatch, list(_OK_VERDICT))
    monkeypatch.setattr(main.perspective, "guide_sanity_issues", lambda *a, **k: [])
    photo = _calibrated_photo(c)
    _mutate_stored_calibration(
        photo["id"],
        lambda e: e["calibration"].__setitem__("anchors", e["calibration"]["anchors"][:2]),
    )
    r = c.post(_RENDER, json={"photo_id": photo["id"]})
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])  # 200-path 约定: 排空后台 job 防红线污染
    assert job["status"] == "done", job
    assert len(relay.calls) == 1


# ---- F006 guide 健全性聚合出画 + near×不可见矛盾话术 -------------------------------

# f4d 生产场景逐字 fixture: 生产 v7 房间 rect + scheme 家具 r_live 子集 (纯数值, 本批核查取证)。
_F4D_ROOM_RECTS = {"r_live": [495, 580, 720, 830], "r_foyer": [495, 250, 180, 330]}
_F4D_FURNITURE = [
    {"t": "dining_table", "w": 300, "h": 110, "seats": 8, "room_id": "r_live", "dx": 208, "dy": 105},
    {"t": "rug", "w": 360, "h": 320, "room_id": "r_live", "dx": 173, "dy": 420},
    {"t": "sofa", "w": 80, "h": 230, "orient": "W", "room_id": "r_live", "dx": 204, "dy": 459},
    {"t": "sofa", "w": 210, "h": 80, "orient": "S", "room_id": "r_live", "dx": 285, "dy": 609},
    {"t": "coffee_table", "w": 100, "h": 108, "room_id": "r_live", "dx": 334, "dy": 478},
    {"t": "media", "w": 44, "h": 244, "room_id": "r_live", "dx": 676, "dy": 457, "orient": "E"},
    {"t": "entry_door", "room_id": "r_live", "dx": -45, "dy": -170, "w": 105, "h": 10, "orient": "N"},
    {"t": "wine_cabinet", "room_id": "r_live", "dx": -60, "dy": 85, "w": 58, "h": 280, "orient": "W", "z": 1400},
    {"t": "wall_art", "room_id": "r_live", "dx": -33, "dy": 632, "w": 80, "h": 8, "orient": "N"},
    {"t": "curtain", "room_id": "r_live", "dx": 1, "dy": 820, "w": 719, "h": 10, "orient": "S"},
    {"t": "plant", "room_id": "r_live", "dcx": 66, "dcy": 753, "r": 13},
    {"t": "plant", "room_id": "r_live", "dcx": 33, "dcy": 786, "r": 20},
    {"t": "wall_art", "w": 8.0, "h": 80.0, "dx": 0.0, "dy": 534.0, "orient": "W", "room_id": "r_live"},
    {"t": "plant", "dcx": 24.0, "dcy": 24.0, "room_id": "r_live", "r": 20},
]


def test_f4d_guide_sanity_flags_mass_offframe():
    """f4d 病灶复现: 12 件可标注家具约半数投到画外 -> 聚合检查报退化 (原先完全静默)。"""
    cam = _solve_production(_payload_f4d())
    issues = perspective.guide_sanity_issues(
        cam, _F4D_FURNITURE, _F4D_ROOM_RECTS, (2048, 1536)
    )
    assert any("不在画面内" in s for s in issues), issues


def test_f4d_prompt_downgrades_invisible_near_to_partial():
    """f4d 病灶复现: 餐桌 0% 可见却标 near -> 话术降级 partial, 不再授权"前景全尺寸"。"""
    cam = _solve_production(_payload_f4d())
    _guide, legend, _drawn = perspective.annotate_boxes(
        cam, _F4D_FURNITURE, _F4D_ROOM_RECTS, _PNG, (2048, 1536)
    )
    dt = next(e for e in legend if e["t"] == "dining_table")
    assert dt.get("near") and dt.get("min_in_frame", 1.0) < 0.05
    prompt = main._geometry_lock_prompt(legend, _F4D_FURNITURE, None)
    assert "near foreground" not in prompt
    assert "partly outside the frame" in prompt


def test_near_note_kept_for_visible_near_piece():
    """反证: 真在前景且可见的件, near 话术保留 (电视柜生产病灶的原始修复不回退)。"""
    prompt = main._geometry_lock_prompt(
        [{"color": "green", "t": "media", "count": 1, "near": True, "min_in_frame": 0.6}], [], None
    )
    assert "near foreground" in prompt


def test_guide_sanity_aggregate_needs_min_items():
    """单件房间半出画是合法构图 (<3 件不判聚合退化)。"""
    cam = _solve_production(_payload_f4d())
    two = [it for it in _F4D_FURNITURE if it["t"] in ("dining_table", "coffee_table")]
    issues = perspective.guide_sanity_issues(cam, two, _F4D_ROOM_RECTS, (2048, 1536))
    assert not any("不在画面内" in s for s in issues)


# ---- F007 DELETE 标定端点 (坏标定的自助出口) ---------------------------------------


def test_delete_calibration_removes_key_and_falls_back(client_fal):
    """删除后照片回未标定态; 出图不再走几何锁定 (fal 后端配好也不被调 = 回退旧路径)。"""
    c, _relay, fal, set_settings = client_fal
    set_settings(geometry_edit_backend="fal")
    photo = _calibrated_photo(c)
    r = c.delete(f"/api/projects/D/baselines/v1/photos/{photo['id']}/calibration")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "removed": True}
    entry = next(p for p in c.get("/api/projects/D/baselines/v1/photos").json() if p["id"] == photo["id"])
    assert "calibration" not in entry
    r2 = c.delete(f"/api/projects/D/baselines/v1/photos/{photo['id']}/calibration")
    assert r2.status_code == 200 and r2.json()["removed"] is False  # 幂等
    c.post(_RENDER, json={"photo_id": photo["id"]})
    assert len(fal.calls) == 0  # 几何锁定被跳过 (同 no_calibration_falls_back 口径)


def test_delete_calibration_geom_readonly_403(client_fal, monkeypatch):
    c, _relay, _fal, _set = client_fal
    photo = _calibrated_photo(c)
    monkeypatch.setattr(main, "GEOM_READONLY", True)
    r = c.delete(f"/api/projects/D/baselines/v1/photos/{photo['id']}/calibration")
    assert r.status_code == 403
    monkeypatch.setattr(main, "GEOM_READONLY", False)
    entry = next(p for p in c.get("/api/projects/D/baselines/v1/photos").json() if p["id"] == photo["id"])
    assert "calibration" in entry  # 未被删


def test_delete_calibration_missing_photo_404(client_fal):
    c, _relay, _fal, _set = client_fal
    r = c.delete("/api/projects/D/baselines/v1/photos/nonexistent/calibration")
    assert r.status_code == 404


# ---- F010 direction 交叉校验 (D7: 仅拦近乎相反 >135°) ------------------------------


def test_direction_mismatch_only_when_nearly_opposite():
    cam, _project = _synthetic_cam()  # 朝向 SE 象限 (朝南偏东 30°)
    assert main._direction_mismatch_reason(cam, "v2") is None  # SE = v2 正配
    assert main._direction_mismatch_reason(cam, "v1") is None  # 相邻象限, 容差内不拦
    assert main._direction_mismatch_reason(cam, "v3") is None  # 相邻象限
    assert main._direction_mismatch_reason(cam, "v0") is not None  # NW = 近乎相反
    assert main._direction_mismatch_reason(cam, None) is None
    assert main._direction_mismatch_reason(cam, "N") is None  # legacy 值不检查 (D7)


def test_save_rejects_direction_opposite_photo(client_fal):
    """照片标注 v0(朝西北) 而解算相机朝东南 -> 硬门 400 (case-A 镜像类粗差的补充防线)。"""
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c)
    pr = c.patch(
        f"/api/projects/D/baselines/v1/photos/{photo['id']}", json={"direction": "v0"}
    )
    assert pr.status_code == 200, pr.text
    r = c.post(_CAL.format(pid=photo["id"]), json=_calib_payload())
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["code"] == "BAD_CALIBRATION"
    assert any("拍摄视角" in x for x in body["reasons"])
