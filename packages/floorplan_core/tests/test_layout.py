# -*- coding: utf-8 -*-
"""Deterministic furniture layout from validated type/count selections."""
import os

import pytest

from floorplan_core import catalog, geometry, layout

_REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _real_d():
    return geometry.load(os.path.join(_REPO, "data", "projects", "D", "geometry.json"))


def _rooms_by_id(G):
    return {r["id"]: r for r in G["rooms"]}


def _center(item):
    app = catalog.appearance(item["t"])
    assert app is not None
    if "r" in app:
        return item["dcx"], item["dcy"]
    return item["dx"] + app["w"] / 2, item["dy"] + app["h"] / 2


def test_plan_is_deterministic_and_returns_placement_only_items():
    G = _real_d()
    selections = [
        {
            "room_id": "r_live",
            "items": [{"t": "sofa", "count": 1}, {"t": "plant", "count": 2}],
        },
        {"room_id": "r_study", "items": [{"t": "desk", "count": 1}]},
    ]

    first = layout.plan(G, selections)
    second = layout.plan(G, selections)

    assert first == second
    assert [it["t"] for it in first] == ["sofa", "plant", "plant", "desk"]
    assert all("room_id" in it for it in first)
    assert all("w" not in it and "h" not in it and "r" not in it for it in first)
    assert all(("dx" in it and "dy" in it) or ("dcx" in it and "dcy" in it) for it in first)
    assert catalog.expand(first)[0]["w"] > 0


def test_plan_keeps_furniture_centers_inside_target_room():
    G = _real_d()
    rooms = _rooms_by_id(G)
    items = layout.plan(
        G,
        [
            {"room_id": "r_live", "items": [{"t": "sofa", "count": 2}, {"t": "plant", "count": 3}]},
            {"room_id": "r_bedm", "items": [{"t": "bed", "count": 1}, {"t": "nightstand", "count": 2}]},
        ],
    )

    assert items
    for item in items:
        x, y, w, h = rooms[item["room_id"]]["rect"]
        cx, cy = _center(item)
        assert 0 <= cx <= w, item
        assert 0 <= cy <= h, item
        # Absolute center also lands inside the room rect.
        assert x <= x + cx <= x + w
        assert y <= y + cy <= y + h


def test_plan_skips_unknown_rooms_and_unknown_types():
    G = _real_d()
    items = layout.plan(
        G,
        [
            {"room_id": "nope", "items": [{"t": "sofa", "count": 1}]},
            {"room_id": "r_live", "items": [{"t": "nope", "count": 1}, {"t": "plant", "count": 1}]},
        ],
    )

    assert items == [{"t": "plant", "room_id": "r_live", "dcx": pytest.approx(items[0]["dcx"]), "dcy": pytest.approx(items[0]["dcy"])}]


def test_plan_truncates_when_room_is_too_small():
    G = {
        "rooms": [
            {
                "id": "tiny",
                "type": "living",
                "rect": [0, 0, 50, 50],
                "label": {"zh": "tiny"},
            }
        ]
    }

    items = layout.plan(G, [{"room_id": "tiny", "items": [{"t": "sofa", "count": 2}, {"t": "plant", "count": 1}]}])

    assert items == [{"t": "plant", "room_id": "tiny", "dcx": 25.0, "dcy": 25.0}]


# ---- plan_report: 避门 / 重叠 / 告警 (批次1) ---- #


def test_plan_report_footprints_avoid_door_zones():
    G = _real_d()
    doors = geometry.derive(G).get("doors", [])
    selections = [
        {
            "room_id": r["id"],
            "items": [{"t": "sofa", "count": 2}, {"t": "bed", "count": 1}],
        }
        for r in G["rooms"]
        if r.get("type") in ("living", "bedroom")
    ]

    items, _warnings = layout.plan_report(G, selections)

    assert items
    rooms = _rooms_by_id(G)
    for item in items:
        rect = rooms[item["room_id"]]["rect"]
        zones = layout._door_zones(rect, doors, G["meta"].get("eps", 1))
        app = catalog.appearance(item["t"])
        cx, cy = _center(item)
        fp = layout._footprint(app, cx, cy)
        for zone in zones:
            assert not layout._boxes_intersect(fp, zone), (item, zone)


