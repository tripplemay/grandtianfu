# -*- coding: utf-8 -*-
"""placement_brief 单测 (render-relation-b1 F001)。

合成几何快照式断言语义规则: orient=靠背墙 / 贴墙边缘缝隙 / merge 组作用域与
『照片房 vs 相连空间』/ 关系模板按实际数量 / 窗帘软化 / 无 direction 降级 / 确定性。
"""

from __future__ import annotations

from floorplan_core import placement_brief


def _G_living():
    """两成员 merge 组: r_main(100,100,400x400) + r_strip(60,200,40x200)。"""
    return {
        "meta": {"mm_per_px": 10},
        "rooms": [
            {"id": "r_main", "rect": [100, 100, 400, 400], "merge": "m1", "label": {"zh": "客厅"}},
            {"id": "r_strip", "rect": [60, 200, 40, 200], "merge": "m1", "label": {"zh": "门厅"}},
        ],
        "openings": [
            {
                "id": "d-kit",
                "kind": "door",
                "material": "glass",
                "wall": {"axis": "h", "at": 100, "span": [200, 300]},
                "between": ["kitchen", "r_main"],
            },
            {
                "id": "w01",
                "kind": "window",
                "wtype": "full",
                "wall": {"axis": "h", "at": 500, "span": [100, 500]},
            },
            {
                "id": "d-entry",
                "kind": "door",
                "wall": {"axis": "v", "at": 60, "span": [250, 350]},
                "between": ["entry", "r_strip"],
            },
        ],
    }


def _scene_living():
    return {
        "axon_furniture": [
            # 沙发: 四边缝隙均 >120px -> 房间中部, orient W = 靠背靠西墙
            {
                "t": "sofa",
                "_room_id": "r_main",
                "_dx": 160,
                "_dy": 130,
                "w": 80,
                "h": 120,
                "orient": "W",
            },
            # 电视柜: 东缘缝隙 0 -> 贴墙, orient E
            {
                "t": "media",
                "_room_id": "r_main",
                "_dx": 360,
                "_dy": 200,
                "w": 40,
                "h": 200,
                "orient": "E",
            },
            {"t": "coffee_table", "_room_id": "r_main", "_dx": 250, "_dy": 280, "w": 100, "h": 80},
            {"t": "rug", "_room_id": "r_main", "_dx": 140, "_dy": 220, "w": 260, "h": 240},
            {
                "t": "curtain",
                "_room_id": "r_main",
                "_dx": 0,
                "_dy": 390,
                "w": 400,
                "h": 10,
                "orient": "S",
            },
            {"t": "dining_table", "_room_id": "r_main", "_dx": 100, "_dy": 30, "w": 200, "h": 90},
            # 酒柜登记 r_main 但几何中心落在 r_strip -> linked (相连空间, 不进验收约束)
            {
                "t": "wine_cabinet",
                "_room_id": "r_main",
                "_dx": -30,
                "_dy": 120,
                "w": 30,
                "h": 150,
                "orient": "W",
            },
            # 未落位 (plants) 与结构件 (entry_door) 必须被跳过
            {"t": "plant", "_room_id": "r_main", "_dx": None, "_dy": None},
            {"t": "entry_door", "_room_id": "r_main", "_dx": 10, "_dy": 10, "w": 100, "h": 10},
        ]
    }


def test_members_and_frame_v2():
    b = placement_brief.build_brief(_G_living(), _scene_living(), "r_main", "v2")
    assert b["members"] == ["r_main", "r_strip"]
    # v2 朝东南: 左=东墙, 右=南墙(落地窗)
    assert "左侧远处是东侧实墙" in b["frame"]
    assert "右侧远处是南墙（落地窗）" in b["frame"]


def test_orient_is_backing_wall_not_facing():
    b = placement_brief.build_brief(_G_living(), _scene_living(), "r_main", "v2")
    sofa = next(x for x in b["placement_lines"] if x.startswith("沙发"))
    assert "靠背靠西侧、面向东" in sofa
    media = next(x for x in b["placement_lines"] if x.startswith("电视柜"))
    assert "贴东侧实墙" in media  # 东缘缝隙 0 -> 贴墙 (边缘缝隙判定, 非中心距)
    assert "靠背靠东侧、面向西" in media


def test_edge_gap_determines_flush_not_center_distance():
    b = placement_brief.build_brief(_G_living(), _scene_living(), "r_main", "v2")
    sofa = next(x for x in b["placement_lines"] if x.startswith("沙发"))
    # 沙发西缘缝隙 150px > 120 -> 房间中部 (尽管中心更靠近西墙)
    assert "房间中部区域" in sofa


