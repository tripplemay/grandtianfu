# -*- coding: utf-8 -*-
"""布局 lint (设计质量体检) 单测: 悬空/背贴落地窗/家具碰撞 + 真实 D 布局零误报。"""

from __future__ import annotations

import json
from pathlib import Path

from floorplan_core import axon, geometry, lint

REPO = Path(__file__).resolve().parents[3]


def _live_scene(furniture):
    G = geometry.load(REPO / "data" / "projects" / "D" / "geometry.json")
    geo = geometry.derive(G)
    return G, geo, axon.build_scene(G, geo, furniture, project_id="D")


def _default_furniture():
    return json.loads(
        (REPO / "data" / "projects" / "D" / "furniture.json").read_text(encoding="utf-8")
    )


def test_shipped_d_layout_is_lint_clean():
    """定稿平面 = 布局质量基准: 现有布局须零问题 (否则默认场景出图/部署门禁被误拦)。"""
    _G, _geo, scene = _live_scene(_default_furniture())
    result = lint.lint_layout(scene)
    assert result["ok"], result["issues"]
    assert result["issues"] == []


def test_scheme_default_furniture_is_lint_clean():
    """方案级 default furniture (部署默认场景门禁渲染的那份) 同样须零问题。"""
    furniture = json.loads(
        (REPO / "data" / "projects" / "D" / "schemes" / "default" / "furniture.json").read_text(
            encoding="utf-8"
        )
    )
    G = geometry.load(REPO / "data" / "projects" / "D" / "baselines" / "v1" / "geometry.json")
    geo = geometry.derive(G)
    scene = axon.build_scene(G, geo, furniture, project_id="D", baseline_version_id="v1")
    result = lint.lint_layout(scene)
    assert result["ok"], result["issues"]


def test_wall_unit_floating_in_room_center_flagged():
    """柜类墙靠件悬空于房间中央 -> LAYOUT_WALL_UNIT_FLOATING (酒柜立于动线中央的生产病灶)。"""
    furniture = _default_furniture() + [
        {"t": "wine_cabinet", "w": 60, "h": 40, "room_id": "r_live", "dx": 350, "dy": 350}
    ]
    _G, _geo, scene = _live_scene(furniture)
    result = lint.lint_layout(scene)
    codes = [i["code"] for i in result["issues"]]
    assert "LAYOUT_WALL_UNIT_FLOATING" in codes
    assert not result["ok"]
    floated = next(i for i in result["issues"] if i["code"] == "LAYOUT_WALL_UNIT_FLOATING")
    assert floated["level"] == "WARN"
    assert floated["room_id"] == "r_live"
    assert floated["wall_gap_mm"] >= 1000  # 距墙 >= 1m


def test_sofa_floating_in_living_is_allowed():
    """客厅沙发面对电视悬空 = 合法布局, 不触发悬空规则 (悬空仅对柜类墙靠件)。"""
    # 默认 D 客厅两张沙发本就悬空 128~158px, 已由 test_shipped_d_layout_is_lint_clean 覆盖;
    # 此处显式再放一张悬空沙发确认不误报。
    furniture = _default_furniture() + [
        {"t": "sofa", "w": 210, "h": 90, "room_id": "r_live", "dx": 300, "dy": 300}
    ]
    _G, _geo, scene = _live_scene(furniture)
    result = lint.lint_layout(scene)
    assert not any(i["code"] == "LAYOUT_WALL_UNIT_FLOATING" for i in result["issues"])


def test_large_piece_backing_glass_curtain_wall_flagged():
    """衣柜背贴 6m 落地窗 (主卧 w02 玻璃幕墙) -> LAYOUT_LARGE_BACKS_FULL_WINDOW。"""
    # 主卧 rect [1215,1020,600,390], 南墙 y=1410 有 w02 (span 1215-1815=6m 落地窗)。
    master_y = 1020
    furniture = _default_furniture() + [
        {
            "t": "wardrobe",
            "w": 120,
            "h": 60,
            "room_id": "r_master",
            "dx": 200,
            "dy": (1410 - 1) - master_y - 60,
        }
    ]
    _G, _geo, scene = _live_scene(furniture)
    result = lint.lint_layout(scene)
    backs = [i for i in result["issues"] if i["code"] == "LAYOUT_LARGE_BACKS_FULL_WINDOW"]
    assert backs, result["issues"]
    assert backs[0]["window_id"] == "w02"
    assert backs[0]["room_id"] == "r_master"