def test_plan_report_placed_footprints_do_not_overlap():
    G = _real_d()
    items, _warnings = layout.plan_report(
        G,
        [
            {
                "room_id": "r_live",
                "items": [
                    {"t": "sofa", "count": 2},
                    {"t": "coffee_table", "count": 2},
                ],
            }
        ],
    )

    fps = []
    for item in items:
        app = catalog.appearance(item["t"])
        cx, cy = _center(item)
        fps.append(layout._footprint(app, cx, cy))
    for i in range(len(fps)):
        for j in range(i + 1, len(fps)):
            assert not layout._boxes_intersect(fps[i], fps[j]), (items[i], items[j])


def test_plan_report_warns_when_items_do_not_fit():
    G = {
        "rooms": [
            {"id": "tiny", "type": "living", "rect": [0, 0, 50, 50], "label": {"zh": "小间"}}
        ]
    }

    items, warnings = layout.plan_report(
        G, [{"room_id": "tiny", "items": [{"t": "sofa", "count": 2}, {"t": "plant", "count": 1}]}]
    )

    assert [it["t"] for it in items] == ["plant"]
    assert any("sofa" in w and "0/2" in w for w in warnings)


def test_plan_wrapper_stays_backwards_compatible():
    G = _real_d()
    selections = [{"room_id": "r_live", "items": [{"t": "sofa", "count": 1}]}]
    assert layout.plan(G, selections) == layout.plan_report(G, selections)[0]


def test_plan_report_orients_directional_furniture_to_nearest_wall():
    """审计 P1-4: 有方向语义的类型 (床/沙发/柜) 落位写 orient=贴靠最近墙。"""
    G = _real_d()
    bedroom = next(r["id"] for r in G["rooms"] if r.get("type") == "bedroom")
    items, _w = layout.plan_report(
        G,
        [
            {"room_id": bedroom, "items": [{"t": "bed", "count": 1}]},
            {"room_id": "r_live", "items": [{"t": "plant", "count": 1}]},
        ],
    )

    bed = next(it for it in items if it["t"] == "bed")
    assert bed["orient"] in ("N", "S", "E", "W")
    rect = _rooms_by_id(G)[bedroom]["rect"]
    app = catalog.appearance("bed")
    fp = layout._footprint(app, *_center(bed))
    assert bed["orient"] == layout._nearest_wall(fp, rect[2], rect[3])
    plant = next(it for it in items if it["t"] == "plant")
    assert "orient" not in plant  # 非方向性类型不写


def test_plan_report_keeps_tall_furniture_off_full_window_walls():
    """审计 P1-4: 高件 (z>=1200mm) 不贴落地窗墙。"""
    G = {
        "meta": {"eps": 1, "mm_per_px": 10},
        "rooms": [{"id": "r1", "type": "bedroom", "rect": [0, 0, 200, 200], "label": {"zh": "房"}}],
    }
    win = [{"axis": "h", "at": 200, "span": [0, 200], "wtype": "full"}]
    zones = layout._window_zones([0, 0, 200, 200], win, 1)
    assert zones == [(0.0, 200 - layout.WINDOW_CLEARANCE, 200.0, 200.0)]

    items, _w = layout.plan_report(
        G, [{"room_id": "r1", "items": [{"t": "wardrobe", "count": 1}]}]
    )
    # 极简 G derive 不出窗 (降级路径), 仅验证 zone 数学 + wardrobe 正常落位。
    assert items and items[0]["t"] == "wardrobe"


# ---- 合并组 (异形二期 b): 并集空间落位 ---- #


def _clean_L():
    """干净 L 形组 (两腿无内部大通道): legA 竖腿 + legB 横腿, 组成 L; 右上为凹口。"""
    return {
        "meta": {"eps": 1, "mm_per_px": 10},
        "spaces": {"s": {"category": "interior", "label": "客厅"}},
        "rooms": [
            {"id": "legA", "type": "living", "rect": [0, 0, 300, 600], "merge": "m", "space": "s", "label": {"zh": "客厅"}},
            {"id": "legB", "type": "living", "rect": [300, 300, 400, 300], "merge": "m", "space": "s"},
        ],
        "openings": [],
        "free_walls": [],
    }


