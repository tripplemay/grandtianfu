# -*- coding: utf-8 -*-
"""decor-b1 软装配饰: wall_art(挂画)/curtain(窗帘) 悬空贴墙渲染 + noshadow + scene 豁免。

byte-safe: 新类型不在 D 活数据 -> golden 不受影响 (由 test_render_snapshot 锁)。本文件测
新件自身渲染语义: 悬空盒 + vplane 竖面、无地面阴影、贴墙不被 inner-clearance 内缩。
"""
import os

from floorplan_core import axon, catalog, geometry, scene

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
D_GEOM = os.path.join(REPO, "data", "projects", "D", "geometry.json")

DECOR = ["wall_art", "curtain"]


def _geom():
    G = geometry.load(D_GEOM)
    return axon.geom_bundle(G, geometry.derive(G))


def _abs_item(t):
    s = catalog.CATALOG[t]
    return {"t": t, "x": 500, "y": 500, "w": s["w"], "h": s["h"], "orient": "N"}


# ---- 目录 + 3D 模型注册 ---- #
def test_decor_registered_with_vplane_and_under_wall():
    for t in DECOR:
        assert t in catalog.CATALOG, f"{t} 缺目录条目"
        assert t in axon.MODELS, f"{t} 缺 MODELS 渲染器"
        assert catalog.CATALOG[t].get("noshadow") is True, f"{t} 应 noshadow"
        assert t in catalog.NOSHADOW_TYPES
        boxes, extra = axon.MODELS[t](_abs_item(t))
        assert boxes, f"{t} 无 box"
        for x0, y0, x1, y1, z0, z1, _c in boxes:
            assert x1 > x0 and y1 > y0 and z1 > z0, f"{t} 退化盒"
            assert z1 <= 1450, f"{t} z1={z1} 穿墙顶"
        # vplane 画面/长幔: extra 含竖直 polygon
        assert "<polygon" in extra, f"{t} 缺 vplane 竖面"


def test_wall_art_is_floating():
    # 挂画画框悬空 (底 z0 明显离地), 不落地。
    boxes, _extra = axon.MODELS["wall_art"](_abs_item("wall_art"))
    assert min(b[4] for b in boxes) >= 800, "挂画应悬在墙上部而非落地"


# ---- noshadow: 无地面阴影 ---- #
def test_decor_casts_no_ground_shadow():
    geom = _geom()
    assert "url(#sh)" not in axon.render(geom, [], mode="photo"), "空房不应有家具阴影 (基线)"
    # 对照: 落地件 (sofa) 投地面阴影
    sofa = {"t": "sofa", "x": 500, "y": 500, "w": 210, "h": 90, "orient": "N"}
    assert "url(#sh)" in axon.render(geom, [sofa], mode="photo"), "sofa 应投阴影 (对照有效性)"
    # 配饰件 noshadow: 单件渲染无 url(#sh)
    for t in DECOR:
        svg = axon.render(geom, [_abs_item(t)], mode="photo")
        assert "url(#sh)" not in svg, f"{t} 不应投地面阴影"


# ---- 2D 平面: 贴墙薄矩形 ---- #
def test_decor_2d_wall_hugging_rect():
    for t in DECOR:
        frags = axon._furn2d_frags(_abs_item(t))
        assert frags and any("<rect" in f for f in frags), f"{t} 2D 应有贴墙矩形"


# ---- scene D13: 贴墙配饰豁免 inner-clearance 内缩 ---- #
def _first_room_id(G):
    for r in G.get("rooms", []):
        if "rect" in r:
            return r["id"]
    raise AssertionError("D geometry 无带 rect 的房间")


def test_decor_exempt_from_inner_clearance():
    G = geometry.load(D_GEOM)
    geo = geometry.derive(G)
    rid = _first_room_id(G)
    # dx=0/dy=0 紧贴房间左上角: 普通件会被 clearance 推离墙 13px, 贴墙配饰豁免保持 0。
    wall_art = {"t": "wall_art", "room_id": rid, "dx": 0, "dy": 0,
                "w": 80, "h": 8, "orient": "W"}
    sofa = {"t": "sofa", "room_id": rid, "dx": 0, "dy": 0,
            "w": 210, "h": 90, "orient": "W"}
    sc = scene.build_scene(G, geo, [wall_art, sofa])
    by_t = {it["t"]: it for it in sc["axon_furniture"]}
    assert by_t["wall_art"].get("_dx") == 0 and by_t["wall_art"].get("_dy") == 0, \
        "挂画应贴墙不被内缩 (D13 豁免)"
    # 对照: sofa 被内缩离墙 (clearance=13)
    assert by_t["sofa"].get("_dx") == 13, "sofa 应被 inner-clearance 内缩 (对照有效性)"
    # 挂画不产生 clearance-shift 调整记录
    shifts = [a for a in sc["adjustments"]
              if a.get("type") == "wall_art" and any("clearance" in n for n in a.get("notes", []))]
    assert not shifts, "挂画不应有 clearance 调整记录"


# ---- byte-safe 前提: D 活数据不含配饰类型 ---- #
def test_d_data_has_no_decor_types():
    import json
    sch = os.path.join(REPO, "data", "projects", "D", "schemes", "default", "furniture.json")
    items = json.load(open(sch, encoding="utf-8"))
    present = {it.get("t") for it in items}
    assert not (present & set(DECOR)), "D 默认方案不应含配饰类型 (保 golden 字节)"
