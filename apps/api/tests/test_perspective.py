# -*- coding: utf-8 -*-
"""透视标定/投影 perspective.py: 消失点、合成相机往返、footprint mask。"""

import numpy as np
import pytest
from aigc.perspective import Camera, calibrate, footprint_mask, vanishing_point


def _synth_camera(f=1600.0, W=2048, H=1536):
    """合成相机: 世界 Z 上, 相机在房间一角朝对角俯视 (与实拍墙角视角同构)。"""
    cx, cy = W / 2, H / 2
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
    eye = np.array([3000.0, 3000.0, 1450.0])
    target = np.array([10000.0, 12000.0, 0.0])
    fwd = target - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    down = np.cross(fwd, right)
    down /= np.linalg.norm(down)
    R = np.vstack([right, down, fwd])  # 行=相机轴在世界系 => 列=世界轴在相机系
    t = -R @ eye
    return Camera(K=K, R=R, t=t), (W, H)


def test_vanishing_point_converging_lines():
    # 两条线延长后交于 (500,200)
    vp = vanishing_point([((100, 100), (300, 150)), ((100, 300), (300, 250))])
    assert np.allclose(vp, [500, 200], atol=1.0)


def test_vanishing_point_needs_two_lines():
    with pytest.raises(ValueError):
        vanishing_point([((0, 0), (1, 1))])


def test_project_in_frame():
    cam, _ = _synth_camera()
    u, v = cam.project(10000, 12000, 0)
    assert 0 <= u <= 2048 and 0 <= v <= 1536


def test_calibrate_roundtrip():
    cam, wh = _synth_camera()
    P = cam.project
    x_lines = [(P(5000, 14000, 0), P(12000, 14000, 0)), (P(5000, 9000, 0), P(12000, 9000, 0))]
    y_lines = [(P(12000, 5000, 0), P(12000, 14000, 0)), (P(8000, 5000, 0), P(8000, 14000, 0))]
    anchors = [((12000, 14000, 0), P(12000, 14000, 0)), ((5000, 14000, 0), P(5000, 14000, 0))]
    rec = calibrate(x_lines, y_lines, anchors, img_wh=wh)
    assert abs(rec.focal - cam.focal) < 5
    for pt in [(7000, 10000, 0), (11000, 13000, 0), (6000, 8000, 0)]:
        a, b = np.array(cam.project(*pt)), np.array(rec.project(*pt))
        assert np.hypot(*(a - b)) < 2.0


def test_calibrate_same_direction_raises():
    cam, wh = _synth_camera()
    P = cam.project
    same = [(P(5000, 14000, 0), P(12000, 14000, 0)), (P(5000, 9000, 0), P(12000, 9000, 0))]
    anchors = [((12000, 14000, 0), P(12000, 14000, 0)), ((5000, 14000, 0), P(5000, 14000, 0))]
    with pytest.raises(ValueError):
        calibrate(same, same, anchors, img_wh=wh)


def test_footprint_mask_covers_item():
    cam, wh = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    furn = [{"t": "media", "room_id": "r", "dx": 1000, "dy": 1000, "w": 40, "h": 200}]
    mask, n = footprint_mask(cam, furn, rooms, wh, mm_per_px=10)
    assert n == 1
    arr = np.asarray(mask)
    assert arr.max() == 255
    cxp, cyp = cam.project((1000 + 20) * 10, (1000 + 100) * 10, 0)
    ys, xs = np.where(arr > 0)
    assert xs.min() <= cxp <= xs.max() and ys.min() <= cyp <= ys.max()


def test_footprint_mask_include_filter_and_skip_partition():
    cam, wh = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    furn = [
        {"t": "media", "room_id": "r", "dx": 1000, "dy": 1000, "w": 40, "h": 200},
        {"t": "partition", "room_id": "r", "dx": 500, "dy": 500, "w": 40, "h": 40},
        {"t": "sofa", "room_id": "r", "dx": 800, "dy": 800, "w": 200, "h": 90},
    ]
    _, n = footprint_mask(cam, furn, rooms, wh, include={"media"})
    assert n == 1  # 只画 media; partition 恒跳过
