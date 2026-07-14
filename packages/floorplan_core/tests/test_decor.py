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
    # 跳过公共区 (prompt_gen 对公共电梯厅/楼梯间 skip, 不出家具短语)。
    for r in G.get("rooms", []):
        if "rect" in r and (r.get("label") or {}).get("zh") not in ("公共电梯厅", "公共楼梯间"):
            return r["id"]
    raise AssertionError("D geometry 无带 rect 的非公共房间")


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


# ---- decor-b3-fix: 贴墙配饰 AXON 落位三项豁免 (与 D13 对齐, 不硬阻断 AI 出图) ---- #
_AXON_PLACEMENT_CODES = {
    "AXON_OUTSIDE_ROOM_BBOX",
    "AXON_WALL_THICKNESS_COLLISION",
    "AXON_CENTER_OUTSIDE_ROOM",
}


def test_wall_hugging_decor_does_not_block_ai_render():
    """贴墙软装 (挂画/窗帘) 在轴测校验中不产生 ERROR —— validation.ok 保持 True。

    复现用户报的误判: 户型 v7 生成轴测图被'场景校验未通过'阻断, 但编辑器无错。
    根因是 build_scene D13 让贴墙件豁免内缩归一化, 但 _validate_items 的 AXON 路径
    未同步豁免 → 贴墙件被判越界/穿墙 ERROR。修复后三项落位检查降为 WARN。
    """
    G = geometry.load(D_GEOM)
    geo = geometry.derive(G)
    rid = _first_room_id(G)
    # 挂画 + 窗帘紧贴左墙 (dx=0), 与用户在编辑器手放的自然位置一致
    wall_art = {"t": "wall_art", "room_id": rid, "dx": 0, "dy": 100,
                "w": 80, "h": 8, "orient": "W"}
    curtain = {"t": "curtain", "room_id": rid, "dx": 0, "dy": 300,
               "w": 120, "h": 10, "orient": "W"}
    sc = scene.build_scene(G, geo, [wall_art, curtain])
    val = sc["validation"]
    assert val["ok"], f"贴墙软装不应阻断出图, 实得 ERROR: {val['errors']}"
    blocking = [i for i in val["issues"]
                if i["level"] == "ERROR" and i["code"] in _AXON_PLACEMENT_CODES]
    assert not blocking, f"贴墙软装的越界/穿墙/中心越界不应为 ERROR: {blocking}"


def test_wall_hugging_exemption_is_type_scoped():
    """豁免仅限 NOSHADOW_TYPES —— 同一越界几何下, 贴墙件 (wall_art) 降 WARN,
    非贴墙件 (wardrobe) 仍 ERROR。证明修复没有把 AXON 硬门整体关掉。"""
    G = geometry.load(D_GEOM)
    geo = geometry.derive(G)
    rid = _first_room_id(G)
    base = scene.build_scene(G, geo, [])
    room = {r["id"]: r for r in base["rooms"]}[rid]
    rx, ry = float(room["rect"][0]), float(room["rect"][1])

    def _axon(t, idx, h):
        # 左边缘嵌进墙 4px -> 必触发 AXON_OUTSIDE_ROOM_BBOX (box.x0 < 房 rect 左界)
        return {"t": t, "_room_id": rid, "_index": idx,
                "x": rx - 4, "y": ry + 60, "w": 80, "h": h}

    base["furniture"] = []
    base["dangling_furniture"] = []
    base["axon_furniture"] = [_axon("wall_art", 0, 8), _axon("wardrobe", 1, 40)]
    val = scene.validate_scene(base)

    by_idx: dict = {}
    for i in val["issues"]:
        by_idx.setdefault(i.get("index"), []).append(i)

    wall_art_placement = [i for i in by_idx.get(0, []) if i["code"] in _AXON_PLACEMENT_CODES]
    assert wall_art_placement, "wall_art 同几何应触发落位检查 (对照有效性)"
    assert all(i["level"] == "WARN" for i in wall_art_placement), \
        f"贴墙 wall_art 落位检查应降为 WARN: {wall_art_placement}"

    wardrobe_placement = [i for i in by_idx.get(1, []) if i["code"] in _AXON_PLACEMENT_CODES]
    assert any(i["level"] == "ERROR" for i in wardrobe_placement), \
        f"非贴墙 wardrobe 同几何应仍触发 AXON ERROR (豁免须类型限定): {wardrobe_placement}"


# ---- byte-safe 前提: D 活数据不含配饰类型 ---- #
def test_d_data_has_no_decor_types():
    import json
    sch = os.path.join(REPO, "data", "projects", "D", "schemes", "default", "furniture.json")
    items = json.load(open(sch, encoding="utf-8"))
    present = {it.get("t") for it in items}
    assert not (present & set(DECOR)), "D 默认方案不应含配饰类型 (保 golden 字节)"


# ==================== F003 附着配饰 ====================
ATTACH = ["cushions", "bedding", "table_lamp", "vase", "ornament"]


