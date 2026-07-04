# -*- coding: utf-8 -*-
"""视角旋转 (实拍对齐): 轴测绕房间中心转 90°×k, 让参考图从与照片同侧看进去。
byte-safe: quarter_turns=0 与旧逐字节一致; round-trip: 4×90°=identity。"""
import os

from floorplan_core import axon, geometry

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
D_GEOM = os.path.join(REPO, "data", "projects", "D", "geometry.json")


def _geom():
    G = geometry.load(D_GEOM)
    return axon.geom_bundle(G, geometry.derive(G))


# ---- 纯函数: 旋转数学 ---- #
def test_rot_pt_roundtrip_identity():
    for x, y in [(0, 0), (13, 47), (-5, 200)]:
        p = (x, y)
        for _ in range(4):
            p = axon._rot_pt(p[0], p[1], 100.0, 80.0, 1)
        assert abs(p[0] - x) < 1e-6 and abs(p[1] - y) < 1e-6


def test_rot_rect_swaps_wh_on_odd_turn():
    x, y, w, h = axon._rot_rect(10, 20, 100, 40, 60.0, 40.0, 1)
    assert round(w) == 40 and round(h) == 100  # 90° -> w/h 互换
    # 4 圈回到原矩形
    r = (10, 20, 100, 40)
    for _ in range(4):
        r = axon._rot_rect(*r, 60.0, 40.0, 1)
    assert [round(v) for v in r] == [10, 20, 100, 40]


def test_rot_orient_cycles_cw():
    assert axon._rot_orient("N", 1) == "E"
    assert axon._rot_orient("E", 1) == "S"
    assert axon._rot_orient("N", 4) == "N"  # round-trip


def test_rot_axis_at_span_roundtrip():
    axis, at, span = "h", 100.0, [10.0, 90.0]
    a, t, s = axis, at, span
    for _ in range(4):
        a, t, s = axon._rot_axis_at_span(a, t, s, 50.0, 50.0, 1)
    assert a == "h" and abs(t - 100.0) < 1e-6 and [round(v) for v in s] == [10, 90]


# ---- 集成: render 旋转 ---- #
def test_render_quarter_turns_zero_is_byte_identical():
    geom = _geom()
    base = axon.render(geom, [], mode="photo")
    assert axon.render(geom, [], mode="photo", quarter_turns=0) == base


def test_render_roundtrip_four_turns_identity():
    geom = _geom()
    base = axon.render(geom, [], mode="photo", quarter_turns=0)
    assert axon.render(geom, [], mode="photo", quarter_turns=4) == base


def test_render_each_turn_distinct():
    geom = _geom()
    svgs = [axon.render(geom, [], mode="photo", quarter_turns=k) for k in range(4)]
    assert len(set(svgs)) == 4  # 四个视角互不相同


def test_shell_mode_unaffected_by_default():
    """plan2d/shell golden 安全: 不传 quarter_turns -> 默认 0 -> 不进旋转分支。"""
    geom = _geom()
    a = axon.render(geom, [], mode="shell")
    b = axon.render(geom, [], mode="shell", quarter_turns=0)
    assert a == b
