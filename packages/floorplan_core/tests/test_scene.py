# -*- coding: utf-8 -*-
"""Canonical scene validation and axon wall-clearance regression tests."""
from __future__ import annotations

import json
from pathlib import Path

from floorplan_core import axon, geometry


REPO = Path(__file__).resolve().parents[3]


def _live_scene():
    G = geometry.load(REPO / "data" / "projects" / "D" / "baselines" / "v1" / "geometry.json")
    geo = geometry.derive(G)
    furniture = json.loads(
        (REPO / "data" / "projects" / "D" / "schemes" / "default" / "furniture.json").read_text(
            encoding="utf-8"
        )
    )
    return G, geo, furniture, axon.build_scene(
        G,
        geo,
        furniture,
        project_id="D",
        baseline_version_id="v1",
        scheme_id="default",
    )


def test_cloak_wardrobes_are_inset_and_height_clamped_for_axon_without_mutating_plan_coords():
    G, geo, furniture, scene = _live_scene()

    assert scene["validation"]["ok"], scene["validation"]["errors"]
    assert scene["units"]["wall_height_mm"] == 1450
    assert scene["units"]["max_furniture_height_mm"] == 1400
    assert not [
        issue
        for issue in scene["validation"]["issues"]
        if issue["level"] == "ERROR" and issue["code"] == "AXON_WALL_THICKNESS_COLLISION"
    ]

    raw_cloak = [
        item
        for item in scene["furniture"]
        if item.get("_room_id") == "r_cloak" and item.get("t") == "wardrobe"
    ]
    axon_cloak = [
        item
        for item in scene["axon_furniture"]
        if item.get("_room_id") == "r_cloak" and item.get("t") == "wardrobe"
    ]
    assert [(it["x"], it["y"]) for it in raw_cloak] == [(1220, 685), (1475, 885)]
    assert [(it["x"], it["y"]) for it in axon_cloak] == [(1228.0, 693.0), (1464.0, 877.0)]
    assert [it["z"] for it in raw_cloak] == [1400, 1400]
    assert [it["z"] for it in axon_cloak] == [1400, 1400]
    assert not [
        issue
        for issue in scene["validation"]["issues"]
        if issue["code"].endswith("_HEIGHT_EXCEEDS_WALL")
    ]

    plan = axon.render_plan_2d(G, geo, furniture)
    assert 'x="1220" y="685" width="40" height="330"' in plan
    assert 'x="1475" y="885" width="38" height="130"' in plan


def test_dangling_room_blocks_scene_validation():
    G, geo, furniture, _scene = _live_scene()
    bad = [*furniture, {"t": "wardrobe", "w": 40, "h": 80, "room_id": "r_missing", "dx": 0, "dy": 0}]
    scene = axon.build_scene(G, geo, bad)
    assert not scene["validation"]["ok"]
    assert any(issue["code"] == "DANGLING_FURNITURE_ROOM" for issue in scene["validation"]["errors"])


def test_axon_oversized_bbox_is_normalized_instead_of_blocking():
    G, geo, _furniture, _scene = _live_scene()
    bad = [{"t": "wardrobe", "w": 1000, "h": 80, "room_id": "r_cloak", "dx": 0, "dy": 20}]
    scene = axon.build_scene(G, geo, bad)
    assert scene["validation"]["ok"], scene["validation"]["errors"]
    assert scene["axon_furniture"][0]["w"] == 274
    assert not any(issue["code"] == "AXON_OUTSIDE_ROOM_BBOX" for issue in scene["validation"]["errors"])


def test_scene_clamps_explicit_and_renderer_default_tall_furniture_heights():
    G, geo, _furniture, _scene = _live_scene()
    sample = [
        {"t": "wardrobe", "w": 40, "h": 80, "z": 2000, "room_id": "r_cloak", "dx": 40, "dy": 40},
        {"t": "washer_dryer", "w": 68, "h": 80, "room_id": "r_balc", "dx": 40, "dy": 40},
        {"t": "shower", "w": 95, "h": 120, "room_id": "r_mbath", "dx": 40, "dy": 40},
    ]
    scene = axon.build_scene(G, geo, sample)

    assert scene["validation"]["ok"], scene["validation"]["errors"]
    assert [item["z"] for item in scene["axon_furniture"]] == [1400, 1400, 1400]
    assert any(
        issue["code"] == "RAW_HEIGHT_EXCEEDS_WALL"
        and issue["index"] == 0
        and issue["height"] == 2000
        and issue["max_height"] == 1400
        for issue in scene["validation"]["warnings"]
    )
    assert not [
        issue
        for issue in scene["validation"]["issues"]
        if issue["level"] == "ERROR" and issue["code"] == "AXON_HEIGHT_EXCEEDS_WALL"
    ]


def test_scene_uses_wall_bbox_second_pass_when_room_clearance_is_zero():
    G, geo, furniture, _scene = _live_scene()
    scene = axon.build_scene(G, geo, furniture, wall_clearance=0)

    assert scene["validation"]["ok"], scene["validation"]["errors"]
    assert not [
        issue
        for issue in scene["validation"]["issues"]
        if issue["level"] == "ERROR" and issue["code"] == "AXON_WALL_THICKNESS_COLLISION"
    ]
    assert any(
        "axon-wall-avoid" in note
        for adj in scene["validation"]["adjustments"]
        for note in adj["notes"]
    )


