# -*- coding: utf-8 -*-
"""room-brief (Phase 1.5a): 跳过 public、尺寸 mm、门匹配到墙、furniture_options 按房。"""
import os

import pytest

from floorplan_core import geometry, room_brief

# repo 根 = tests/../../../.. (packages/floorplan_core/tests -> repo)
_REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _G():
    # 单房 1000x800px(=10000x8000mm), 北墙开一扇门 width=90px。
    return {
        "meta": {"mm_per_px": 10, "eps": 1, "origin": [0, 0]},
        "rooms": [
            {"id": "r_pub", "type": "public", "rect": [0, 0, 100, 100], "label": {"zh": "电梯厅"}},
            {"id": "r_bed", "type": "bedroom", "rect": [200, 200, 400, 300],
             "label": {"zh": "主卧"}},
        ],
    }


def _geo_with_door():
    # 在 r_bed 北墙 (y=200) 放一扇门, span 沿 x [350,440], width 90。
    return {
        "doors": [{"axis": "h", "at": 200, "span": [350, 440], "width": 90, "kind": "door"}],
        "windows": [{"axis": "v", "at": 600, "span": [300, 460], "wtype": "full", "kind": "window"}],
    }


def test_skips_public_and_dims_in_mm():
    briefs = room_brief.build_briefs(_G(), geo={"doors": [], "windows": []})
    assert [b["room_id"] for b in briefs] == ["r_bed"]  # public 跳过
    bed = briefs[0]
    assert bed["width_mm"] == 4000 and bed["depth_mm"] == 3000  # px*10
    assert bed["name"] == "主卧" and bed["type"] == "bedroom"
    assert "bed" in bed["furniture_options"]


def test_door_window_matched_to_walls():
    briefs = room_brief.build_briefs(_G(), geo=_geo_with_door())
    bed = next(b for b in briefs if b["room_id"] == "r_bed")
    assert len(bed["doors"]) == 1
    d = bed["doors"][0]
    assert d["wall"] == "N"                    # at=200=房间上沿
    assert d["center_mm"] == round((395 - 200) * 10)  # mid=395, rel=195 -> 1950mm
    assert d["width_mm"] == 900
    assert len(bed["windows"]) == 1
    assert bed["windows"][0]["wall"] == "E"    # at=600=房间右沿 (x+w=200+400)


def test_real_D_briefs():
    gpath = os.path.join(_REPO, "data", "projects", "D", "geometry.json")
    if not os.path.exists(gpath):
        pytest.skip("D 数据不在预期路径")
    G = geometry.load(gpath)
    briefs = room_brief.build_briefs(G)
    assert all(b["type"] != "public" for b in briefs)
    # 每房 dims 正; 至少有房带门; bedroom/living/wet 有家具选项
    assert all(b["width_mm"] > 0 and b["depth_mm"] > 0 for b in briefs)
    assert any(b["doors"] for b in briefs)
    by_type = {b["type"] for b in briefs}
    assert {"bedroom", "living", "wet"} & by_type


def test_derive_exposes_passages_and_brief_has_no_zero_width_doors():
    """审计 P1-4: passage 进派生; 推拉门宽度 span 兜底 (不再给 LLM 0mm 门)。"""
    import os

    from floorplan_core import geometry, room_brief

    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    G = geometry.load(os.path.join(repo, "data", "projects", "D", "geometry.json"))
    geo = geometry.derive(G)

    passages = geo.get("passages", [])
    assert passages, "D 户型应派生出通道口"
    for p in passages:
        assert p["kind"] == "passage"
        assert p["axis"] in ("v", "h") and p["at"] is not None
        assert p["span"][1] > p["span"][0]

    briefs = room_brief.build_briefs(G, geo)
    widths = [d["width_mm"] for b in briefs for d in b["doors"]]
    assert widths and all(w > 0 for w in widths)


def test_geometry_load_rejects_future_schema_version(tmp_path):
    """审计 P2-1: schema_version 从写而不读变成显式闸门 (静默错读 -> 快速失败)。"""
    import json

    import pytest
    from floorplan_core import geometry

    payload = {"meta": {"schema_version": 99}, "rooms": []}
    path = tmp_path / "g.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        geometry.load(str(path))
