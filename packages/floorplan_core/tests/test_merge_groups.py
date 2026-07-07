# -*- coding: utf-8 -*-
"""P3 异形空间一期: merge_groups 基础几何 (聚组/代表/最近part/并集覆盖)。byte-safe:
无 merge / 单成员组返回空 -> 下游走单房路径。"""
import json
import os

from floorplan_core import axon, geometry
from floorplan_core import geometry as g

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
D_GEOM = os.path.join(REPO, "data", "projects", "D", "geometry.json")


def _G(rooms):
    return {"meta": {"eps": 1}, "spaces": {}, "rooms": rooms}


def test_no_merge_returns_empty():
    G = _G([
        {"id": "a", "space": "s1", "rect": [0, 0, 100, 100]},
        {"id": "b", "space": "s2", "rect": [200, 0, 100, 100]},
    ])
    assert g.merge_groups(G) == {}
    assert g.group_rep_map(G) == {}
    assert g.room_group_of(G) == {}


def test_singleton_merge_group_ignored():
    """merge 只标在一个房上 -> 不成组 (byte-safe: 视同普通房)。"""
    G = _G([{"id": "a", "space": "s", "rect": [0, 0, 100, 100], "merge": "m1"}])
    assert g.merge_groups(G) == {}


def test_two_member_group_union_and_rep():
    # L 形: a=(0,0,100,300) 面积 30000; b=(100,200,300,300) 即 [100,200]w200 h100 面积 20000
    G = _G([
        {"id": "r_a", "space": "s", "rect": [0, 0, 100, 300], "merge": "m"},
        {"id": "r_b", "space": "s", "rect": [100, 200, 200, 100], "merge": "m"},
    ])
    mg = g.merge_groups(G)
    assert set(mg) == {"m"}
    grp = mg["m"]
    assert grp["members"] == ["r_a", "r_b"]  # 按 id 稳定
    assert grp["bbox"] == (0.0, 0.0, 300.0, 300.0)  # 并集包围盒 (含凹口)
    assert grp["rep"] == "r_a"  # 最大面积 (30000 > 20000)
    assert g.group_rep_map(G) == {"r_a": "r_a", "r_b": "r_a"}
    assert g.room_group_of(G) == {"r_a": "m", "r_b": "m"}


def test_rep_tiebreak_area_then_id():
    # 等面积 -> 取最小 id
    G = _G([
        {"id": "z", "space": "s", "rect": [0, 0, 100, 100], "merge": "m"},
        {"id": "a", "space": "s", "rect": [100, 0, 100, 100], "merge": "m"},
    ])
    assert g.merge_groups(G)["m"]["rep"] == "a"


def test_nearest_part_tiebreak():
    rects = [("r_a", 0, 0, 100, 300), ("r_b", 100, 200, 300, 300)]
    # 点在 a 内 -> a
    assert g.nearest_part(rects, 50, 50) == "r_a"
    # 点在 b 内 -> b
    assert g.nearest_part(rects, 200, 250) == "r_b"
    # 凹口点 (150,50): 不在任何矩形内; 到 a 间隙=50 (x), 到 b 间隙=150 (y) -> a 更近
    assert g.nearest_part(rects, 150, 50) == "r_a"


def test_point_in_any_excludes_notch():
    rects = [("r_a", 0, 0, 100, 300), ("r_b", 100, 200, 300, 300)]
    assert g.point_in_any(rects, 50, 50)     # 在 a
    assert g.point_in_any(rects, 200, 250)   # 在 b
    assert not g.point_in_any(rects, 200, 50)  # L 凹口 -> 不在


def test_rect_covered_by_union_vs_notch():
    rects = [("r_a", 0, 0, 100, 300), ("r_b", 100, 200, 300, 300)]
    # 完全落在 a 内的小盒 -> 覆盖
    assert g.rect_covered_by((10, 10, 90, 90), rects)
    # 跨接缝但都在并集内 (a 下段 + b): 盒 (50,210,150,290) -> a 覆盖左半, b 覆盖右半
    assert g.rect_covered_by((50, 210, 150, 290), rects)
    # 伸进凹口的盒 (50,10,150,90) 右半落凹口 -> 不覆盖
    assert not g.rect_covered_by((50, 10, 150, 90), rects)


# ---- axon slice 组裁切 (P3 slice 组裁切): 用 D 真实 merge 组 m_living ---- #
def _D_geom():
    G = geometry.load(D_GEOM)
    return G, axon.geom_bundle(G, geometry.derive(G))


def test_slice_merge_group_includes_all_members():
    G, geom = _D_geom()
    merged = [r["id"] for r in G["rooms"] if r.get("merge")]
    assert len(merged) >= 2, "D 应含 merge 组 m_living (r_foyer+r_live)"
    sliced = axon.slice_geom_for_room(geom, merged[0])
    ids = {r["id"] for r in sliced[6]["rooms"]}
    assert ids == set(merged)  # 切任一成员 -> 整组
    assert axon.merge_group_ids(G, merged[0]) == set(merged)


