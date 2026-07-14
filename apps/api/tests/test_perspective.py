# -*- coding: utf-8 -*-
"""透视标定/投影 perspective.py: 消失点、合成相机往返、footprint mask、彩盒标注图。"""

import io

import numpy as np
import pytest
from aigc.perspective import (
    Camera,
    annotate_boxes,
    box_usability,
    calibrate,
    footprint_mask,
    vanishing_point,
)
from PIL import Image


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


def test_camera_serialization_roundtrip():
    cam, _ = _synth_camera()
    cam2 = Camera.from_dict(cam.to_dict())
    for pt in [(7000, 10000, 0), (11000, 13000, 500)]:
        a, b = cam.project(*pt), cam2.project(*pt)
        assert abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6


def test_footprint_mask_3d_box_and_dilate():
    cam, wh = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    furn = [{"t": "wardrobe", "room_id": "r", "dx": 1000, "dy": 1000, "w": 200, "h": 60, "z": 2000}]
    mask, n = footprint_mask(cam, furn, rooms, wh)
    assert n == 1
    area = int((np.asarray(mask) > 0).sum())
    assert area > 0
    mask2, _ = footprint_mask(cam, furn, rooms, wh, dilate=3)
    assert int((np.asarray(mask2) > 0).sum()) >= area  # 膨胀不缩小


def _photo_png(wh, color=(200, 200, 200)):
    buf = io.BytesIO()
    Image.new("RGB", wh, color).save(buf, format="PNG")
    return buf.getvalue()


def test_annotate_boxes_draws_colored_boxes_with_legend():
    cam, wh = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    furn = [
        {"t": "sofa", "room_id": "r", "dx": 800, "dy": 800, "w": 200, "h": 90},
        {"t": "sofa", "room_id": "r", "dx": 700, "dy": 900, "w": 80, "h": 200},  # L形第二段
        {"t": "coffee_table", "room_id": "r", "dx": 900, "dy": 1050, "w": 100, "h": 100},
    ]
    png, legend, drawn = annotate_boxes(cam, furn, rooms, _photo_png(wh), wh, mm_per_px=10)
    assert drawn == 3
    # legend: 同类共色, 首次出现序稳定, count 计件 (两段沙发 -> prompt 写 "2 pieces")
    assert legend == [
        {"color": "purple", "t": "sofa", "count": 2},
        {"color": "blue", "t": "coffee_table", "count": 1},
    ]
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    img = Image.open(io.BytesIO(png))
    assert img.size == wh
    arr = np.asarray(img.convert("RGB"), int)
    # 盒区像素被染色 (纯灰照片上出现通道差 > 40 的彩色像素)
    spread = arr.max(axis=2) - arr.min(axis=2)
    assert int((spread > 40).sum()) > 500


def test_annotate_boxes_skips_rug_and_partition():
    cam, wh = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    furn = [
        {"t": "rug", "room_id": "r", "dx": 700, "dy": 700, "w": 300, "h": 300},
        {"t": "partition", "room_id": "r", "dx": 500, "dy": 500, "w": 40, "h": 40},
        {"t": "sofa", "room_id": "r", "dx": 800, "dy": 800, "w": 200, "h": 90},
    ]
    _png, legend, drawn = annotate_boxes(cam, furn, rooms, _photo_png(wh), wh, mm_per_px=10)
    assert drawn == 1
    assert [e["t"] for e in legend] == ["sofa"]


def test_annotate_boxes_includes_decor_skips_rug():
    # decor-b2 F003: 挂画/窗帘用墙面带 z0 进彩盒 (撤销 b1-F008 隔离, 完整接入第7步); rug 仍跳。
    cam, wh = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    furn = [
        {"t": "rug", "room_id": "r", "dx": 700, "dy": 700, "w": 300, "h": 300},
        {"t": "wall_art", "room_id": "r", "dx": 500, "dy": 500, "w": 80, "h": 8},
        {"t": "curtain", "room_id": "r", "dx": 800, "dy": 800, "w": 120, "h": 10},
        {"t": "sofa", "room_id": "r", "dx": 900, "dy": 900, "w": 200, "h": 90},
    ]
    _png, legend, drawn = annotate_boxes(cam, furn, rooms, _photo_png(wh), wh, mm_per_px=10)
    assert drawn == 3  # wall_art + curtain + sofa (rug 跳)
    assert set(e["t"] for e in legend) == {"wall_art", "curtain", "sofa"}


