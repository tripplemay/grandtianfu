# -*- coding: utf-8 -*-
"""compile_brief: 结构化设计 Brief -> 紧凑英文片段 (工作流改造 B3)。"""
from floorplan_core.brief_prompt import compile_brief


def test_empty_returns_empty_string():
    assert compile_brief(None) == ""
    assert compile_brief({}) == ""
    assert compile_brief("not a dict") == ""  # type: ignore[arg-type]
    # 全空字段 -> 无 segment -> 空串。
    assert compile_brief({"occupants": "  ", "primary_materials": [], "keep_hardscape": False}) == ""


def test_single_string_field():
    out = compile_brief({"style_direction": "日式原木自然风"})
    assert out == "Design brief — style direction: 日式原木自然风."


def test_list_field_joined():
    out = compile_brief({"primary_materials": ["oak", "travertine", "  "]})
    assert "preferred materials: oak, travertine" in out
    assert out.startswith("Design brief — ")
    assert out.endswith(".")


def test_keep_hardscape_phrase():
    assert "keep the existing hardscape" in compile_brief({"keep_hardscape": True})
    assert "keep the existing hardscape" not in compile_brief({"keep_hardscape": False})
    assert "hardscape" not in compile_brief({"occupants": "young couple"})


def test_deterministic_order_and_full_brief():
    brief = {
        "occupants": "three-person family",
        "budget_tier": "mid-high",
        "style_direction": "modern light-luxury",
        "keep_hardscape": True,
        "primary_materials": ["walnut"],
        "banned_materials": ["chrome"],
        "primary_colors": ["beige"],
        "banned_colors": ["neon"],
        "focus_rooms": ["living room", "master"],
        "avoid_elements": ["clutter"],
    }
    out = compile_brief(brief)
    # 顺序固定: residents < budget < style < keep < 各列表段。
    order = [
        "target residents: three-person family",
        "budget tier: mid-high",
        "style direction: modern light-luxury",
        "keep the existing hardscape and architecture unchanged",
        "preferred materials: walnut",
        "avoid materials: chrome",
        "preferred colors: beige",
        "avoid colors: neon",
        "focus rooms: living room, master",
        "avoid: clutter",
    ]
    positions = [out.index(seg) for seg in order]
    assert positions == sorted(positions), out
    # 同一 brief 编译两次结果一致 (确定性)。
    assert compile_brief(brief) == out


def test_decor_preferences_field():
    # decor-b2 F005: 配饰偏好字段编译进 prompt (soft furnishing preferences)。
    out = compile_brief({"decor_preferences": ["少量挂画", "绿植点缀"]})
    assert "soft furnishing preferences: 少量挂画, 绿植点缀" in out
    # 缺省时不出现 (byte-safe, 保护历史 brief)
    assert "soft furnishing" not in compile_brief({"occupants": "young couple"})
