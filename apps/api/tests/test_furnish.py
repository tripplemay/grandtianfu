# -*- coding: utf-8 -*-
"""AI 软装风格服务 (Phase C-2): 布局锁定, AI 出 style_prompt + 同组换件 (不落位)。"""
import os

import furnish
from floorplan_core import geometry

_REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload
        self.messages = None
        self.model = None

    def chat_json(self, messages, *, model=None, temperature=0.2):
        self.messages = messages
        self.model = model
        return self.payload


def _G():
    return geometry.load(os.path.join(_REPO, "data", "projects", "D", "geometry.json"))


# 锁定布局种子 (基线拷来的): r_live 有沙发/茶几/绿植。
BASE = [
    {"t": "sofa", "room_id": "r_live", "dx": 100, "dy": 50, "w": 210, "h": 90, "orient": "N"},
    {"t": "coffee_table", "room_id": "r_live", "dx": 130, "dy": 160, "w": 100, "h": 60},
    {"t": "plant", "room_id": "r_live", "dcx": 300, "dcy": 40, "r": 20},
]


def test_layout_summary_groups_by_room_with_swap_options():
    G = _G()
    summary = furnish.layout_summary(BASE, G)
    assert len(summary) == 1 and summary[0]["room_id"] == "r_live"
    pieces = {p["t"]: p for p in summary[0]["pieces"]}
    assert pieces["sofa"]["count"] == 1
    # 沙发有同组可换件 (chaise), 绿植是单件组无可换。
    assert any(o["t"] == "chaise" for o in pieces["sofa"]["swap_options"])
    assert "swap_options" not in pieces["plant"]


def test_build_messages_include_style_layout_count():
    G = _G()
    summary = furnish.layout_summary(BASE, G)
    messages = furnish.build_messages("现代轻奢", summary, 2)
    assert messages[0]["role"] == "system"
    assert "锁定" in messages[0]["content"] and "style_prompt" in messages[0]["content"]
    user = messages[1]["content"]
    assert "现代轻奢" in user
    assert "候选方案数量: 2" in user
    assert "swap_options" in user


def test_validate_candidates_accepts_same_group_swap_rejects_others():
    room_ids = {"r_live"}
    raw = {
        "schemes": [
            {
                "name": "A",
                "style_prompt": "  暖木原色  ",
                "swaps": [
                    {"room_id": "r_live", "from": "sofa", "to": "chaise"},  # 同组 OK
                    {"room_id": "r_live", "from": "sofa", "to": "bed"},  # 跨组 拒
                    {"room_id": "nope", "from": "sofa", "to": "chaise"},  # 未知房 拒
                    {"room_id": "r_live", "from": "desk", "to": "console_table"},  # 源件不存在 拒
                ],
            }
        ]
    }
    out, warnings = furnish.validate_candidates(raw, BASE, room_ids, requested_count=1)
    assert out[0]["style_prompt"] == "暖木原色"
    assert out[0]["swaps"] == [{"room_id": "r_live", "from": "sofa", "to": "chaise"}]
    assert any("非同组" in w for w in warnings)
    assert any("未知房间" in w for w in warnings)
    assert any("无 desk 可换" in w for w in warnings)


def test_swap_item_type_keeps_center_rect_and_switches_to_circle():
    sofa = BASE[0]  # center = (205, 95)
    chaise = furnish._swap_item_type(sofa, "chaise")  # 矩形→矩形
    assert chaise["t"] == "chaise" and chaise["w"] == 105 and chaise["h"] == 170
    assert abs((chaise["dx"] + 105 / 2) - 205) <= 1
    assert abs((chaise["dy"] + 170 / 2) - 95) <= 1
    assert chaise["orient"] == "N"  # 朝向保留
    rt = furnish._swap_item_type(sofa, "round_table")  # 矩形→圆形
    assert rt["t"] == "round_table" and "r" in rt and "w" not in rt
    assert rt["dcx"] == 205 and rt["dcy"] == 95 and "orient" not in rt


