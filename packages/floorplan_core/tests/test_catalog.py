# -*- coding: utf-8 -*-
"""家具目录 (Phase 1.5a): 类型可渲染、expand 填默认且幂等、按房过滤。"""
from floorplan_core import axon, catalog


def test_every_catalog_type_is_renderable():
    """矩形目录类型必在 axon.MODELS (inline 件如 rug 走渲染器内联路径除外);
    圆形件走独立圆形渲染路径 (draw_round)。"""
    rect_types = {
        t for t, s in catalog.CATALOG.items()
        if s["shape"] == "rect" and not s.get("inline")
    }
    missing = rect_types - set(axon.MODELS)
    assert not missing, f"矩形目录类型缺渲染器: {missing}"
    # 圆形件由 draw_round 统一渲染 (不入 MODELS); 目录派生集合应与 shape 判定一致。
    round_types = {t for t, s in catalog.CATALOG.items() if s["shape"] == "round"}
    assert round_types == set(catalog.ROUND_TYPES)
    assert {"plant", "round_table"} <= round_types  # D 渲染已证可出的基线圆形件


def test_types_for_room():
    assert "bed" in catalog.types_for_room("bedroom")
    assert "sofa" in catalog.types_for_room("living")
    assert "vanity" in catalog.types_for_room("wet")
    assert catalog.types_for_room("public") == []  # 公共区无软装


def test_appearance_rect_and_round():
    bed = catalog.appearance("bed")
    assert bed == {"w": 180, "h": 200}
    plant = catalog.appearance("plant")
    assert plant == {"r": 20}
    nightstand = catalog.appearance("nightstand")
    assert nightstand["z"] == 470 and nightstand["color"] == "#8a633e"
    assert catalog.appearance("nope") is None


def test_expand_fills_placement_only_item():
    placed = [{"t": "bed", "room_id": "r1", "dx": 10, "dy": 20}]
    full = catalog.expand(placed)
    assert full[0]["w"] == 180 and full[0]["h"] == 200
    assert full[0]["room_id"] == "r1" and full[0]["dx"] == 10  # 摆放保留
    assert placed[0] == {"t": "bed", "room_id": "r1", "dx": 10, "dy": 20}  # 不改入参


def test_expand_idempotent_on_full_item():
    full = [{"t": "bed", "room_id": "r1", "dx": 0, "dy": 0, "w": 160, "h": 200, "color": "#abc"}]
    again = catalog.expand(full)
    assert again[0]["w"] == 160 and again[0]["color"] == "#abc"  # 不覆盖已有


def test_expand_passes_unknown_type():
    out = catalog.expand([{"t": "partition", "x": 0, "y": 0, "w": 5, "h": 5}])
    assert out[0]["t"] == "partition"