def test_linked_member_excluded_from_constraints():
    b = placement_brief.build_brief(_G_living(), _scene_living(), "r_main", "v2")
    assert any("酒柜" in x for x in b["linked_lines"])
    assert all("酒柜" not in c for c in b["constraints"])
    assert any("可能在画面外" in x for x in b["linked_lines"])


def test_skip_unplaced_and_structural():
    b = placement_brief.build_brief(_G_living(), _scene_living(), "r_main", "v2")
    assert all("绿植" not in x for x in b["placement_lines"])
    assert all("entry_door" not in x for x in b["placement_lines"])


def test_curtain_softened_and_relations():
    b = placement_brief.build_brief(_G_living(), _scene_living(), "r_main", "v2")
    curtain = next(x for x in b["placement_lines"] if x.startswith("落地窗帘"))
    assert "沿南墙（落地窗）布置" in curtain  # 软化: 不是『整面悬挂』
    assert any("沙发组合与电视柜面对面" in x for x in b["constraints"])
    assert any("茶几在沙发组合旁边" in x for x in b["constraints"])
    assert any("餐桌位于北墙（玻璃推拉门(通往kitchen)）附近" in x for x in b["constraints"])
    # 酒柜落在相连空间 -> 关系行进 linked_lines, 不进验收约束
    assert any("酒柜位于入户门厅一侧" in x for x in b["linked_lines"])
    assert all("酒柜位于入户门厅一侧" not in c for c in b["constraints"])


def _G_bedroom():
    return {
        "meta": {"mm_per_px": 10},
        "rooms": [{"id": "r_bed", "rect": [600, 600, 400, 300], "label": {"zh": "卧室"}}],
        "openings": [
            {
                "id": "w02",
                "kind": "window",
                "wtype": "normal",
                "wall": {"axis": "h", "at": 900, "span": [650, 950]},
            },
        ],
    }


def test_nightstand_count_uses_actual_number():
    scene = {
        "axon_furniture": [
            {
                "t": "bed",
                "_room_id": "r_bed",
                "_dx": 200,
                "_dy": 50,
                "w": 180,
                "h": 200,
                "orient": "E",
            },
            {"t": "nightstand", "_room_id": "r_bed", "_dx": 370, "_dy": 30, "w": 40, "h": 40},
        ]
    }
    b = placement_brief.build_brief(_G_bedroom(), scene, "r_bed", None)
    # 只有 1 个床头柜 -> 关系行不得出现『两个/N个分列』
    rel = next(x for x in b["constraints"] if "紧靠" in x or "分列" in x)
    assert "个床头柜分列" not in rel
    assert "紧靠双人床床头一侧" in rel


def test_no_direction_degrades_frame_to_none():
    b = placement_brief.build_brief(_G_bedroom(), {"axon_furniture": []}, "r_bed", None)
    assert b["frame"] is None


def test_flush_gap_boundary_30px():
    scene = {
        "axon_furniture": [
            {"t": "cabinet", "_room_id": "r_bed", "_dx": 30, "_dy": 100, "w": 50, "h": 40},
            {"t": "bookshelf", "_room_id": "r_bed", "_dx": 31, "_dy": 160, "w": 50, "h": 40},
        ]
    }
    b = placement_brief.build_brief(_G_bedroom(), scene, "r_bed", None)
    cab = next(x for x in b["placement_lines"] if x.startswith("边柜"))
    assert "贴西侧实墙" in cab  # gap=30 恰好贴墙
    shelf = next(x for x in b["placement_lines"] if x.startswith("书柜"))
    assert "距墙约310mm" in shelf  # gap=31 -> 靠近档


def test_deterministic():
    a = placement_brief.build_brief(_G_living(), _scene_living(), "r_main", "v2")
    b = placement_brief.build_brief(_G_living(), _scene_living(), "r_main", "v2")
    assert a == b


def test_view_forwards_values_match_main_legacy():
    """视角映射与 main.py 原 _VIEW_FORWARDS/_VIEW_FACING_ZH 逐值一致 (双写消除的回归锁)。"""
    assert placement_brief.VIEW_FORWARDS == {
        "v0": (-1.0, -1.0),
        "v1": (-1.0, 1.0),
        "v2": (1.0, 1.0),
        "v3": (1.0, -1.0),
    }
    assert placement_brief.VIEW_FACING_ZH == {
        "v0": "西北",
        "v1": "西南",
        "v2": "东南",
        "v3": "东北",
    }
