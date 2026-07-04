# -*- coding: utf-8 -*-
"""P5 门批次: 对开双扇 (double) 修复 + 玻璃门 material 全链。byte-safe: wood 默认,
现有数据 (全 wood, 无 double) 渲染逐字节不变 (由 golden 保); 仅新值触发新分支。"""
from floorplan_core import axon, geometry


def _op(**kw):
    base = {"id": "d", "kind": "door", "wall": {"axis": "h", "at": 100, "span": [50, 150]}}
    base.update(kw)
    return base


def test_material_defaults_wood():
    d = geometry.build_door(_op(door_type="swing", hinge="lo", swing="+"))
    assert d["material"] == "wood"  # 零迁移: 无 material 键 -> wood


def test_double_produces_two_half_leaves():
    d = geometry.build_door(_op(door_type="double", swing="+"))
    assert d["door_type"] == "double" and len(d["leaves"]) == 2
    for lf in d["leaves"]:
        assert lf["width"] == 50.0  # 半跨 (100/2)
        assert {"hinge_pt", "jamb_pt", "open_tip", "width"} <= set(lf)
    # 两扇铰接在外侧门垛 (span 两端), 中间对开
    hinges = sorted(lf["hinge_pt"][0] for lf in d["leaves"])
    assert hinges == [50.0, 150.0]


def test_double_renders_two_leaves_axon_and_2d():
    d = geometry.build_door(_op(door_type="double", swing="+"))
    _k, svg = axon.door_axon(d)
    assert svg.count("<circle") == 2  # 两把手
    svg2 = axon.door_svg_2d(d)
    assert svg2.count("door-leaf") == 2 and svg2.count("door-arc") == 2


def test_glass_door_uses_window_recipe_wood_unchanged():
    wood = geometry.build_door(_op(door_type="swing", hinge="lo", swing="+"))
    glass = geometry.build_door(_op(door_type="swing", hinge="lo", swing="+", material="glass"))
    _kw, sw = axon.door_axon(wood)
    _kg, sg = axon.door_axon(glass)
    assert "#bfe0f088" in sg and "#bfe0f088" not in sw  # 玻璃复用窗配方; wood 无玻璃色
    assert "DOOR" not in sw  # 常量已解析
    # 2D: glass 叠 inline 描边, wood 不叠 (STYLE 块不变 -> plan2d 字节安全)
    assert 'style="stroke:#7fa6bc"' in axon.door_svg_2d(glass)
    assert "style=" not in axon.door_svg_2d(wood)
