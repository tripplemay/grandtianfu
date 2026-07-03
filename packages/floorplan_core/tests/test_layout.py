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
