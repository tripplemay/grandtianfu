# -*- coding: utf-8 -*-
"""resolve_furniture: 正常解析、无 room_id 透传、悬挂 room_id 跳过(不抛错)。

回归保护生产 bug: 编辑器删/改房后残留的悬挂家具件曾让 render 整体 500 (画廊全黑)。
"""
from floorplan_core import axon

_G = {"rooms": [{"id": "r1", "rect": [100, 200, 300, 400]}]}


def test_resolves_relative_to_room_origin():
    out = axon.resolve_furniture([{"t": "bed", "room_id": "r1", "dx": 10, "dy": 20}], _G)
    assert out == [{"t": "bed", "x": 110, "y": 220}]


def test_round_item_uses_dcx_dcy():
    out = axon.resolve_furniture([{"t": "plant", "room_id": "r1", "dcx": 5, "dcy": 7}], _G)
    assert out[0]["cx"] == 105 and out[0]["cy"] == 207


def test_legacy_absolute_item_passthrough():
    item = {"t": "rug", "x": 1, "y": 2}
    assert axon.resolve_furniture([item], _G) == [item]


def test_dangling_room_id_is_skipped_not_raised():
    F = [
        {"t": "bed", "room_id": "r1", "dx": 0, "dy": 0},
        {"t": "plant", "room_id": "r_ghost", "dcx": 5, "dcy": 5},  # 悬挂
        {"t": "plant", "room_id": "r_ghost", "dx": 1, "dy": 1},    # 悬挂
    ]
    out = axon.resolve_furniture(F, _G)
    assert len(out) == 1  # 仅保留有效件, 2 悬挂件被跳过
    assert out[0]["t"] == "bed"
