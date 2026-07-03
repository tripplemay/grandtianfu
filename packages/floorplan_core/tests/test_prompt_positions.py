# -*- coding: utf-8 -*-
"""prompt_gen 房内方位 (Phase1.5b): 默认关=无方位短语, 开=每件附方位; _zone_phrase 判定。"""
from floorplan_core import prompt_gen

# 单房 100x100, 原点(0,0); 用偏移命中各分区。
_G = {
    "rooms": [{"id": "r1", "type": "bedroom", "rect": [0, 0, 100, 100],
               "label": {"zh": "主卧"}}],
}


def test_zone_phrase_regions():
    z = prompt_gen._zone_phrase
    rect = [0, 0, 90, 90]
    assert z({"dx": 0, "dy": 0, "w": 10, "h": 10}, rect) == "in the north-west corner"
    assert z({"dx": 40, "dy": 0, "w": 10, "h": 10}, rect) == "against the north wall"
    assert z({"dx": 40, "dy": 40, "w": 10, "h": 10}, rect) == "in the centre"
    assert z({"dcx": 80, "dcy": 45}, rect) == "against the east wall"
    assert z({"dcx": 80, "dcy": 80}, rect) == "in the south-east corner"


def test_positions_off_has_no_zone_phrases():
    F = [{"t": "bed", "room_id": "r1", "dx": 40, "dy": 0, "w": 18, "h": 20}]
    out = prompt_gen.generate(F, _G, with_positions=False)
    assert "a bed" in out
    for marker in ("against the", "in the centre", "corner"):
        assert marker not in out


def test_positions_on_adds_zone_phrases():
    F = [{"t": "bed", "room_id": "r1", "dx": 40, "dy": 0, "w": 18, "h": 20}]
    out = prompt_gen.generate(F, _G, with_positions=True)
    assert "a bed against the north wall" in out


def test_accepts_list_or_path_equivalently(tmp_path):
    import json
    F = [{"t": "sofa", "room_id": "r1", "dx": 10, "dy": 10, "w": 30, "h": 15}]
    p = tmp_path / "f.json"
    p.write_text(json.dumps(F), encoding="utf-8")
    assert prompt_gen.generate(F, _G) == prompt_gen.generate(str(p), _G)


def test_generate_style_injection_and_default_unchanged():
    """style 贯通 (审计 P0-6): 传 style 注入 head/palette; 不传保持既有默认文案。"""
    furniture = [{"t": "sofa", "room_id": "r1", "dx": 10, "dy": 10, "w": 20, "h": 15}]

    default = prompt_gen.generate(furniture, _G, with_positions=True)
    styled = prompt_gen.generate(furniture, _G, with_positions=True, style="日式原木,浅色木饰面")

    assert "modern light-luxury" in default
    assert "walnut wood" in default
    assert "日式原木" in styled
    assert "modern light-luxury" not in styled
    assert "walnut wood" not in styled
    assert "KEEP EXACTLY the same camera angle" in styled


def test_prompt_falls_back_to_catalog_en_for_new_types(monkeypatch):
    """升级计划 P0: TYPE_EN 未收录的类型回退 catalog.en, 提示词不漏述。"""
    from floorplan_core import catalog as _catalog

    monkeypatch.setitem(_catalog.CATALOG, "floor_lamp_x", {"en": "a floor lamp", "shape": "rect", "w": 20, "h": 20})
    F = [{"t": "floor_lamp_x", "room_id": "r1", "dx": 40, "dy": 40, "w": 20, "h": 20}]

    out = prompt_gen.generate(F, _G, with_positions=False)

    assert "a floor lamp" in out


def test_prompt_injects_wall_material_phrases():
    """墙面材质A (P1): 标注注入逐墙英文短语; 未标注输出不变 (既有测试即字节锁)。"""
    import copy

    G2 = copy.deepcopy(_G)
    G2["rooms"][0]["walls"] = {"N": {"material": "wood_panel"}, "E": {"material": "mirror"}}
    F = [{"t": "bed", "room_id": "r1", "dx": 40, "dy": 10, "w": 18, "h": 20}]

    plain = prompt_gen.generate(F, _G, with_positions=False)
    tagged = prompt_gen.generate(F, G2, with_positions=False)

    assert "north wall clad in warm walnut wood veneer paneling" in tagged
    assert "east wall clad in full-height mirror finish" in tagged
    assert "wall clad in" not in plain