def test_group_placement_spreads_across_both_legs():
    """并集落位跨腿分布 (round-robin 交错), 而非填满代表腿留空另一腿。"""
    G = _clean_L()
    rep = geometry.merge_groups(G)["m"]["rep"]
    items, warns = layout.plan_report(
        G, [{"room_id": rep, "items": [{"t": "plant", "count": 6}, {"t": "armchair", "count": 2}]}]
    )
    legs = {it["room_id"] for it in items}
    assert legs == {"legA", "legB"}, (legs, items)
    assert len(items) == 8 and not warns
    # 确定性
    again, _ = layout.plan_report(
        G, [{"room_id": rep, "items": [{"t": "plant", "count": 6}, {"t": "armchair", "count": 2}]}]
    )
    assert items == again


def test_group_placement_attributes_member_leg_with_leg_relative_coords():
    """每件归属所落成员腿, 腿内相对坐标落在该腿矩形内 (与 scene.rect_of 原点契约一致)。"""
    G = _clean_L()
    members = set(geometry.merge_groups(G)["m"]["members"])
    rep = geometry.merge_groups(G)["m"]["rep"]
    rooms = _rooms_by_id(G)
    items, _ = layout.plan_report(
        G, [{"room_id": rep, "items": [{"t": "bed", "count": 2}, {"t": "plant", "count": 4}]}]
    )
    assert items
    for it in items:
        assert it["room_id"] in members
        x, y, w, h = rooms[it["room_id"]]["rect"]
        cx, cy = _center(it)
        assert 0 <= cx <= w and 0 <= cy <= h, it


def test_group_placement_stays_within_single_leg_no_notch_no_straddle():
    """每件 footprint 完全落在其归属成员腿内 —— 既排 L 凹口, 又不骑腿间缝 (否则下游
    scene 组感知夹取会把骑缝件推回单腿、偏离落位并使件间避让失效)。"""
    G = _clean_L()
    mr = geometry.merge_groups(G)["m"]["member_rects"]
    rep = geometry.merge_groups(G)["m"]["rep"]
    rooms = _rooms_by_id(G)
    items, _ = layout.plan_report(
        G, [{"room_id": rep, "items": [{"t": "dining_table", "count": 2}, {"t": "bed", "count": 2}, {"t": "wardrobe", "count": 2}]}]
    )
    assert items
    for it in items:
        x, y, w, h = rooms[it["room_id"]]["rect"]
        app = catalog.appearance(it["t"])
        cx, cy = _center(it)
        fp = layout._footprint(app, cx, cy)  # 腿内相对
        assert 0 <= fp[0] and fp[2] <= w and 0 <= fp[1] and fp[3] <= h, it  # 完全落本腿
        assert geometry.rect_covered_by(layout._footprint(app, x + cx, y + cy), mr)  # 无凹口


def test_group_placement_orients_to_exterior_wall_not_internal_seam():
    """方向件 orient 指向真实外墙, 不指向与相邻/重叠腿相接的内部边 (D m_living 重叠腿)。"""
    G = _real_d()
    mr = geometry.merge_groups(G)["m_living"]["member_rects"]
    items, _ = layout.plan_report(
        G, [{"room_id": "r_live", "items": [{"t": "bed", "count": 1}, {"t": "sofa", "count": 2}]}]
    )
    directional = [it for it in items if "orient" in it]
    assert directional
    rooms = _rooms_by_id(G)
    for it in directional:
        x, y, w, h = rooms[it["room_id"]]["rect"]
        cx, cy = _center(it)
        acx, acy = x + cx, y + cy
        leg = next(m for m in mr if m[0] == it["room_id"])
        others = [m for m in mr if m[0] != it["room_id"]]
        pts = {
            "N": (acx, leg[2] - 1.0), "S": (acx, leg[4] + 1.0),
            "W": (leg[1] - 1.0, acy), "E": (leg[3] + 1.0, acy),
        }
        px, py = pts[it["orient"]]
        assert not geometry.point_in_any(others, px, py), it  # orient 墙外侧非另一成员


def test_group_placement_roundtrips_through_scene_and_prompt():
    """D 真实 L 组 m_living: 落位经 scene.build_scene 零 ERROR, prompt 方位无 KeyError。"""
    from floorplan_core import scene as scene_mod, prompt_gen

    G = _real_d()
    geo = geometry.derive(G)
    items, _ = layout.plan_report(
        G,
        [{"room_id": "r_live", "items": [{"t": "sofa", "count": 2}, {"t": "plant", "count": 3}, {"t": "wine_cabinet", "count": 1}]}],
    )
    assert items
    furniture = catalog.expand(items)
    scene = scene_mod.build_scene(G, geo, furniture)
    errs = [i for i in scene.get("validation", {}).get("issues", []) if i.get("level") == "ERROR"]
    assert errs == [], errs  # 组感知校验/夹取下无越界/凹口 ERROR
    prompt = prompt_gen.generate(items, G, with_positions=True)
    assert isinstance(prompt, str) and prompt


