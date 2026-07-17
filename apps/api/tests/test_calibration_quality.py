# -*- coding: utf-8 -*-
"""calib-cure-b1 F003: assess_calibration_quality 单一真源 + 保存硬门 400 BAD_CALIBRATION。

负样本 = 生产两案标定 payload 逐字内联 (spec §6, 纯数值无 PIPL): 798 书房 (近竖直墙线 +
图角锚点, reproj≈2353px) 与 f4d 客餐厅 (门厅虚拟角, reproj≈112px + 相机高 399mm)。
沙箱种子几何与生产 baseline 允许分叉 (F001 偏差报告), 端点断言只锚定对几何不敏感的
硬门 (reproj / 相机高), 不断言离房软信号的具体数值。
"""

import numpy as np
import pytest
from aigc import perspective
from test_render_real_geometry import _calib_payload, _upload_photo

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
