# -*- coding: utf-8 -*-
"""声明式俯视外形解释器 (Phase C-3): edge/arms/inner/doors 按 orient 定位的几何。"""
from floorplan_core import plan2d_shapes as ps


def _rects(prims):
    return [p for p in prims if p["k"] == "rect"]


def test_edge_on_each_orient_side():
    # footprint 0,0,100,80。edge depth 0.2 贴 orient 边。
    n = ps.detail_prims(0, 0, 100, 80, "N", [{"k": "edge", "depth": 0.2}])[0]
    assert (n["x"], n["y"], n["w"], n["h"]) == (0, 0, 100, 16)  # 顶边
    s = ps.detail_prims(0, 0, 100, 80, "S", [{"k": "edge", "depth": 0.2}])[0]
    assert (s["x"], s["y"], s["w"], s["h"]) == (0, 64, 100, 16)  # 底边
    w = ps.detail_prims(0, 0, 100, 80, "W", [{"k": "edge", "depth": 0.2}])[0]
    assert (w["x"], w["y"], w["w"], w["h"]) == (0, 0, 20, 80)  # 左边
    e = ps.detail_prims(0, 0, 100, 80, "E", [{"k": "edge", "depth": 0.2}])[0]
    assert (e["x"], e["y"], e["w"], e["h"]) == (80, 0, 20, 80)  # 右边


def test_orient_defaults_to_north_when_absent_or_invalid():
    a = ps.detail_prims(0, 0, 100, 80, None, [{"k": "edge", "depth": 0.2}])[0]
    b = ps.detail_prims(0, 0, 100, 80, "X", [{"k": "edge", "depth": 0.2}])[0]
    assert a["y"] == 0 and b["y"] == 0  # 都当作 N (顶边)


def test_arms_vertical_back_are_left_and_right():
    # orient N -> 竖向靠背, 扶手在左右, 从顶部沿 y 伸出。
    arms = _rects(ps.detail_prims(0, 0, 100, 80, "N", [{"k": "arms", "depth": 0.75, "width": 0.1}]))
    assert len(arms) == 2
    left, right = sorted(arms, key=lambda r: r["x"])
    assert left["x"] == 0 and right["x"] == 90  # 左右两侧
    assert left["y"] == 0 and left["h"] == 60  # 从顶伸出 0.75*80


def test_arms_horizontal_back_are_top_and_bottom():
    arms = _rects(ps.detail_prims(0, 0, 100, 80, "W", [{"k": "arms", "depth": 0.75, "width": 0.1}]))
    top, bot = sorted(arms, key=lambda r: r["y"])
    assert top["y"] == 0 and bot["y"] == 72  # 上下两侧 (0.9*80)
    assert top["x"] == 0 and top["w"] == 75  # 从左伸出 0.75*100


def test_inner_is_hollow_inset_rect():
    inner = ps.detail_prims(0, 0, 100, 80, "N", [{"k": "inner", "inset": [0.1, 0.2, 0.1, 0.1], "rx": 5}])[0]
    assert inner["hollow"] is True and inner["rx"] == 5
    assert (round(inner["x"], 3), round(inner["y"], 3)) == (10, 16)
    assert (round(inner["w"], 3), round(inner["h"], 3)) == (80, 56)  # w*(1-0.2), h*(1-0.3)


def test_inner_inset_rotates_with_orient():
    # inset t=0.2 是靠 orient 边的留白, 应随 orient 旋转 (与 edge 同侧, 不越到错轴)。
    spec = [{"k": "inner", "inset": [0.1, 0.2, 0.1, 0.1]}]
    # orient E: 靠右留白 0.2 -> 右侧 gap, 内胎 x∈[10,80]。
    e = ps.detail_prims(0, 0, 100, 80, "E", spec)[0]
    assert round(e["x"], 3) == 10 and round(e["w"], 3) == 70  # 右留 0.2, 左留 0.1
    assert round(e["y"], 3) == 8 and round(e["h"], 3) == 64  # 上下各 0.1
    # orient S: 靠下留白 0.2 -> 底部 gap。
    s = ps.detail_prims(0, 0, 100, 80, "S", spec)[0]
    assert round(s["y"], 3) == 8 and round(s["h"], 3) == 56  # 下留 0.2, 上留 0.1 -> h*(1-0.3)


def test_doors_divide_across_wall_axis():
    # orient N (墙水平) -> 竖线沿宽度等分。
    lines = [p for p in ps.detail_prims(0, 0, 90, 60, "N", [{"k": "doors", "n": 3}]) if p["k"] == "line"]
    assert len(lines) == 2
    assert [round(l["x1"]) for l in lines] == [30, 60] and all(l["y1"] == 0 and l["y2"] == 60 for l in lines)
    # orient W (墙竖直) -> 横线沿高度等分。
    hlines = [p for p in ps.detail_prims(0, 0, 90, 60, "W", [{"k": "doors", "n": 2}]) if p["k"] == "line"]
    assert len(hlines) == 1 and hlines[0]["y1"] == 30 and hlines[0]["x1"] == 0