def test_attach_registry_and_helpers():
    for t in ATTACH:
        assert catalog.is_attach_type(t)
        assert catalog.attach_en(t)
        assert catalog.DECOR_ATTACH[t]["hosts"]
    # mount_z 对齐实际 3D 模型顶面 (D12)
    assert catalog.attach_mount_z("cushions", "sofa") == 470       # m_sofa 座面
    assert catalog.attach_mount_z("cushions", "bed") == 480        # m_bed 被面
    assert catalog.attach_mount_z("vase", "coffee_table") == 420   # m_coffee 台面
    assert catalog.attach_mount_z("table_lamp", "console_table") == 800
    # 不兼容宿主返回 None
    assert catalog.attach_mount_z("bedding", "sofa") is None
    assert catalog.attach_mount_z("cushions", "toilet") is None


def test_attach_excludes_round_hosts():
    # 圆形宿主 (draw_round 路径) 不作宿主 (D12)
    for round_t in catalog.ROUND_TYPES:
        assert catalog.attach_types_for_host(round_t) == [], f"{round_t} 圆形不应作宿主"


def test_attach_sanitize_strips_invalid():
    kept, warns = catalog.sanitize_decor("sofa", [{"t": "cushions"}])
    assert kept == [{"t": "cushions"}] and not warns
    kept, warns = catalog.sanitize_decor("sofa", [{"t": "nope"}])       # 未知类型
    assert kept == [] and warns
    kept, warns = catalog.sanitize_decor("sofa", [{"t": "bedding"}])    # 不兼容宿主
    assert kept == [] and warns
    kept, _ = catalog.sanitize_decor("sofa", [{"t": "cushions"}, {"t": "cushions"}])  # 去重
    assert kept == [{"t": "cushions"}]


def test_attach_prims_render_at_host_top():
    host = {"t": "sofa", "x": 100, "y": 100, "w": 210, "h": 90, "orient": "N"}
    assert axon._attach_prims(host) == ([], "")  # 无 decor -> 空
    ebx, _svg = axon._attach_prims({**host, "decor": [{"t": "cushions"}]})
    assert ebx and all(b[4] >= 470 for b in ebx), "抱枕应在座面 470 之上"
    # 台灯: 发光点 svg
    lamp = {"t": "nightstand", "x": 100, "y": 100, "w": 40, "h": 45, "decor": [{"t": "table_lamp"}]}
    ebx2, svg2 = axon._attach_prims(lamp)
    assert ebx2 and "url(#glow)" in svg2
    # 非法宿主 (wall_art 挂 cushions) -> 剥离空
    bad = {"t": "wall_art", "x": 100, "y": 100, "w": 80, "h": 8, "decor": [{"t": "cushions"}]}
    assert axon._attach_prims(bad) == ([], "")


def test_attach_render_integration_bytesafe():
    geom = _geom()
    sofa = {"t": "sofa", "x": 500, "y": 500, "w": 210, "h": 90, "orient": "N"}
    base = axon.render(geom, [sofa], mode="photo")
    # 无 decor 键: 逐字节与原来一致 (byte-safe)
    assert axon.render(geom, [{**sofa}], mode="photo") == base
    # 带 decor: SVG 变长 (多出附着图元)
    withd = axon.render(geom, [{**sofa, "decor": [{"t": "cushions"}]}], mode="photo")
    assert withd != base and len(withd) > len(base)


# ==================== F004 prompt 贯通 ====================
from floorplan_core import prompt_gen  # noqa: E402


def test_prompt_independent_decor_phrases():
    G = geometry.load(D_GEOM)
    rid = _first_room_id(G)
    furn = [{"t": "wall_art", "room_id": rid, "dx": 10, "dy": 10, "w": 80, "h": 8, "orient": "N"},
            {"t": "curtain", "room_id": rid, "dx": 100, "dy": 10, "w": 120, "h": 10, "orient": "N"}]
    p = prompt_gen.generate(furn, G)
    assert "framed wall art" in p and "floor-length curtains" in p


def test_prompt_attached_decor_folds_into_host():
    G = geometry.load(D_GEOM)
    rid = _first_room_id(G)
    sofa = [{"t": "sofa", "room_id": rid, "dx": 10, "dy": 10, "w": 210, "h": 90,
             "orient": "N", "decor": [{"t": "cushions"}]}]
    assert "a sofa with decorative cushions" in prompt_gen.generate(sofa, G)
    # 多配饰: 'a vase with flowers and decorative ornaments'
    ct = [{"t": "coffee_table", "room_id": rid, "dx": 10, "dy": 10, "w": 100, "h": 60,
           "orient": "N", "decor": [{"t": "vase"}, {"t": "ornament"}]}]
    assert "a coffee table with a vase with flowers and decorative ornaments" \
        in prompt_gen.generate(ct, G)


def test_prompt_no_decor_is_byte_identical():
    G = geometry.load(D_GEOM)
    rid = _first_room_id(G)
    sofa = {"t": "sofa", "room_id": rid, "dx": 10, "dy": 10, "w": 210, "h": 90, "orient": "N"}
    base = prompt_gen.generate([sofa], G)
    assert prompt_gen.generate([{**sofa}], G) == base          # 无 decor 键
    assert prompt_gen.generate([{**sofa, "decor": []}], G) == base  # 空 decor
    # 全非法 decor 被剥离 -> 逐字节等价
    assert prompt_gen.generate([{**sofa, "decor": [{"t": "bedding"}]}], G) == base
