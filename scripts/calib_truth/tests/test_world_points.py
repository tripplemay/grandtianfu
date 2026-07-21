"""calib-route-a1 F001 — world_points.py 与端到端夹具构建。

重点守两条 calib-cure-b3 的旧病：
  * F008 标签重名（merge 组成员共用 label.zh）
  * F009 虚拟角（merge 组内部 rect 分界角在照片上不存在）
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import solve as S           # noqa: E402
import world_points as WP   # noqa: E402
from test_solve import make_camera, synth  # noqa: E402


def geom(rooms, openings=(), mm_per_px=10):
    return {"meta": {"mm_per_px": mm_per_px}, "rooms": list(rooms),
            "openings": list(openings)}


SINGLE = geom([{"id": "r_a", "rect": [100, 100, 600, 400], "label": {"zh": "卧室"}}])

# 一个无洞口的矩形房间最多只有 8 个候选点（4 角 x 地面/天花），**永远凑不够 spec
# 的 >=10**。门窗框角是必需的补充 —— 生产 r_master 也正是靠门 d09 才过线（12 个）。
SINGLE_DOOR = geom(
    [{"id": "r_a", "rect": [100, 100, 600, 400], "label": {"zh": "卧室"}}],
    [{"id": "d1", "kind": "door", "wall": {"axis": "h", "at": 100, "span": [250, 350]}}],
)
# 三扇门 -> 地面层就有 4+6=10 个点，够触发共面判据（而不是先被点数不足拦下）
FLAT_ENOUGH = geom(
    [{"id": "r_a", "rect": [100, 100, 600, 400], "label": {"zh": "卧室"}}],
    [{"id": "d1", "kind": "door", "wall": {"axis": "h", "at": 100, "span": [200, 260]}},
     {"id": "d2", "kind": "door", "wall": {"axis": "h", "at": 500, "span": [300, 360]}},
     {"id": "d3", "kind": "door", "wall": {"axis": "v", "at": 100, "span": [200, 260]}}],
)

# 复现 D 户型客厅的形状：主厅 + 西侧窄凹龛。两块各自贡献四个方位角，
# 且都通过并集边界判据 -> **方位名必然重复**（r_live 实况就是这样）。
L_MERGED = geom([
    {"id": "r_main", "rect": [100, 100, 700, 800], "merge": "mL", "label": {"zh": "客厅"}},
    {"id": "r_alcove", "rect": [40, 300, 60, 280], "merge": "mL", "label": {"zh": "客厅"}},
])

# 两个 rect 拼成一个开放空间（南北相接），共享边上的角 = 虚拟角
MERGED = geom([
    {"id": "r_n", "rect": [100, 100, 600, 200], "merge": "m1", "label": {"zh": "客厅"}},
    {"id": "r_s", "rect": [100, 300, 600, 300], "merge": "m1", "label": {"zh": "客厅"}},
])


# ------------------------------------------------------------ 基本几何

def test_single_room_gives_eight_corners_floor_and_ceiling():
    pts = WP.room_corners(SINGLE, "r_a")
    assert len(pts) == 8
    zs = sorted({p.xyz[2] for p in pts})
    assert zs == [0.0, WP.CEILING_MM]


def test_world_coords_are_rect_px_times_scale_without_origin_offset():
    """与产品 _calibration_wireframe 同口径：**不减 meta.origin**。"""
    nw = next(p for p in WP.room_corners(SINGLE, "r_a") if p.id == "r_a.NW.floor")
    assert nw.xyz == (1000.0, 1000.0, 0.0)
    se = next(p for p in WP.room_corners(SINGLE, "r_a") if p.id == "r_a.SE.ceil")
    assert se.xyz == (7000.0, 5000.0, WP.CEILING_MM)


def test_candidates_are_non_coplanar():
    assert WP.non_coplanar(WP.candidates(SINGLE, "r_a"))


# ------------------------------------------------------------ b3 F009: 虚拟角

def test_interior_merge_boundary_corners_are_dropped():
    """两 rect 相接处的角落在直墙上，照片里没有可指认的角 -> 必须剔除。"""
    ids = {p.id for p in WP.room_corners(MERGED, "r_n")}
    # r_n 的南侧两角 / r_s 的北侧两角 都在拼接缝上
    for gone in ("r_n.SW.floor", "r_n.SE.floor", "r_s.NW.floor", "r_s.NE.floor"):
        assert gone not in ids, f"{gone} 是虚拟角, 不该出现"
    # 外围真角必须保留
    for kept in ("r_n.NW.floor", "r_n.NE.floor", "r_s.SW.floor", "r_s.SE.floor"):
        assert kept in ids


def test_quadrant_rule_classifies_convex_concave_and_flat():
    rects = [(0, 0, 10, 10), (10, 0, 10, 5)]        # L 形
    assert WP._is_identifiable_corner(0, 0, rects)      # 凸角(1 象限)
    assert WP._is_identifiable_corner(20, 5, rects)     # 凸角
    assert WP._is_identifiable_corner(10, 5, rects)     # 凹角(3 象限)
    assert not WP._is_identifiable_corner(10, 0, rects)  # 直墙上(2 象限)
    assert not WP._is_identifiable_corner(5, 5, rects)   # 内部(4 象限)


# ------------------------------------------------------------ b3 F008: 重名

def test_merge_members_sharing_label_get_unique_labels():
    labels = [p.label for p in WP.candidates(MERGED, "r_n")]
    assert len(set(labels)) == len(labels), "merge 组内标签必须唯一"
    assert any("[r_n]" in x for x in labels) and any("[r_s]" in x for x in labels)


def test_single_room_label_has_no_id_suffix():
    """无 merge 时不该画蛇添足加 [rid]。"""
    assert all("[" not in p.label for p in WP.room_corners(SINGLE, "r_a"))


def test_candidate_ids_are_unique():
    for G, rid in ((SINGLE, "r_a"), (MERGED, "r_n")):
        ids = [p.id for p in WP.candidates(G, rid)]
        assert len(set(ids)) == len(ids)


# ------------------------------------------------------------ 洞口

def test_door_jambs_use_door_head_height():
    G = geom([{"id": "r_a", "rect": [100, 100, 600, 400], "label": {"zh": "卧室"}}],
             [{"id": "d1", "kind": "door", "wall": {"axis": "h", "at": 100, "span": [200, 300]}}])
    heads = [p for p in WP.opening_points(G, "r_a") if p.id.endswith(".head")]
    assert heads and all(p.xyz[2] == WP.DOOR_HEAD_MM for p in heads)


def test_full_window_head_is_ceiling():
    G = geom([{"id": "r_a", "rect": [100, 100, 600, 400], "label": {"zh": "卧室"}}],
             [{"id": "w1", "kind": "window", "wtype": "full",
               "wall": {"axis": "v", "at": 100, "span": [150, 350]}}])
    heads = [p for p in WP.opening_points(G, "r_a") if p.id.endswith(".head")]
    assert heads and all(p.xyz[2] == WP.CEILING_MM for p in heads)


def test_openings_not_on_boundary_are_ignored():
    G = geom([{"id": "r_a", "rect": [100, 100, 600, 400], "label": {"zh": "卧室"}}],
             [{"id": "dX", "kind": "door", "wall": {"axis": "h", "at": 9999, "span": [200, 300]}}])
    assert WP.opening_points(G, "r_a") == []


# ------------------------------------------------------------ 端到端

def _write(tmp, name, obj):
    p = tmp / name
    p.write_text(json.dumps(obj, ensure_ascii=False))
    return p


def test_end_to_end_fixture_build(tmp_path):
    """合成相机 -> 投影出「人工标注」-> CLI 构建夹具 -> 应判可用且恢复出相机。"""
    G = json.loads(_write(tmp_path, "g.json", SINGLE_DOOR).read_text())
    cands = WP.candidates(G, "r_a")
    K, R, t = make_camera(cam_xyz=(4000.0, -5000.0, 1500.0),
                          look_at=(4000.0, 3000.0, 1200.0))
    corr = synth(K, R, t, [p.xyz for p in cands], noise_px=0.6, seed=2)
    marks = {"marks": [{"point_id": p.id, "px": list(c[1])} for p, c in zip(cands, corr)]}
    _write(tmp_path, "marks.json", marks)
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xdb not-a-real-jpeg")   # 只用于 sha256
    out = tmp_path / "fx.json"

    rc = subprocess.run(
        [sys.executable, str(ROOT / "build_fixture.py"), "build",
         "--geometry", str(tmp_path / "g.json"), "--room", "r_a",
         "--photo", str(photo), "--marks", str(tmp_path / "marks.json"),
         "--mode", "full", "--out", str(out)],
        capture_output=True, text=True)
    assert rc.returncode == 0, rc.stderr

    fx = json.loads(out.read_text())
    assert fx["usable_as_truth"] is True
    assert fx["camera"]["det_R"] == pytest.approx(-1.0, abs=1e-3)
    assert fx["uncertainty"]["median_px"] < 12.0
    assert len(fx["correspondences"]) == len(cands)
    assert fx["photo"]["sha256"] and "wh" in fx["photo"]
    # PIPL: 夹具里不得出现文件名/路径
    assert "p.jpg" not in out.read_text()


def test_cli_rejects_coplanar_marks(tmp_path):
    """全共面必须**明确失败**，不能静默出一台错相机。"""
    _write(tmp_path, "g.json", FLAT_ENOUGH)
    floor = [p for p in WP.candidates(FLAT_ENOUGH, "r_a") if p.xyz[2] == 0.0]
    assert len(floor) >= 10, "本用例须先越过点数门槛, 才能验共面判据"
    K, R, t = make_camera(cam_xyz=(4000.0, -5000.0, 1500.0), look_at=(4000.0, 3000.0, 0.0))
    corr = synth(K, R, t, [p.xyz for p in floor])
    _write(tmp_path, "marks.json",
           {"marks": [{"point_id": p.id, "px": list(c[1])} for p, c in zip(floor, corr)]})
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"x")
    rc = subprocess.run(
        [sys.executable, str(ROOT / "build_fixture.py"), "build",
         "--geometry", str(tmp_path / "g.json"), "--room", "r_a",
         "--photo", str(photo), "--marks", str(tmp_path / "marks.json"),
         "--mode", "full"],
        capture_output=True, text=True)
    assert rc.returncode == 2
    assert "共面" in rc.stderr


def test_cli_rejects_too_few_marks(tmp_path):
    _write(tmp_path, "g.json", SINGLE_DOOR)
    cands = WP.candidates(SINGLE_DOOR, "r_a")[:4]
    K, R, t = make_camera(cam_xyz=(4000.0, -5000.0, 1500.0), look_at=(4000.0, 3000.0, 1200.0))
    corr = synth(K, R, t, [p.xyz for p in cands])
    _write(tmp_path, "marks.json",
           {"marks": [{"point_id": p.id, "px": list(c[1])} for p, c in zip(cands, corr)]})
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"x")
    rc = subprocess.run(
        [sys.executable, str(ROOT / "build_fixture.py"), "build",
         "--geometry", str(tmp_path / "g.json"), "--room", "r_a",
         "--photo", str(photo), "--marks", str(tmp_path / "marks.json"),
         "--mode", "full"],
        capture_output=True, text=True)
    assert rc.returncode == 2
    assert ">= 10" in rc.stderr or ">=10" in rc.stderr


def test_cli_points_subcommand_lists_candidates(tmp_path):
    _write(tmp_path, "g.json", SINGLE)
    rc = subprocess.run(
        [sys.executable, str(ROOT / "build_fixture.py"), "points",
         "--geometry", str(tmp_path / "g.json"), "--room", "r_a", "--mode", "full"],
        capture_output=True, text=True)
    assert rc.returncode == 0
    d = json.loads(rc.stdout)
    assert d["room_id"] == "r_a" and d["coplanar_warning"] is False
    assert len(d["points"]) == 8


def test_bare_rectangle_cannot_reach_ten_points():
    """无洞口矩形房只有 8 点 —— 记录这条硬约束，选片时须据此排除。"""
    assert len(WP.candidates(SINGLE, "r_a")) == 8
    assert len(WP.candidates(SINGLE_DOOR, "r_a")) == 12


# ------------------------------------------------ 窗台高度未知 -> 不得臆造坐标

NORMAL_WIN = geom(
    [{"id": "r_a", "rect": [100, 100, 600, 400], "label": {"zh": "卧室"}}],
    [{"id": "w_n", "kind": "window", "wtype": "normal",
      "wall": {"axis": "v", "at": 100, "span": [150, 350]}}],
)
FULL_WIN = geom(
    [{"id": "r_a", "rect": [100, 100, 600, 400], "label": {"zh": "卧室"}}],
    [{"id": "w_f", "kind": "window", "wtype": "full",
      "wall": {"axis": "v", "at": 100, "span": [150, 350]}}],
)


def test_normal_window_emits_no_points_at_all():
    """普通窗有窗台，geometry 无该字段 -> 底和顶都不知道 -> 一个点都不发。

    早先版本一律发 z=0 的『窗底』，等于把错坐标喂进真值。真值里的错坐标比缺点
    更糟：它不会报错，只会静默地把参考相机拉歪。
    """
    assert WP.opening_points(NORMAL_WIN, "r_a") == []


def test_full_window_still_emits_floor_and_ceiling():
    pts = WP.opening_points(FULL_WIN, "r_a")
    assert {p.xyz[2] for p in pts} == {0.0, WP.CEILING_MM}


def test_assumed_heights_are_labelled_as_assumptions():
    """门头/窗顶是常量假设，标签必须自曝，否则标注者会以为它是量出来的。"""
    heads = [p for p in WP.opening_points(SINGLE_DOOR, "r_a") if p.id.endswith(".head")]
    assert heads and all("假设" in p.label for p in heads)


# ------------------------------------------------------------ 仅地面候选

def test_floor_candidates_are_all_z_zero():
    fl = WP.floor_candidates(MERGED, "r_n")
    assert fl and all(p.xyz[2] == 0.0 for p in fl)


def test_floor_candidates_exclude_normal_window_base():
    """普通窗的『底』曾被当作地面点 —— 它不在地面上。"""
    assert WP.floor_candidates(NORMAL_WIN, "r_a") == WP.floor_candidates(SINGLE, "r_a")


def test_floor_candidates_carry_no_assumed_coordinate():
    """地面点的坐标应零假设：x/y 来自平面图，z=0 是定义。"""
    for p in WP.floor_candidates(SINGLE_DOOR, "r_a"):
        assert p.xyz[2] == 0.0 and "假设" not in p.label


# ------------------------------------------------------ plane 模式（默认）端到端

def test_plane_mode_is_the_cli_default(tmp_path):
    _write(tmp_path, "g.json", SINGLE_DOOR)
    rc = subprocess.run(
        [sys.executable, str(ROOT / "build_fixture.py"), "points",
         "--geometry", str(tmp_path / "g.json"), "--room", "r_a"],
        capture_output=True, text=True)
    d = json.loads(rc.stdout)
    assert d["mode"] == "plane" and d["min_marks"] == 5
    assert all(p["xyz"][2] == 0.0 for p in d["points"])


def test_plane_mode_end_to_end_from_floor_marks_only(tmp_path):
    """只标地面点 -> 单平面标定 -> 可用真值。标注量从 10 降到 5。"""
    _write(tmp_path, "g.json", SINGLE_DOOR)
    floor = WP.floor_candidates(SINGLE_DOOR, "r_a")
    assert len(floor) >= 5
    K, R, t = make_camera(f=900.0, cx=1024.0, cy=768.0,
                          cam_xyz=(4000.0, -3000.0, 1500.0), look_at=(4000.0, 3000.0, 0.0))
    corr = synth(K, R, t, [p.xyz for p in floor], noise_px=0.6, seed=2)
    _write(tmp_path, "marks.json",
           {"marks": [{"point_id": p.id, "px": list(c[1])} for p, c in zip(floor, corr)]})
    photo = tmp_path / "p.jpg"
    from PIL import Image
    Image.new("RGB", (2048, 1536)).save(photo)
    out = tmp_path / "fx.json"
    rc = subprocess.run(
        [sys.executable, str(ROOT / "build_fixture.py"), "build",
         "--geometry", str(tmp_path / "g.json"), "--room", "r_a",
         "--photo", str(photo), "--marks", str(tmp_path / "marks.json"), "--out", str(out)],
        capture_output=True, text=True)
    assert rc.returncode == 0, rc.stderr + rc.stdout
    fx = json.loads(out.read_text())
    assert fx["mode"] == "plane" and fx["usable_as_truth"] is True
    assert fx["self_check"]["self_consistent"] is True
    assert abs(fx["camera"]["f_px"] - 900.0) / 900.0 < 0.05
    assert fx["camera"]["det_R"] == pytest.approx(-1.0, abs=1e-3)


def test_plane_mode_rejects_non_floor_marks(tmp_path):
    """混入天花角(假设坐标) -> 必须明确报错, 不得静默丢弃。"""
    _write(tmp_path, "g.json", SINGLE_DOOR)
    pts = WP.floor_candidates(SINGLE_DOOR, "r_a")[:4] + \
        [p for p in WP.candidates(SINGLE_DOOR, "r_a") if p.xyz[2] > 0][:2]
    K, R, t = make_camera(f=900.0, cx=1024.0, cy=768.0,
                          cam_xyz=(4000.0, -3000.0, 1500.0), look_at=(4000.0, 3000.0, 1000.0))
    corr = synth(K, R, t, [p.xyz for p in pts])
    _write(tmp_path, "marks.json",
           {"marks": [{"point_id": p.id, "px": list(c[1])} for p, c in zip(pts, corr)]})
    photo = tmp_path / "p.jpg"
    from PIL import Image
    Image.new("RGB", (2048, 1536)).save(photo)
    rc = subprocess.run(
        [sys.executable, str(ROOT / "build_fixture.py"), "build",
         "--geometry", str(tmp_path / "g.json"), "--room", "r_a",
         "--photo", str(photo), "--marks", str(tmp_path / "marks.json")],
        capture_output=True, text=True)
    assert rc.returncode == 2
    assert "z=0" in rc.stderr and "假设" in rc.stderr


# ---------------------------------------------- 平面图数据（可辨识性的解法）

def test_plan_outline_covers_all_merge_members():
    """merge 组的每个子矩形都要画出来, 否则用户看不到那些重名角在哪。"""
    plan = WP.plan_outline(MERGED, "r_n")
    assert {r["id"] for r in plan["rects"]} == {"r_n", "r_s"}
    assert plan["rects"][0]["xywh"] == [1000.0, 1000.0, 6000.0, 2000.0]


def test_plan_outline_includes_openings_as_landmarks():
    plan = WP.plan_outline(SINGLE_DOOR, "r_a")
    assert len(plan["openings"]) == 1
    o = plan["openings"][0]
    assert o["id"] == "d1" and o["kind"] == "door"
    assert o["a"] == [2500.0, 1000.0] and o["b"] == [3500.0, 1000.0]


def test_duplicate_direction_labels_are_disambiguated_by_plan_not_text():
    """merge 组里方位名必然重复 —— 这是几何事实, 不是 bug。

    钉住的是: 重名点坐标必须真的不同, 且 plan 能把它们区分开。文字标签解决不了
    可辨识性（用户不知道 `r-itki-331` 在哪）, 位置图才行。
    """
    fl = WP.floor_candidates(L_MERGED, "r_main")
    labels = [p.label.split("]")[-1] for p in fl]
    assert len(labels) != len(set(labels)), "本用例前提: 方位名确实重复"
    xy = [(p.xyz[0], p.xyz[1]) for p in fl]
    assert len(xy) == len(set(xy)), "重名点的坐标必须互不相同"
    plan = WP.plan_outline(L_MERGED, "r_main")
    assert len(plan["rects"]) == 2, "必须提供两块矩形的位置供定位"


def test_points_cli_emits_plan(tmp_path):
    _write(tmp_path, "g.json", SINGLE_DOOR)
    rc = subprocess.run(
        [sys.executable, str(ROOT / "build_fixture.py"), "points",
         "--geometry", str(tmp_path / "g.json"), "--room", "r_a"],
        capture_output=True, text=True)
    d = json.loads(rc.stdout)
    assert d["plan"]["rects"] and "openings" in d["plan"]
