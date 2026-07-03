# -*- coding: utf-8 -*-
"""P2 首批扩充: 声明式基元 m_from_spec + 12 新类型 + rug 升格 + round_chair 注册。"""
from floorplan_core import axon, catalog

NEW_RECT = [
    "tv", "floor_lamp", "armchair", "ottoman", "sideboard", "wine_cabinet",
    "side_table", "dresser", "chest", "kids_bed", "mirror", "shoe_cabinet",
]


def _item(t: str, orient: str = "N") -> dict:
    s = catalog.CATALOG[t]
    it = {"t": t, "x": 100, "y": 100, "w": s["w"], "h": s["h"], "orient": orient}
    if "color" in s:
        it["color"] = s["color"]
    if "z" in s:
        it["z"] = s["z"]
    return it


def test_new_rect_types_registered_and_emit_valid_boxes():
    """12 新矩形件都在 MODELS 且出合法 (x0,y0,x1,y1,z0,z1,color) 盒, z 不穿墙。"""
    for t in NEW_RECT:
        assert t in axon.MODELS, f"{t} 未注册 axon.MODELS"
        boxes, _extra = axon.MODELS[t](_item(t))
        assert boxes, f"{t} 无 box 输出"
        for b in boxes:
            assert len(b) == 7, f"{t} box 非 7 元组: {b}"
            x0, y0, x1, y1, z0, z1, color = b
            assert x1 > x0 and y1 > y0 and z1 > z0, f"{t} 退化盒 {b}"
            assert z1 <= 1450, f"{t} z1={z1} 穿墙 (>1450)"
            assert isinstance(color, str) and color.startswith("#")


def test_spec_accents_present():
    """spec 配件: 电视有发光屏, 落地灯有发光罩, 穿衣镜有竖直镜面。"""
    _, tv_extra = axon.MODELS["tv"](_item("tv"))
    assert "filter=\"url(#glow)\"" in tv_extra and "<line" in tv_extra
    _, lamp_extra = axon.MODELS["floor_lamp"](_item("floor_lamp"))
    assert "<circle" in lamp_extra and "url(#glow)" in lamp_extra
    _, mirror_extra = axon.MODELS["mirror"](_item("mirror"))
    assert "<polygon" in mirror_extra  # 竖直镜面


def test_armchair_backrest_follows_orient():
    """扶手椅靠背随 orient 换侧 (声明式 edge 'orient' 生效)。"""
    boxes_n, _ = axon.MODELS["armchair"](_item("armchair", "N"))
    boxes_s, _ = axon.MODELS["armchair"](_item("armchair", "S"))
    # 靠背是 z 顶最高的盒 (到 720); N 时贴 y0, S 时贴 y1。
    back_n = max(boxes_n, key=lambda b: b[5])
    back_s = max(boxes_s, key=lambda b: b[5])
    assert back_n[1] < back_s[1], "靠背未随 orient N->S 从北侧移到南侧"


def test_round_chair_registered_round_and_draws():
    """round_chair 补注册: 圆形件, 在 ROUND_TYPES, draw_round 出圆座不崩。"""
    assert catalog.is_round("round_chair")
    assert "round_chair" in catalog.ROUND_TYPES
    frags = []
    axon.draw_round(
        {"t": "round_chair", "cx": 300, "cy": 300, "r": 30, "color": "#3d5440"},
        lambda k, v: frags.append(v),
        lambda *a: None,
    )
    assert frags and any("<ellipse" in f for f in frags)


def test_rug_promoted_but_ai_excluded():
    """rug 升格入目录 (有 appearance + 真实尺寸), 但 AI 不选 (rooms 空 -> 任何房都不出)。"""
    app = catalog.appearance("rug")
    assert app == {"w": 200, "h": 140, "color": "#b8ad9a"}
    for rt in ("living", "bedroom", "wet", "corridor"):
        assert "rug" not in catalog.types_for_room(rt)


def test_to_public_serves_new_types_with_sizes():
    """/api/catalog 出参覆盖新类型 + 真实尺寸 + 分组。"""
    by_t = {e["t"]: e for e in catalog.to_public()}
    for t in NEW_RECT + ["rug", "round_chair"]:
        assert t in by_t, f"{t} 未随 to_public 下发"
    assert by_t["kids_bed"]["w"] == 100 and by_t["kids_bed"]["h"] == 180
    assert by_t["round_chair"]["shape"] == "round" and by_t["round_chair"]["r"] == 30
    assert by_t["wine_cabinet"]["tall"] is True
