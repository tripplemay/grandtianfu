# -*- coding: utf-8 -*-
"""确定性回归评测集 eval_scenarios: 全场景应通过 + 失败类型覆盖完整 (批2-6 回归门)。"""
from pathlib import Path

from aigc import eval_scenarios as ev
from floorplan_core import geometry

REPO = Path(__file__).resolve().parents[3]


def _live():
    G = geometry.load(REPO / "data" / "projects" / "D" / "geometry.json")
    return G, geometry.derive(G)


def test_all_scenarios_pass_on_real_d():
    """回归门: 真实 D 户型上全部确定性场景应通过 (任一 lint/校验回归即失败)。"""
    G, geo = _live()
    rows = ev.run_scenarios(G, geo)
    failed = [r["id"] for r in rows if not r["ok"]]
    assert not failed, f"回归: 以下场景未按预期判定 {failed}\n{ev.to_markdown(rows)}"


def test_failure_type_coverage_complete():
    """P2-2 覆盖: 声明的失败类型全部被某场景覆盖且检出。"""
    G, geo = _live()
    cov = ev.coverage(ev.run_scenarios(G, geo))
    assert cov["all_pass"] is True
    assert cov["coverage_complete"] is True
    assert set(cov["failure_types_detected"]) == set(cov["failure_types_covered"])


def test_good_layout_has_no_lint_false_positives():
    """好布局场景 (含组合沙发拼接) 不得产生 lint 误报。"""
    G, geo = _live()
    rows = {r["id"]: r for r in ev.run_scenarios(G, geo)}
    assert rows["good_living"]["lint_codes"] == []
    assert rows["sectional_no_false_collision"]["false_positive"] == []


def test_each_failure_scenario_detects_its_type():
    """每个失败场景命中其预期 code (悬空/背窗/碰撞/dangling)。"""
    G, geo = _live()
    rows = {r["id"]: r for r in ev.run_scenarios(G, geo)}
    assert "LAYOUT_WALL_UNIT_FLOATING" in rows["floating_wall_unit"]["lint_codes"]
    assert "LAYOUT_LARGE_BACKS_FULL_WINDOW" in rows["backs_glass_wall"]["lint_codes"]
    assert "LAYOUT_FURNITURE_OVERLAP" in rows["furniture_overlap"]["lint_codes"]
    assert "DANGLING_FURNITURE_ROOM" in rows["dangling_room"]["scene_errors"]


def test_to_markdown_renders_summary():
    G, geo = _live()
    rows = ev.run_scenarios(G, geo)
    md = ev.to_markdown(rows)
    assert "场景" in md and "失败类型覆盖 完整" in md
