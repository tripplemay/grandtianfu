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