def test_generate_candidates_keeps_layout_and_applies_swap():
    G = _G()
    provider = FakeProvider(
        {
            "schemes": [
                {
                    "name": "轻奢 A",
                    "style_prompt": "现代轻奢, 米白+黄铜",
                    "swaps": [{"room_id": "r_live", "from": "sofa", "to": "chaise"}],
                },
                {"name": "自然", "style_prompt": "原木自然"},
            ]
        }
    )
    result = furnish.generate_candidates(
        G, provider, base_furniture=BASE, style_prompt="现代轻奢", count=2, base_scheme_id="default"
    )
    assert len(result["schemes"]) == 2
    first = result["schemes"][0]
    assert first["source"] == "ai" and first["base_scheme_id"] == "default"
    assert first["style_prompt"] == "现代轻奢, 米白+黄铜"  # AI 富化 prompt
    types = [it["t"] for it in first["furniture"]]
    assert "chaise" in types and "sofa" not in types  # 沙发被换成贵妃
    assert "coffee_table" in types and "plant" in types  # 其余布局不动
    assert len(first["furniture"]) == len(BASE)  # 不增删件
    # 第二候选无 swaps -> 原布局不变, style_prompt 富化
    second = result["schemes"][1]
    assert [it["t"] for it in second["furniture"]] == ["sofa", "coffee_table", "plant"]
    assert second["style_prompt"] == "原木自然"


def test_generate_candidates_falls_back_to_base_layout_when_llm_empty():
    G = _G()
    provider = FakeProvider({"schemes": []})
    result = furnish.generate_candidates(
        G, provider, base_furniture=BASE, style_prompt="极简", count=1, base_scheme_id="default"
    )
    assert len(result["schemes"]) == 1
    # 原布局原样保留, style_prompt 回退用户输入。
    assert [it["t"] for it in result["schemes"][0]["furniture"]] == ["sofa", "coffee_table", "plant"]
    assert result["schemes"][0]["style_prompt"] == "极简"
    assert any("未返回有效候选" in w for w in result["warnings"])


def test_generate_candidates_warns_on_fewer_candidates():
    G = _G()
    provider = FakeProvider({"schemes": [{"name": "唯一", "style_prompt": "现代"}]})
    result = furnish.generate_candidates(
        G, provider, base_furniture=BASE, style_prompt="现代", count=3, base_scheme_id="default"
    )
    assert len(result["schemes"]) == 1
    assert any("仅返回 1 个有效候选" in w for w in result["warnings"])


def test_swap_preserves_id_color_zorder_and_drops_type_specific_keys():
    # 换件白名单 (与前端同构): 保 id/color/zorder/orient, 丢类型专属键 (seats)。
    item = {
        "t": "dining_table", "room_id": "r_live", "dx": 100, "dy": 50, "w": 300, "h": 110,
        "id": "f_1", "color": "#abcabc", "zorder": 3, "orient": "N", "seats": 8,
    }
    out = furnish._swap_item_type(item, "island")  # dining 同组
    assert out["t"] == "island"
    assert out["id"] == "f_1" and out["color"] == "#abcabc" and out["zorder"] == 3
    assert out["orient"] == "N"
    assert "seats" not in out  # 类型专属键不残留


def test_swap_transfers_compatible_decor_and_strips_incompatible():
    # decor-b1 D11: 换件透传附着配饰, 按新宿主重新校验 (部分保留部分剥离)。
    # bed 挂 cushions + bedding; 换 sofa: sofa 是 cushions 宿主但非 bedding 宿主 -> 保 cushions 剥 bedding。
    bed = {"t": "bed", "room_id": "r_bed", "dx": 100, "dy": 50, "w": 180, "h": 200,
           "orient": "N", "decor": [{"t": "cushions"}, {"t": "bedding"}]}
    sofa = furnish._swap_item_type(bed, "sofa")
    assert sofa["decor"] == [{"t": "cushions"}], "sofa 保 cushions 剥 bedding"
    # 换 coffee_table: 非 cushions/bedding 宿主 -> 全剥。
    ct = furnish._swap_item_type(bed, "coffee_table")
    assert "decor" not in ct
    # 换圆形件 (round_table): 圆形不作宿主 -> 全剥。
    rt = furnish._swap_item_type(bed, "round_table")
    assert "decor" not in rt


def test_validate_candidates_filters_before_truncate():
    # 坏项在前不应挤掉窗口外的有效候选 (先过滤再截断)。
    raw = {"schemes": ["坏占位", {"name": "暖", "style_prompt": "暖木"}, {"name": "冷", "style_prompt": "冷灰"}]}
    out, warnings = furnish.validate_candidates(raw, BASE, {"r_live"}, requested_count=2)
    assert [c["name"] for c in out] == ["暖", "冷"]
    assert any("格式无效" in w for w in warnings)


def test_validate_candidates_ignores_non_scalar_swap_fields():
    # LLM 偶发把 from/to 返成数组/对象, 不能让 swap_group 抛 TypeError。
    raw = {"schemes": [{"name": "A", "swaps": [{"room_id": "r_live", "from": ["sofa"], "to": "chaise"}]}]}
    out, warnings = furnish.validate_candidates(raw, BASE, {"r_live"}, requested_count=1)
    assert out[0]["swaps"] == []
    assert any("非字符串" in w for w in warnings)
