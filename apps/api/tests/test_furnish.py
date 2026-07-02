# -*- coding: utf-8 -*-
"""AI furnish planner: prompt, validation, layout, catalog expansion."""
import os

import pytest

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


def test_build_messages_include_style_count_and_room_options():
    G = _G()
    briefs = furnish.room_briefs(G)

    messages = furnish.build_messages("现代轻奢", briefs, 2)

    assert messages[0]["role"] == "system"
    assert "只选择" in messages[0]["content"]
    user = messages[1]["content"]
    assert "现代轻奢" in user
    assert "候选方案数量: 2" in user
    assert "furniture_options" in user


def test_validate_selection_rejects_unknown_room_and_type_and_caps_count():
    G = _G()
    briefs = furnish.room_briefs(G)
    raw = {
        "schemes": [
            {
                "name": "A",
                "rooms": [
                    {"room_id": "nope", "items": [{"t": "sofa", "count": 1}]},
                    {"room_id": "r_live", "items": [{"t": "sofa", "count": 99}, {"t": "bed", "count": 1}]},
                ],
            }
        ]
    }

    selected, warnings = furnish.validate_selection(raw, briefs, requested_count=1)

    assert selected == [
        {
            "name": "A",
            "rooms": [{"room_id": "r_live", "items": [{"t": "sofa", "count": 4}]}],
        }
    ]
    assert any("未知房间" in w for w in warnings)
    assert any("不允许类型" in w for w in warnings)
    assert any("数量过大" in w for w in warnings)


def test_generate_candidates_expands_catalog_and_names_schemes():
    G = _G()
    provider = FakeProvider(
        {
            "schemes": [
                {
                    "name": "轻奢 A",
                    "rooms": [
                        {"room_id": "r_live", "items": [{"t": "sofa", "count": 1}, {"t": "plant", "count": 1}]}
                    ],
                },
                {
                    "rooms": [
                        {"room_id": "r_study", "items": [{"t": "desk", "count": 1}]}
                    ],
                },
            ]
        }
    )

    result = furnish.generate_candidates(
        G,
        provider,
        style_prompt="现代轻奢",
        count=2,
        base_scheme_id="default",
    )

    assert len(result["schemes"]) == 2
    first = result["schemes"][0]
    assert first["name"] == "轻奢 A"
    assert first["source"] == "ai"
    assert first["base_scheme_id"] == "default"
    assert first["style_prompt"] == "现代轻奢"
    assert any(it["t"] == "sofa" and "w" in it and "h" in it for it in first["furniture"])
    assert any(it["t"] == "plant" and "r" in it for it in first["furniture"])
    assert result["schemes"][1]["name"].startswith("AI 方案")
    assert provider.messages is not None


def test_generate_candidates_falls_back_to_single_empty_scheme_when_llm_returns_nothing():
    G = _G()
    provider = FakeProvider({"schemes": []})

    result = furnish.generate_candidates(
        G,
        provider,
        style_prompt="极简",
        count=1,
        base_scheme_id="default",
    )

    assert len(result["schemes"]) == 1
    assert result["schemes"][0]["furniture"] == []
    assert any("未返回有效方案" in w for w in result["warnings"])


def test_validate_selection_warns_on_invalid_and_zero_counts():
    briefs = [
        {"room_id": "r_live", "furniture_options": ["sofa", "plant", "bed"]},
    ]
    raw = {
        "schemes": [
            {
                "name": "A",
                "rooms": [
                    {
                        "room_id": "r_live",
                        "items": [
                            {"t": "sofa", "count": "两个"},
                            {"t": "plant", "count": 0},
                            {"t": "bed", "count": 1},
                        ],
                    }
                ],
            }
        ]
    }

    selected, warnings = furnish.validate_selection(raw, briefs, requested_count=1)

    assert selected[0]["rooms"][0]["items"] == [
        {"t": "sofa", "count": 1},
        {"t": "bed", "count": 1},
    ]
    assert any("数量无效" in w for w in warnings)
    assert any("数量为 0" in w for w in warnings)


def test_generate_candidates_warns_on_fewer_schemes_and_layout_drops():
    provider = FakeProvider(
        {
            "schemes": [
                {
                    "name": "唯一",
                    "rooms": [{"room_id": "r_live", "items": [{"t": "sofa", "count": 4}]}],
                }
            ]
        }
    )

    result = furnish.generate_candidates(
        _G(),
        provider,
        style_prompt="现代",
        count=3,
        base_scheme_id="default",
    )

    assert len(result["schemes"]) == 1
    assert any("仅返回 1 个有效候选" in w for w in result["warnings"])