def test_small_decorative_full_window_does_not_flag():
    """玄关矮柜置于 1.6m 装饰落地窗下 (w13) = D 定稿设计, 不触发背贴落地窗 (仅拦≥3m玻璃幕墙)。

    该配置就在真实 D 布局中 (r_vest cabinet), 由 test_shipped_d_layout_is_lint_clean 保证零命中;
    此处显式断言 window span < WINDOW_MIN_SPAN_PX 的窗不参与判定。
    """
    _G, _geo, scene = _live_scene(_default_furniture())
    result = lint.lint_layout(scene)
    assert not any(i["code"] == "LAYOUT_LARGE_BACKS_FULL_WINDOW" for i in result["issues"])


def test_significant_furniture_overlap_flagged():
    """两大件明显重叠 -> LAYOUT_FURNITURE_OVERLAP。"""
    furniture = _default_furniture() + [
        {"t": "bed", "w": 180, "h": 200, "room_id": "r_guest2", "dx": 20, "dy": 20},
        {"t": "wardrobe", "w": 120, "h": 60, "room_id": "r_guest2", "dx": 40, "dy": 60},
    ]
    _G, _geo, scene = _live_scene(furniture)
    result = lint.lint_layout(scene)
    overlaps = [i for i in result["issues"] if i["code"] == "LAYOUT_FURNITURE_OVERLAP"]
    assert overlaps, result["issues"]
    assert any(
        {"床", "衣柜"}.issubset(set(i["message"].replace("与", " ").split()))
        or ("床" in i["message"] and "衣柜" in i["message"])
        for i in overlaps
    )


def test_rug_under_furniture_is_not_a_collision():
    """地毯铺在家具下 = 合法重叠, 不触发碰撞 (rug 在 OVERLAY_TYPES)。"""
    furniture = [
        {"t": "rug", "w": 300, "h": 200, "room_id": "r_live", "dx": 100, "dy": 100},
        {"t": "sofa", "w": 210, "h": 90, "room_id": "r_live", "dx": 120, "dy": 120},
    ]
    _G, _geo, scene = _live_scene(furniture)
    result = lint.lint_layout(scene)
    assert not any(i["code"] == "LAYOUT_FURNITURE_OVERLAP" for i in result["issues"])


def test_chair_tucked_under_table_is_not_a_collision():
    """餐椅塞进餐桌下 = 合法重叠, 不触发碰撞。"""
    furniture = [
        {"t": "dining_table", "w": 300, "h": 110, "room_id": "r_live", "dx": 100, "dy": 100},
        {"t": "chair", "w": 60, "h": 60, "room_id": "r_live", "dx": 140, "dy": 130},
    ]
    _G, _geo, scene = _live_scene(furniture)
    result = lint.lint_layout(scene)
    assert not any(i["code"] == "LAYOUT_FURNITURE_OVERLAP" for i in result["issues"])


def test_console_behind_floating_sofa_is_not_flagged():
    """浮岛沙发背后的条案 (console_table) 合法悬空, 不触发悬空规则 (review FP 修复)。"""
    furniture = [
        {"t": "sofa", "w": 210, "h": 90, "room_id": "r_live", "dx": 200, "dy": 200},
        {"t": "console_table", "w": 120, "h": 30, "room_id": "r_live", "dx": 200, "dy": 300},
    ]
    _G, _geo, scene = _live_scene(furniture)
    result = lint.lint_layout(scene)
    assert not any(i["code"] == "LAYOUT_WALL_UNIT_FLOATING" for i in result["issues"])


def test_desk_facing_window_is_not_backs_window():
    """书桌面窗采光 = 合法, 不触发背贴落地窗 (仅拦高储物柜/沙发/床, review FP 修复)。"""
    desk_dy = (1410 - 1) - 1020 - 60  # 主卧 y=1020, 南墙 y=1410 有 w02 玻璃墙
    furniture = _default_furniture() + [
        {"t": "desk", "w": 120, "h": 60, "room_id": "r_master", "dx": 200, "dy": desk_dy}
    ]
    _G, _geo, scene = _live_scene(furniture)
    result = lint.lint_layout(scene)
    assert not any(i["code"] == "LAYOUT_LARGE_BACKS_FULL_WINDOW" for i in result["issues"])


def test_sectional_sofa_pieces_do_not_collide():
    """组合沙发多件拼接 (sofa+chaise 叠角) = 合法, 不触发碰撞 (review FP 修复)。"""
    furniture = [
        {"t": "sofa", "w": 210, "h": 90, "room_id": "r_live", "dx": 100, "dy": 100},
        {"t": "chaise", "w": 105, "h": 170, "room_id": "r_live", "dx": 260, "dy": 100},
    ]
    _G, _geo, scene = _live_scene(furniture)
    result = lint.lint_layout(scene)
    assert not any(i["code"] == "LAYOUT_FURNITURE_OVERLAP" for i in result["issues"])