def test_slice_solo_room_unchanged():
    G, geom = _D_geom()
    solo = next(r["id"] for r in G["rooms"] if not r.get("merge"))
    ids = {r["id"] for r in axon.slice_geom_for_room(geom, solo)[6]["rooms"]}
    assert ids == {solo}  # 无 merge -> 单房路径 byte-safe
    assert axon.merge_group_ids(G, solo) == {solo}


# ---- scene 并集夹取 helper (P3 scene 夹取): 中心在本腿则不动, 否则夹最近腿 ---- #
def test_scene_clamp_rect_group_aware():
    from floorplan_core import scene
    rooms = [
        {"id": "r_a", "rect": [0, 0, 100, 300], "merge": "m"},
        {"id": "r_b", "rect": [100, 200, 200, 100], "merge": "m"},
    ]
    gr = scene._group_rects_by_room(rooms)
    assert set(gr) == {"r_a", "r_b"}
    rbi = {r["id"]: r for r in rooms}
    # 中心在本腿 r_a -> 本 rect (byte-safe)
    assert scene._clamp_rect_for("r_a", 50, 50, rbi, gr) == [0, 0, 100, 300]
    # 中心在 r_b 区 (200,250), 但件挂 r_a -> 夹到最近腿 r_b (以 [x,y,w,h] 给出)
    assert scene._clamp_rect_for("r_a", 200, 250, rbi, gr) == [100, 200, 200, 100]
    # 非组 -> assigned rect 原样 (byte-safe)
    assert scene._clamp_rect_for("s", 0, 0, {"s": {"rect": [5, 5, 10, 10]}}, {}) == [5, 5, 10, 10]


def test_scene_build_photo_still_renders_with_merge_group():
    """D (含 m_living) 经 build_scene->render photo 不崩, 且 shell 仍 byte-lock (已由 golden 保)。"""
    G, geom = _D_geom()
    import json as _json
    furn = _json.load(open(os.path.join(REPO, "data", "projects", "D", "furniture.json"), encoding="utf-8"))
    svg = axon.render(geom, furn, mode="photo")
    assert svg.startswith("<svg") and "<polygon" in svg


def test_edge_openings_matches_four_walls():
    """edge_openings: axis/at 匹配 rect 四壁, rel_center 为沿墙相对原点中心。"""
    rect = (100.0, 200.0, 300.0, 400.0)  # x,y,w,h -> x0..x1=100..400, y0..y1=200..600
    ops = [
        {"axis": "v", "at": 100, "span": [250, 350]},   # W 墙
        {"axis": "v", "at": 400, "span": [250, 350]},   # E 墙
        {"axis": "h", "at": 200, "span": [150, 250]},   # N 墙
        {"axis": "h", "at": 600, "span": [150, 250]},   # S 墙
        {"axis": "v", "at": 999, "span": [250, 350]},   # 不贴任何墙
    ]
    got = geometry.edge_openings(rect, ops, 1)
    walls = [w for w, _rel, _op in got]
    assert walls == ["W", "E", "N", "S"]
    # W 墙 rel_center = mid(300) - y(200) = 100
    assert got[0][1] == 100.0


def test_group_exterior_openings_suppresses_internal_shared_edge():
    """两腿共线共享边上的洞 (两侧各一成员) 抑制; 外墙洞保留。"""
    member_rects = [("a", 0.0, 0.0, 300.0, 300.0), ("b", 300.0, 0.0, 600.0, 300.0)]
    internal = {"axis": "v", "at": 300, "span": [100, 200]}   # a 的 E 墙 + b 的 W 墙 (共享)
    exterior = {"axis": "h", "at": 0, "span": [0, 100]}       # a 的 N 墙 (外墙)
    ext = geometry.group_exterior_openings(member_rects, [internal, exterior], 1)
    kept_ops = [op for _w, _mr, op, _r in ext]
    assert exterior in kept_ops
    assert internal not in kept_ops
    assert all(mr[0] == "a" for _w, mr, _op, _r in ext)


def test_group_exterior_openings_geometric_over_count_heuristic():
    """几何外墙判定 (外侧点是否落在另一成员) 优于计数启发式:
    - 重叠腿: 一条腿的边落在另一腿内部, 只命中一次但仍应抑制;
    - 共线外墙: 洞跨接缝命中两腿但外侧仍在外, 应保留。"""
    # 重叠腿: legA 南墙 y=400 整段落在 legB 内部 -> 内部洞, 命中一次也抑制。
    overlap = [("legA", 0.0, 0.0, 180.0, 400.0), ("legB", 0.0, 240.0, 600.0, 800.0)]
    internal = {"axis": "h", "at": 400, "span": [50, 150]}
    assert geometry.group_exterior_openings(overlap, [internal], 1) == []
    # 共线外墙: 两腿南墙同在 y=600, 洞跨 x=300 接缝命中两腿, 外侧在外 -> 保留一次。
    collinear = [("legA", 0.0, 0.0, 300.0, 600.0), ("legB", 300.0, 300.0, 700.0, 600.0)]
    seam = {"axis": "h", "at": 600, "span": [250, 350]}
    ext = geometry.group_exterior_openings(collinear, [seam], 1)
    assert len(ext) == 1 and ext[0][2] is seam
