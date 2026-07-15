# -*- coding: utf-8 -*-
"""透视标定/投影 perspective.py: 消失点、合成相机往返、footprint mask、彩盒标注图。"""

import io

import numpy as np
import pytest
from aigc.perspective import (
    ANNO_PALETTE,
    NEAR_MM,
    Camera,
    _box_polys,
    _footprint_corners_px,
    _item_height_mm,
    _item_z0_mm,
    annotate_boxes,
    box_usability,
    calibrate,
    footprint_mask,
    guide_sanity_issues,
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


# ==================== render-fix-b1 F001: 近平面裁剪 ====================
# 生产病灶: 贴窗 curtain 盒跨相机平面 (minDepth=-55mm), 无守卫投影 uv/负深度 -> 多边形穿过
# 相机翻转炸开 (u:-8903..6580 v:-47843..111194), 品红覆盖全画幅糊死引导图 -> AI 无位置信号。


def _naive_box_polys(cam, item, room_origin, mm_per_px):
    """修复前的无守卫投影 (对照基线): 直接 uv[0]/uv[2], 不做近平面裁剪。"""
    corners = _footprint_corners_px(item, room_origin)
    z0 = _item_z0_mm(item)
    hz = _item_height_mm(item)

    def pd(px, py, z):
        w = np.array([px * mm_per_px, py * mm_per_px, z], float)
        uv = cam.K @ (cam.R @ w + cam.t)
        return (float(uv[0] / uv[2]), float(uv[1] / uv[2])), float(uv[2])

    base = [pd(px, py, z0) for px, py in corners]
    top = [pd(px, py, hz) for px, py in corners]
    faces = [base, top] + [
        [base[i], base[(i + 1) % 4], top[(i + 1) % 4], top[i]] for i in range(4)
    ]
    return [(float(np.mean([d for _, d in f])), [p for p, _ in f]) for f in faces]


def _straddling_item():
    """薄板跨相机平面 (相机 eye=(3000,3000,1450)mm=(300,300)px): 与生产贴窗 curtain 同构。"""
    return {"t": "curtain", "dx": 250, "dy": 250, "w": 120, "h": 10, "z": 1450}


def test_box_polys_fully_visible_box_is_byte_identical_to_unclipped():
    """byte-safe 铁要求: 盒完全在近平面之前 -> 裁剪为 no-op, 与修复前投影逐字节一致。"""
    cam, _wh = _synth_camera()
    item = {"t": "sofa", "dx": 800, "dy": 900, "w": 210, "h": 90, "z": 800}
    got = _box_polys(cam, item, (0, 0), 10.0)
    assert len(got) == 6, "全可见盒应 6 面俱在"
    assert got == _naive_box_polys(cam, item, (0, 0), 10.0), "全可见盒投影必须逐字节不变"


def test_box_polys_straddling_camera_plane_is_clipped_not_exploded():
    cam, (W, H) = _synth_camera()
    item = _straddling_item()
    # 前提: 该盒确有顶点在相机背后 (与生产 curtain minDepth=-55 同构)
    assert not box_usability(cam, item, (0, 0), (W, H), mm_per_px=10.0)["usable"]
    # 对照有效性: 无守卫投影确实炸开 (纵向跨度 >5 倍画幅; 合法盒绝无可能。生产实测 ~103 倍)
    naive_v = [p[1] for _d, pts in _naive_box_polys(cam, item, (0, 0), 10.0) for p in pts]
    assert max(naive_v) - min(naive_v) > 5 * H, "对照基线应复现炸开病灶"
    # 修复后: 可见部分保留 (勿整件丢弃), 且无负深度顶点参与投影
    got = _box_polys(cam, item, (0, 0), 10.0)
    assert got, "跨平面盒的可见部分应保留"
    assert all(d >= NEAR_MM for d, _pts in got), "存活面深度必 >= NEAR_MM"
    for _d, pts in got:
        us = [p[0] for p in pts]
        vs = [p[1] for p in pts]
        assert not (
            min(us) < 0 and max(us) > W and min(vs) < 0 and max(vs) > H
        ), "不得有面双轴罩死整幅画面"


def test_box_polys_drops_faces_entirely_behind_camera():
    """整盒在相机背后 -> 全部面丢弃 (投影不可信, 画上去就是垃圾)。"""
    cam, _wh = _synth_camera()
    item = {"t": "sofa", "dx": -300, "dy": -300, "w": 100, "h": 100, "z": 800}
    assert _box_polys(cam, item, (0, 0), 10.0) == []


def test_footprint_mask_not_flooded_by_straddling_box():
    """footprint_mask 共用 _box_polys: 跨相机平面的盒修前会把 mask 糊成全白。"""
    cam, (W, H) = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    furn = [{**_straddling_item(), "room_id": "r"}]
    mask, drawn = footprint_mask(cam, furn, rooms, (W, H), mm_per_px=10)
    assert drawn == 1
    white = sum(1 for p in mask.getdata() if p > 0)
    assert white < 0.5 * W * H, "跨相机平面的盒不应把 mask 糊成全白"


# ============ render-fix-b1 F002: 调色板撞色 / 结构件跳过 ============
# 生产病灶: ANNO_PALETTE 仅 8 色 + `% len(ANNO_PALETTE)` 静默回绕 -> r_live 跳过 rug 后 9 类,
# 第9类 plant 撞第1类 dining_table 同为 purple -> prompt 并存 "purple box = 餐桌" 与
# "purple boxes = 绿植(3个)" -> 画面 4 个紫盒语义不可区分 -> 模型自行猜 -> 餐桌落位错。

_LIVE_TYPES = [  # 生产实证: D 户型 r_live 的 9 种类型 (跳 rug 后)
    "dining_table", "sofa", "coffee_table", "media", "entry_door",
    "wine_cabinet", "wall_art", "curtain", "plant",
]


def _spread_furn(types, room="r"):
    return [
        {"t": t, "room_id": room, "dx": 400 + i * 30, "dy": 800, "w": 40, "h": 40, "z": 500}
        for i, t in enumerate(types)
    ]


def test_annotate_boxes_colors_are_injective_and_skip_structural():
    cam, wh = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    _png, legend, drawn = annotate_boxes(
        cam, _spread_furn(_LIVE_TYPES), rooms, _photo_png(wh), wh, mm_per_px=10
    )
    colors = [e["color"] for e in legend]
    assert len(colors) == len(set(colors)), f"颜色->家具必须单射, 实得 {colors}"
    assert not any(e["t"] == "entry_door" for e in legend), "结构件 entry_door 不应进盒"
    assert drawn == len(_LIVE_TYPES) - 1, "entry_door 被跳, 其余照画"
    # 生产病灶正面锁: 餐桌与绿植不得同色
    dt = next(e["color"] for e in legend if e["t"] == "dining_table")
    pl = next(e["color"] for e in legend if e["t"] == "plant")
    assert dt != pl, "餐桌与绿植撞色 = 生产病灶复发"


def test_annotate_boxes_raises_on_palette_exhaustion_not_silent_wrap():
    """调色板耗尽必须报错阻断 —— 静默回绕会出颜色歧义的错图 (烧预算且 auto_check 检不出)。"""
    cam, wh = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    too_many = [f"kind{i}" for i in range(len(ANNO_PALETTE) + 1)]
    with pytest.raises(ValueError, match="调色板耗尽"):
        annotate_boxes(cam, _spread_furn(too_many), rooms, _photo_png(wh), wh, mm_per_px=10)


def test_anno_palette_has_headroom_and_unique_names():
    assert len(ANNO_PALETTE) >= 14, "调色板须留足单房现实类型数余量"
    names = [n for n, _rgb in ANNO_PALETTE]
    assert len(names) == len(set(names)), "色名不得重复 (prompt 靠色名映射)"
    rgbs = [rgb for _n, rgb in ANNO_PALETTE]
    assert len(rgbs) == len(set(rgbs)), "RGB 不得重复"
    # 前 8 色顺序/取值冻结 (既有 legend 字节安全)
    assert names[:8] == ["purple", "blue", "orange", "green", "cyan", "red", "yellow", "magenta"]


# ============ render-fix-b1 F003: 引导图健全性门禁 ============
# 生产病灶: 引导图退化时 auto_check 照样打 0.967 通过 -> 静默出错图烧预算。


def test_guide_sanity_passes_normal_layout():
    cam, wh = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    furn = [
        {"t": "sofa", "room_id": "r", "dx": 800, "dy": 900, "w": 210, "h": 90, "z": 800},
        {"t": "dining_table", "room_id": "r", "dx": 600, "dy": 1100, "w": 300, "h": 110, "z": 760},
    ]
    assert guide_sanity_issues(cam, furn, rooms, wh, mm_per_px=10) == [], "正常布局不得被拦"


def test_guide_sanity_flags_box_swallowing_the_frame():
    """相机陷在家具体内 -> 单盒罩死画面, 引导图无位置信息 -> 必须拦下。"""
    cam, wh = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    # 盒把相机 eye=(3000,3000,1450)mm=(300,300)px 包在体内
    furn = [{"t": "wardrobe", "room_id": "r", "dx": 200, "dy": 200, "w": 200, "h": 200, "z": 3000}]
    issues = guide_sanity_issues(cam, furn, rooms, wh, mm_per_px=10)
    assert issues and "wardrobe" in issues[0]


def test_guide_sanity_does_not_flag_legit_offframe_clipped_box():
    """反证 (勿把门关死): F001 裁剪后合法的贴脸盒 (相机站窗边的窗帘) 坐标很大, 但画幅内
    几乎不覆盖 —— 生产实物实证该场景应放行。"""
    cam, wh = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    furn = [{**_straddling_item(), "room_id": "r"}]
    assert guide_sanity_issues(cam, furn, rooms, wh, mm_per_px=10) == []


def test_guide_sanity_skips_structural_types():
    cam, wh = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    furn = [{"t": "partition", "room_id": "r", "dx": 200, "dy": 200, "w": 200, "h": 200, "z": 3000}]
    assert guide_sanity_issues(cam, furn, rooms, wh, mm_per_px=10) == []


def test_guide_sanity_threshold_boundary_is_load_bearing(monkeypatch):
    """阈值边界用例: 取覆盖率贴近阈值 (~82%) 的盒, 在阈值两侧行为必须翻转。

    首轮验收指出: 只测 1.7% 与 ~100% 两端极值时, 阈值漂移不会让测试变红 = 阈值不承重。
    本例把同一个盒卡在阈值两侧, 锁住阈值的判别力。
    """
    from aigc import perspective as P

    cam, wh = _synth_camera()
    rooms = {"r": [0, 0, 2000, 2000]}
    # 该盒实测覆盖 ~82% 画幅 (贴近默认阈值 0.9 但未越线)
    furn = [{"t": "wardrobe", "room_id": "r", "dx": 400, "dy": 400, "w": 300, "h": 300, "z": 2500}]
    assert P.GUIDE_SINGLE_BOX_MAX_FRAME_FRAC == 0.9, "本例的边界位置与默认阈值耦合"
    assert guide_sanity_issues(cam, furn, rooms, wh, mm_per_px=10) == [], "略低于阈值须放行"
    # 阈值下调到覆盖率之下 -> 同一盒必须被拦 (证明阈值真承重, 不是摆设)
    monkeypatch.setattr(P, "GUIDE_SINGLE_BOX_MAX_FRAME_FRAC", 0.80)
    flagged = P.guide_sanity_issues(cam, furn, rooms, wh, mm_per_px=10)
    assert flagged and "wardrobe" in flagged[0], "略高于阈值须拦下"
