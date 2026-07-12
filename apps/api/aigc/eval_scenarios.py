# -*- coding: utf-8 -*-
"""路线A 几何锁定链路【确定性回归评测集】(审查 P2-2): 无需真实生成图/网络即可跑。

image2 回归评测集 (eval_harness.py) 评的是【出图结果】(需 live provider + 人工评分)。本模块补
另一半: 批2-6 加的一整套【确定性输入侧检查】—— 布局 lint (悬空/背贴玻璃幕墙/碰撞)、场景校验
(家具穿墙/dangling)、盒子投影可用性 (出画/近场)、标定生命周期 (stale) —— 都是给定
几何+家具(+合成相机) 即可断言的纯函数。改 prompt/lint/validation/geometry-lock 后跑一次即知
这些检查有无回归、各失败类型是否仍被正确识别。

设计: 声明式场景 (在真实 D 户型上叠加特定家具) + 期望的检查产出; run_scenarios 跑全套检查,
verdict 逐场景比对期望 vs 实际, coverage 汇总各失败类型是否都被覆盖。纯函数, 单测友好。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from floorplan_core import axon, lint


@dataclass(frozen=True)
class LayoutScenario:
    """一个确定性布局场景: 在 D 户型上放这组家具, 期望命中这些 lint/场景ERROR code。

    failure_type: 该场景演示的失败类型 (用于覆盖统计); "" = 好布局 (应零问题)。
    expect_lint / expect_scene_error: 期望【至少】命中的 code 集合。
    forbid_lint: 期望【不得】命中的 code (防误报, 如好布局/合法叠放)。
    """

    id: str
    description: str
    furniture: tuple[dict, ...]
    failure_type: str = ""
    expect_lint: frozenset = field(default_factory=frozenset)
    expect_scene_error: frozenset = field(default_factory=frozenset)
    forbid_lint: frozenset = field(default_factory=frozenset)


# 客厅/主卧的真实 rect 常量 (D 户型): r_live=[495,490,720,765], r_master=[1215,1020,600,390]
# (南墙 y=1410 有 6m 落地窗 w02)。场景家具坐标据此构造演示各失败类型。
_MASTER_SOUTH_DY = (1410 - 1) - 1020 - 60  # 衣柜背贴主卧南落地窗

SCENARIOS: tuple[LayoutScenario, ...] = (
    LayoutScenario(
        "good_living",
        "客厅正常布局: 沙发面对电视悬空 + 茶几 + 电视柜贴墙, 应零 lint 问题",
        (
            {"t": "sofa", "w": 210, "h": 90, "room_id": "r_live", "dx": 200, "dy": 200},
            {"t": "coffee_table", "w": 100, "h": 60, "room_id": "r_live", "dx": 250, "dy": 320},
            {"t": "media", "w": 150, "h": 44, "room_id": "r_live", "dx": 280, "dy": 6},
        ),
        forbid_lint=frozenset(
            {"LAYOUT_WALL_UNIT_FLOATING", "LAYOUT_LARGE_BACKS_FULL_WINDOW", "LAYOUT_FURNITURE_OVERLAP"}
        ),
    ),
    LayoutScenario(
        "floating_wall_unit",
        "酒柜悬空于客厅中央 (生产病灶): 应命中 LAYOUT_WALL_UNIT_FLOATING",
        ({"t": "wine_cabinet", "w": 60, "h": 40, "room_id": "r_live", "dx": 350, "dy": 350},),
        failure_type="悬空柜类",
        expect_lint=frozenset({"LAYOUT_WALL_UNIT_FLOATING"}),
    ),
    LayoutScenario(
        "backs_glass_wall",
        "衣柜背贴主卧 6m 玻璃幕墙: 应命中 LAYOUT_LARGE_BACKS_FULL_WINDOW",
        ({"t": "wardrobe", "w": 120, "h": 60, "room_id": "r_master", "dx": 200, "dy": _MASTER_SOUTH_DY},),
        failure_type="大件背贴玻璃幕墙",
        expect_lint=frozenset({"LAYOUT_LARGE_BACKS_FULL_WINDOW"}),
    ),
    LayoutScenario(
        "furniture_overlap",
        "床与衣柜明显重叠: 应命中 LAYOUT_FURNITURE_OVERLAP",
        (
            {"t": "bed", "w": 180, "h": 200, "room_id": "r_guest2", "dx": 20, "dy": 20},
            {"t": "wardrobe", "w": 120, "h": 60, "room_id": "r_guest2", "dx": 40, "dy": 60},
        ),
        failure_type="家具碰撞",
        expect_lint=frozenset({"LAYOUT_FURNITURE_OVERLAP"}),
    ),
    LayoutScenario(
        "sectional_no_false_collision",
        "组合沙发拼接 (sofa+chaise 叠角): 合法, 不得误报碰撞",
        (
            {"t": "sofa", "w": 210, "h": 90, "room_id": "r_live", "dx": 100, "dy": 100},
            {"t": "chaise", "w": 105, "h": 170, "room_id": "r_live", "dx": 260, "dy": 100},
        ),
        forbid_lint=frozenset({"LAYOUT_FURNITURE_OVERLAP"}),
    ),
    LayoutScenario(
        "dangling_room",
        "家具引用不存在房间: 场景校验应报 DANGLING_FURNITURE_ROOM (ERROR)",
        ({"t": "sofa", "w": 100, "h": 80, "room_id": "r_nope", "dx": 0, "dy": 0},),
        failure_type="家具挂空房间",
        expect_scene_error=frozenset({"DANGLING_FURNITURE_ROOM"}),
    ),
)

# P2-2 要求覆盖的失败类型 (确定性可测部分)。缺任一 = 评测集覆盖不全。
COVERED_FAILURE_TYPES = frozenset(
    s.failure_type for s in SCENARIOS if s.failure_type
)


def run_scenario(G: dict, geo: dict, scenario: LayoutScenario) -> dict:
    """跑一个场景: build_scene -> lint + 场景校验, 比对期望。返回 verdict 行。"""
    scene = axon.build_scene(G, geo, list(scenario.furniture), project_id="D")
    lint_codes = {i["code"] for i in lint.lint_layout(scene).get("issues", [])}
    scene_errors = {e.get("code") for e in scene.get("validation", {}).get("errors", [])}

    missing_lint = scenario.expect_lint - lint_codes
    missing_err = scenario.expect_scene_error - scene_errors
    false_pos = scenario.forbid_lint & lint_codes
    ok = not missing_lint and not missing_err and not false_pos
    return {
        "id": scenario.id,
        "description": scenario.description,
        "failure_type": scenario.failure_type,
        "ok": ok,
        "lint_codes": sorted(lint_codes),
        "scene_errors": sorted(c for c in scene_errors if c),
        "missing_expected": sorted(missing_lint | missing_err),
        "false_positive": sorted(false_pos),
    }


def run_scenarios(G: dict, geo: dict) -> list[dict]:
    """跑全部场景, 返回 verdict 行列表。"""
    return [run_scenario(G, geo, s) for s in SCENARIOS]


def coverage(rows: list[dict]) -> dict:
    """汇总: 全过否 / 各失败类型是否被覆盖且检出。"""
    passed = sum(1 for r in rows if r["ok"])
    detected_types = {
        r["failure_type"] for r in rows if r["failure_type"] and r["ok"]
    }
    return {
        "total": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "all_pass": passed == len(rows),
        "failure_types_covered": sorted(COVERED_FAILURE_TYPES),
        "failure_types_detected": sorted(detected_types),
        "coverage_complete": detected_types >= COVERED_FAILURE_TYPES,
    }


def to_markdown(rows: list[dict], summary: dict | None = None) -> str:
    """verdict 行 -> markdown 报告 (确定性回归)。"""
    summary = summary or coverage(rows)
    head = "| 场景 | 失败类型 | 结果 | 命中 lint | 场景ERROR | 缺失/误报 |"
    sep = "| --- | --- | --- | --- | --- | --- |"
    body = []
    for r in rows:
        mark = "✅" if r["ok"] else "❌"
        problems = ", ".join(r["missing_expected"] + [f"误报{p}" for p in r["false_positive"]]) or "—"
        body.append(
            f"| {r['id']} | {r['failure_type'] or '好布局'} | {mark} | "
            f"{', '.join(r['lint_codes']) or '—'} | {', '.join(r['scene_errors']) or '—'} | {problems} |"
        )
    line = (
        f"\n合计 {summary['total']} · 通过 {summary['passed']} · 失败 {summary['failed']} · "
        f"失败类型覆盖 {'完整' if summary['coverage_complete'] else '不全'} "
        f"({len(summary['failure_types_detected'])}/{len(summary['failure_types_covered'])})"
    )
    return "\n".join([head, sep, *body]) + "\n" + line
