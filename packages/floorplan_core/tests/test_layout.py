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