def test_item_z0_and_height_wall_band():
    # decor-b2 F003: 挂画/窗帘盒底面在墙面带, 既有件 z0=0 (byte-safe)。
    from aigc import perspective as P
    assert P._item_z0_mm({"t": "wall_art"}) == 1000
    assert P._item_z0_mm({"t": "curtain"}) == 150
    assert P._item_z0_mm({"t": "sofa"}) == 0        # 既有件地面
    assert P._item_z0_mm({"t": "coffee_table"}) == 0
    assert P._DEFAULT_HEIGHT_MM["wall_art"] == 1400  # 顶对齐 SPECS 画框
    assert P._DEFAULT_HEIGHT_MM["curtain"] == 1450


def test_wall_art_box_in_upper_wall_band_not_floor():
    # 挂画彩盒投影在墙面带 (y 像素靠上), 非墙脚地面盒。
    from aigc.perspective import _box_polys
    cam, wh = _synth_camera()
    wa = {"t": "wall_art", "dx": 900, "dy": 900, "w": 80, "h": 8}
    floor = {"t": "rug", "dx": 900, "dy": 900, "w": 80, "h": 8}
    wa_ys = [pt[1] for _d, pts in _box_polys(cam, wa, (0, 0), 10) for pt in pts]
    fl_ys = [pt[1] for _d, pts in _box_polys(cam, floor, (0, 0), 10) for pt in pts]
    # 挂画盒最低点 (max y) 明显高于地面盒最低点 (悬空在墙面带)
    assert max(wa_ys) < max(fl_ys)


def test_annotate_boxes_resizes_photo_to_img_wh():
    cam, wh = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    furn = [{"t": "sofa", "room_id": "r", "dx": 800, "dy": 800, "w": 200, "h": 90}]
    png, _legend, drawn = annotate_boxes(
        cam, furn, rooms, _photo_png((1024, 768)), wh, mm_per_px=10
    )
    assert drawn == 1
    assert Image.open(io.BytesIO(png)).size == wh  # 照片尺寸与标定 img_wh 不符时对齐


def test_box_usability_far_piece_in_frame():
    """P0-5 盒子可用性: 房间深处的家具完整在画面内, 不判 partial/near。"""
    cam, wh = _synth_camera()
    far = {"t": "sofa", "dx": 400, "dy": 800, "w": 210, "h": 90, "z": 800}
    u = box_usability(cam, far, (300, 300), wh, mm_per_px=10)
    assert u["usable"] is True
    assert u["in_frame_frac"] > 0.85
    assert u["near"] is False


def test_box_usability_near_camera_piece_flagged():
    """P0-5 盒子可用性: 贴镜头家具大幅出画 -> near + 低 in_frame_frac (生产绿盒电视柜病灶)。"""
    cam, wh = _synth_camera()
    near = {"t": "media", "dx": 10, "dy": 10, "w": 150, "h": 44, "z": 550}
    u = box_usability(cam, near, (300, 300), wh, mm_per_px=10)
    assert u["near"] is True
    assert u["in_frame_frac"] < 0.85


def test_annotate_boxes_legend_flags_out_of_frame_piece():
    """P0-5: 出画/近场的家具在 legend 条目打 partial/near 标记, 供 prompt 降级话术。"""
    cam, wh = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    furn = [
        {"t": "sofa", "room_id": "r", "dx": 400, "dy": 800, "w": 210, "h": 90, "z": 800},
        {"t": "media", "room_id": "r", "dx": 5, "dy": 5, "w": 150, "h": 44, "z": 550},
    ]
    _png, legend, drawn = annotate_boxes(cam, furn, rooms, _photo_png(wh), wh, mm_per_px=10)
    assert drawn == 2
    sofa = next(e for e in legend if e["t"] == "sofa")
    media = next(e for e in legend if e["t"] == "media")
    assert not sofa.get("partial") and not sofa.get("near")  # 深处沙发不标
    assert media.get("near")  # 贴镜头电视柜标 near
