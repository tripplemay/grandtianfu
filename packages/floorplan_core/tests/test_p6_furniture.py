# -*- coding: utf-8 -*-
"""P6 第二批 7 类家具 (补至 45+ 类): bunk_bed(spec) + 复用基元 6 类。byte-safe: 新类型不在
D 数据 -> golden 不受影响 (catalog 扩充不改现有类型渲染)。"""
from floorplan_core import axon, catalog

NEW = ["bunk_bed", "crib", "desk_chair", "bar_stool", "console_table", "coat_rack", "bidet"]


def _item(t):
    s = catalog.CATALOG[t]
    it = {"t": t, "x": 100, "y": 100, "w": s["w"], "h": s["h"], "orient": "N"}
    if "color" in s:
        it["color"] = s["color"]
    if "z" in s:
        it["z"] = s["z"]
    return it


def test_p6_types_registered_and_render_under_wall():
    for t in NEW:
        assert t in catalog.CATALOG, f"{t} 缺目录条目"
        assert t in axon.MODELS, f"{t} 缺 MODELS 渲染器"
        boxes, _extra = axon.MODELS[t](_item(t))
        assert boxes, f"{t} 无 box"
        for b in boxes:
            x0, y0, x1, y1, z0, z1, color = b
            assert x1 > x0 and y1 > y0 and z1 > z0, f"{t} 退化盒"
            assert z1 <= 1450, f"{t} z1={z1} 穿墙"


def test_p6_types_served_by_api():
    by_t = {e["t"]: e for e in catalog.to_public()}
    for t in NEW:
        assert t in by_t and by_t[t]["zh"] and by_t[t]["category"]
    # bunk_bed 是床类 (bedroom, directional); bidet 卫浴
    assert "bedroom" in by_t["bunk_bed"]["rooms"]
    assert by_t["bidet"]["rooms"] == ["wet"]


def test_catalog_reached_target_count():
    # 原 25 + P2(12+rug+round_chair=14) + P6(7) = 46 (计划 ~45 类)
    assert len(catalog.CATALOG) >= 45