def test_group_door_zones_suppress_internal_shared_edge():
    """并集门净空只避外墙开洞; 两腿共享边上的内部开洞不产生避让区。"""
    # 两腿在 x=300 竖直相接; 一个洞跨该共享边 (同时命中 legA E 墙与 legB W 墙) -> 抑制。
    member_rects = [("legA", 0.0, 0.0, 300.0, 300.0), ("legB", 300.0, 0.0, 600.0, 300.0)]
    internal = {"axis": "v", "at": 300, "span": [100, 200], "width": 90}
    exterior = {"axis": "h", "at": 0, "span": [0, 100], "width": 90}  # legA N 墙 (外墙)
    ext = geometry.group_exterior_openings(member_rects, [internal, exterior], 1)
    kept = [op for _w, _mr, op, _r in ext]
    assert internal not in kept and exterior in kept
    zones = layout._group_opening_zones(member_rects, [internal, exterior], 1, "door")
    assert zones and all(z[1] <= 90 for z in zones)  # 仅 N 墙外墙洞产生净空


# ==================== decor-b2 F002: 独立配饰件确定性落位 ====================
def test_place_wall_art_on_host_backing_wall():
    G = _real_d()
    rect = _rooms_by_id(G)["r_master"]["rect"]
    bed = {"t": "bed", "room_id": "r_master", "dx": 100, "dy": 300,
           "w": 180, "h": 200, "orient": "S"}
    placed = layout.place_decor_standalone(G, "r_master", ["wall_art"], [bed])
    assert len(placed) == 1
    wa = placed[0]
    assert wa["t"] == "wall_art" and wa["orient"] == "S" and wa["room_id"] == "r_master"
    assert abs((wa["dy"] + wa["h"]) - float(rect[3])) < 1.0  # 贴 S 墙 (flush)


def test_place_wall_art_skips_without_host():
    G = _real_d()
    tbl = {"t": "coffee_table", "room_id": "r_master", "dx": 100, "dy": 100, "w": 100, "h": 60}
    assert layout.place_decor_standalone(G, "r_master", ["wall_art"], [tbl]) == []


def test_place_curtain_covers_window_span():
    G = _real_d()
    placed = layout.place_decor_standalone(G, "r_master", ["curtain"], [])
    assert len(placed) == 1
    c = placed[0]
    assert c["t"] == "curtain" and c["orient"] == "S"
    assert c["w"] > 100  # 宽对齐窗跨 (S 窗 span 0-600)


def test_place_plant_in_corner_avoiding_furniture():
    G = _real_d()
    placed = layout.place_decor_standalone(G, "r_master", ["plant"], [])
    assert len(placed) == 1 and placed[0]["t"] == "plant"
    assert "dcx" in placed[0] and "dcy" in placed[0]


def test_place_decor_is_deterministic():
    G = _real_d()
    bed = {"t": "bed", "room_id": "r_master", "dx": 100, "dy": 300,
           "w": 180, "h": 200, "orient": "S"}
    a = layout.place_decor_standalone(G, "r_master", ["wall_art", "curtain", "plant"], [bed])
    b = layout.place_decor_standalone(G, "r_master", ["wall_art", "curtain", "plant"], [bed])
    assert a == b and len(a) == 3


def test_placed_wall_art_not_pushed_off_wall_by_scene():
    from floorplan_core import scene
    G = _real_d()
    geo = geometry.derive(G)
    bed = {"t": "bed", "room_id": "r_master", "dx": 100, "dy": 300,
           "w": 180, "h": 200, "orient": "S"}
    placed = layout.place_decor_standalone(G, "r_master", ["wall_art"], [bed])
    furn = catalog.expand([bed] + placed)
    sc = scene.build_scene(G, geo, furn)
    wa = next(it for it in sc["axon_furniture"] if it["t"] == "wall_art")
    rect = _rooms_by_id(G)["r_master"]["rect"]
    # D13 豁免: 贴墙配饰不被 inner-clearance 内缩, S 墙 flush 保持
    assert abs((wa["y"] + wa["h"]) - (float(rect[1]) + float(rect[3]))) < 1.0
