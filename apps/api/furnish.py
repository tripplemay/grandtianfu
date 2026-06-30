# -*- coding: utf-8 -*-
"""AI furniture planning service.

LLM output is intentionally limited to room/type/count selection. Deterministic
layout converts validated selections to coordinates; catalog expands renderable
appearance.
"""
from __future__ import annotations

import json
from typing import Any

from floorplan_core import catalog, geometry, layout, room_brief

MAX_COUNT_PER_TYPE = 4


def room_briefs(G: dict) -> list[dict]:
    return room_brief.build_briefs(G, geometry.derive(G))


def build_messages(style_prompt: str, briefs: list[dict], count: int) -> list[dict]:
    system = (
        "你是室内软装方案助理。只选择每个房间 furniture_options 中允许的家具类型和数量;"
        "不要输出坐标、尺寸、颜色或解释。必须返回 JSON object。"
    )
    user = {
        "style_prompt": style_prompt,
        "candidate_count": count,
        "instructions": [
            "输出 schemes 数组,长度尽量等于候选方案数量",
            "每个 scheme 包含 name 和 rooms",
            "每个 room 包含 room_id 和 items",
            "每个 item 只包含 t 和 count",
        ],
        "rooms": briefs,
    }
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": f"候选方案数量: {count}\n" + json.dumps(user, ensure_ascii=False),
        },
    ]


def _brief_maps(briefs: list[dict]) -> tuple[dict[str, dict], dict[str, set[str]]]:
    by_room = {b["room_id"]: b for b in briefs}
    allowed = {b["room_id"]: set(b.get("furniture_options") or []) for b in briefs}
    return by_room, allowed


def _int_count(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def validate_selection(
    raw: dict, briefs: list[dict], *, requested_count: int
) -> tuple[list[dict], list[str]]:
    by_room, allowed = _brief_maps(briefs)
    warnings: list[str] = []
    schemes_in = raw.get("schemes") if isinstance(raw, dict) else None
    if not isinstance(schemes_in, list):
        warnings.append("LLM 未返回 schemes 数组")
        return [], warnings
    out: list[dict] = []
    for scheme_idx, scheme in enumerate(schemes_in[: max(1, requested_count)]):
        if not isinstance(scheme, dict):
            warnings.append(f"方案 {scheme_idx + 1} 格式无效")
            continue
        rooms_out: list[dict] = []
        for room in scheme.get("rooms") or []:
            if not isinstance(room, dict):
                continue
            room_id = room.get("room_id")
            if room_id not in by_room:
                warnings.append(f"未知房间: {room_id}")
                continue
            items_out: list[dict] = []
            for item in room.get("items") or []:
                if not isinstance(item, dict):
                    continue
                t = item.get("t")
                if t not in allowed[room_id]:
                    warnings.append(f"房间 {room_id} 不允许类型: {t}")
                    continue
                count = _int_count(item.get("count", 1))
                if count <= 0:
                    continue
                if count > MAX_COUNT_PER_TYPE:
                    warnings.append(f"房间 {room_id} 类型 {t} 数量过大,已降级")
                    count = MAX_COUNT_PER_TYPE
                items_out.append({"t": t, "count": count})
            if items_out:
                rooms_out.append({"room_id": room_id, "items": items_out})
        out.append({"name": scheme.get("name") or "", "rooms": rooms_out})
    return out, warnings


def generate_candidates(
    G: dict,
    provider,
    *,
    style_prompt: str,
    count: int,
    base_scheme_id: str,
    model: str | None = None,
) -> dict:
    briefs = room_briefs(G)
    messages = build_messages(style_prompt, briefs, count)
    raw = provider.chat_json(messages, model=model, temperature=0.2)
    selected, warnings = validate_selection(raw, briefs, requested_count=count)
    if not selected:
        warnings.append("LLM 未返回有效方案,已创建空候选")
        selected = [{"name": "AI 方案 1", "rooms": []}]
    schemes: list[dict] = []
    for idx, scheme in enumerate(selected[:count], start=1):
        placed = layout.plan(G, scheme["rooms"])
        furniture = catalog.expand(placed)
        name = (scheme.get("name") or "").strip() or f"AI 方案 {idx}"
        schemes.append(
            {
                "name": name,
                "source": "ai",
                "style_prompt": style_prompt,
                "base_scheme_id": base_scheme_id,
                "furniture": furniture,
            }
        )
    return {"schemes": schemes, "warnings": warnings}