def test_scene_shrinks_oversized_axon_furniture_before_validation():
    G, geo, _furniture, _scene = _live_scene()
    scene = axon.build_scene(
        G,
        geo,
        [{"t": "wardrobe", "w": 520, "h": 520, "z": 2000, "room_id": "r_cloak", "dx": -80, "dy": -90}],
    )

    assert scene["validation"]["ok"], scene["validation"]["errors"]
    ax_item = scene["axon_furniture"][0]
    assert ax_item["w"] == 274
    assert ax_item["h"] == 243
    assert ax_item["z"] == 1400
    assert not [
        issue
        for issue in scene["validation"]["issues"]
        if issue["level"] == "ERROR"
    ]
    assert any(
        "axon-size-clamp" in note
        for adj in scene["validation"]["adjustments"]
        for note in adj["notes"]
    )


def test_circle_furniture_wall_collision_downgrades_to_warn_not_error():
    """圆形件 (cx/cy/r) 不经归一化无法自愈, 贴墙碰撞应为 WARN 而非 ERROR 硬阻断。"""
    G = geometry.load(REPO / "data" / "projects" / "D" / "baselines" / "v1" / "geometry.json")
    geo = geometry.derive(G)
    room = G["rooms"][0]
    furniture = [
        # dcx=0 → 圆心贴房间左边缘, footprint 必与墙厚相交。
        {"t": "plant", "room_id": room["id"], "dcx": 0, "dcy": room["rect"][3] / 2, "r": 12}
    ]

    scene = axon.build_scene(G, geo, furniture)

    collisions = [
        issue
        for issue in scene["validation"]["issues"]
        if issue["code"] == "AXON_WALL_THICKNESS_COLLISION"
    ]
    assert collisions, "贴墙圆件应命中墙碰撞检测"
    assert all(issue["level"] == "WARN" for issue in collisions)
    assert not [
        issue
        for issue in scene["validation"]["errors"]
        if issue["code"] == "AXON_WALL_THICKNESS_COLLISION"
    ]


def test_slice_geom_for_room_narrows_rooms_walls_and_openings():
    """第7步按房切片: 单间照片配单间轴测参考 (审计 P0-3 / Phase1.5c)。"""
    G = geometry.load(REPO / "data" / "projects" / "D" / "baselines" / "v1" / "geometry.json")
    geo = geometry.derive(G)
    geom = axon.geom_bundle(G, geo)
    room = next(r for r in G["rooms"] if r.get("type") in ("living", "bedroom"))

    sliced = axon.slice_geom_for_room(geom, room["id"])

    rooms_s, walls_s, doors_s, windows_s, dims_s, ann_s, G_s = sliced
    assert len(rooms_s) == 1 and [r["id"] for r in G_s["rooms"]] == [room["id"]]
    assert 0 < len(walls_s) < len(geom[1])
    assert dims_s == {} and ann_s == []
    # 确定性 + 不改入参
    assert axon.slice_geom_for_room(geom, room["id"]) == sliced
    assert len(geom[0]) == len(G["rooms"])

    # 切片后可渲染, viewBox 收紧到单间 (宽度显著小于整宅)。
    import re

    # axon_furniture 形态: 绝对 x/y + _room_id (resolve 后 room_id 已剥离)。
    furn = [
        {"t": "sofa", "x": room["rect"][0] + 30, "y": room["rect"][1] + 30,
         "w": 60, "h": 40, "_room_id": room["id"]}
    ]
    svg_room = axon.render(sliced, furn, mode="photo")
    svg_house = axon.render(geom, furn, mode="photo")
    wb_room = float(re.search(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+)', svg_room).group(1))
    wb_house = float(re.search(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+)', svg_house).group(1))
    assert wb_room < wb_house * 0.7

    import pytest as _pytest

    with _pytest.raises(ValueError):
        axon.slice_geom_for_room(geom, "nope")


def test_axon_items_carry_adjusted_room_relative_coords():
    """审计 P1-8: 归一化后回填 _dx/_dy, 供提示词方位与底图一致。"""
    G, geo, furniture, scene = _live_scene()

    for it in scene["axon_furniture"]:
        rid = it.get("_room_id")
        if rid is None:
            continue
        rect = next(r["rect"] for r in G["rooms"] if r["id"] == rid)
        if "x" in it:
            assert it["_dx"] == it["x"] - rect[0]
            assert it["_dy"] == it["y"] - rect[1]
        elif "cx" in it:
            assert it["_dcx"] == it["cx"] - rect[0]


def test_build_scene_rejects_non_default_mm_per_px():
    """审计 P1-6: axon 常量按 10mm/px 标定, 非 10 显式失败优于静默错比例。"""
    import pytest as _pytest

    G = {"meta": {"mm_per_px": 5}, "rooms": [{"id": "r1", "type": "living", "rect": [0, 0, 100, 100]}]}
    with _pytest.raises(ValueError):
        axon.build_scene(G, {"walls": [], "doors": [], "windows": [], "dims": {}}, [])
