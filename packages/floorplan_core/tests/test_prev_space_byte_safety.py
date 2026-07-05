# -*- coding: utf-8 -*-
"""CP5v2 贴合并房升级: rooms[].prev_space 编辑器元数据字节安全护栏.

前端并房时会在被并房间上写 prev_space 快照 (供「分隔」还原原名称/类别)。
引擎全链路不读该键 —— 本测试锁死: 同一几何加不加 prev_space, derive() 与
plan2d 出图逐字节一致, validate() 结论不变。数据真源 = data/projects/D 活几何。
"""
from __future__ import annotations

import copy
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
GEOM_JSON = os.path.join(REPO, "data", "projects", "D", "geometry.json")

from floorplan_core import axon, geometry  # noqa: E402


def _with_prev_space(G):
    """深拷贝并给每个房间打上 prev_space/prev_type 快照 (模拟前端并房后落盘)。"""
    G2 = copy.deepcopy(G)
    for r in G2["rooms"]:
        r["prev_space"] = {
            "id": "sp-old",
            "label": "原空间",
            "category": "interior",
            "style": "solid",
        }
        r["prev_type"] = "bedroom"
        r["prev_label"] = "原房间名"
    return G2


def test_prev_space_derive_byte_safe():
    G = geometry.load(GEOM_JSON)
    G2 = _with_prev_space(G)
    d1 = geometry.derive(G)
    d2 = geometry.derive(G2)
    assert json.dumps(d1, sort_keys=True, ensure_ascii=False) == json.dumps(
        d2, sort_keys=True, ensure_ascii=False
    )


def test_prev_space_plan2d_byte_safe():
    G = geometry.load(GEOM_JSON)
    G2 = _with_prev_space(G)
    svg1 = axon.render_plan_2d(G, geometry.derive(G), [])
    svg2 = axon.render_plan_2d(G2, geometry.derive(G2), [])
    assert svg1 == svg2


def test_prev_space_validate_unchanged():
    G = geometry.load(GEOM_JSON)
    G2 = _with_prev_space(G)
    assert geometry.validate(G) == geometry.validate(G2)