def test_collision_across_merge_group_members_is_flagged():
    """L 形合并房 (D 的 m_living=r_foyer+r_live) 内跨成员的家具重叠也应查 (review 漏报修复)。"""
    G = geometry.load(REPO / "data" / "projects" / "D" / "geometry.json")
    foyer = next(r for r in G["rooms"] if r["id"] == "r_foyer")["rect"]
    live = next(r for r in G["rooms"] if r["id"] == "r_live")["rect"]
    # 两柜分属 r_foyer / r_live, 但绝对 footprint 重叠。
    furniture = [
        {"t": "cabinet", "w": 60, "h": 40, "room_id": "r_foyer", "dx": 10, "dy": 10},
        {
            "t": "cabinet",
            "w": 60,
            "h": 40,
            "room_id": "r_live",
            "dx": (foyer[0] + 10) - live[0],
            "dy": (foyer[1] + 10) - live[1],
        },
    ]
    _G, _geo, scene = _live_scene(furniture)
    result = lint.lint_layout(scene)
    assert any(i["code"] == "LAYOUT_FURNITURE_OVERLAP" for i in result["issues"])


def test_room_scope_limits_lint_to_given_rooms():
    """room_ids 作用域: 只体检指定房间, 另一间房的悬空件不牵连 (实拍按房门禁)。"""
    furniture = _default_furniture() + [
        {"t": "wine_cabinet", "w": 60, "h": 40, "room_id": "r_live", "dx": 350, "dy": 350}
    ]
    _G, _geo, scene = _live_scene(furniture)
    # 全屋: 命中 r_live 的悬空酒柜。
    assert not lint.lint_layout(scene)["ok"]
    # 只看 r_master (干净): 不受 r_live 悬空件牵连。
    scoped = lint.lint_layout(scene, room_ids={"r_master"})
    assert scoped["ok"]
    # 只看 r_live: 仍命中。
    assert not lint.lint_layout(scene, room_ids={"r_live"})["ok"]


def test_split_glass_wall_merges_for_span_threshold():
    """连续 full 窗合并后判跨度 (review 漏报修复): 3 条各 120px 连续窗 (总 360≥300) 全部合格;
    孤立 120px 窗 (<300) 不合格。"""
    # 同墙 (h, at=0) 3 条连续窗 -> 合并 360px >= 300 -> 三者都算玻璃幕墙。
    contiguous = [
        {"id": "wa", "wtype": "full", "axis": "h", "at": 0, "span": [40, 160]},
        {"id": "wb", "wtype": "full", "axis": "h", "at": 0, "span": [160, 280]},
        {"id": "wc", "wtype": "full", "axis": "h", "at": 0, "span": [280, 400]},
    ]
    assert lint._wide_full_window_ids(contiguous) == {"wa", "wb", "wc"}
    # 孤立小窗 (120px < 300) -> 不算玻璃幕墙。
    isolated = [{"id": "wx", "wtype": "full", "axis": "h", "at": 0, "span": [40, 160]}]
    assert lint._wide_full_window_ids(isolated) == set()
    # 非连续 (中间断开) 各自 <300 -> 都不合格。
    gapped = [
        {"id": "wa", "wtype": "full", "axis": "h", "at": 0, "span": [0, 120]},
        {"id": "wb", "wtype": "full", "axis": "h", "at": 0, "span": [200, 320]},
    ]
    assert lint._wide_full_window_ids(gapped) == set()


def test_envelope_shape_matches_validate_scene():
    """lint 信封结构与 validate_scene 同构 (前端统一渲染): ok/issues/errors/warnings。"""
    _G, _geo, scene = _live_scene(_default_furniture())
    result = lint.lint_layout(scene)
    assert set(result.keys()) == {"ok", "issues", "errors", "warnings"}
    assert isinstance(result["issues"], list)
    assert result["errors"] == [i for i in result["issues"] if i["level"] == "ERROR"]
    assert result["warnings"] == [i for i in result["issues"] if i["level"] == "WARN"]


def test_lint_does_not_mutate_scene():
    """lint 纯只读: 不改 scene (不得污染 scene_hash / 后续渲染)。"""
    _G, _geo, scene = _live_scene(_default_furniture())
    import copy

    before = copy.deepcopy(scene)
    lint.lint_layout(scene)
    assert scene == before
