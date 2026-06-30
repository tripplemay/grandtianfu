# -*- coding: utf-8 -*-
"""Deterministic furniture placement from controlled type/count selections.

The LLM selects furniture types and counts only. This module converts those
validated selections into room-relative placements that the editor can refine.
"""
from __future__ import annotations

from . import catalog


def _room_map(G: dict) -> dict[str, dict]:
    return {r.get("id"): r for r in G.get("rooms", []) if r.get("id")}


def _slots(width: float, depth: float, count: int) -> list[tuple[float, float]]:
    """Stable room-relative center candidates, distributed from walls inward."""
    if count <= 0:
        return []
    xs = [0.24, 0.5, 0.76, 0.38, 0.62]
    ys = [0.24, 0.5, 0.76, 0.38, 0.62]
    out: list[tuple[float, float]] = []
    for y in ys:
        for x in xs:
            out.append((round(width * x, 3), round(depth * y, 3)))
    out.append((round(width / 2, 3), round(depth / 2, 3)))
    return out


def _fits(app: dict, room_w: float, room_h: float, cx: float, cy: float) -> bool:
    if "r" in app:
        r = app["r"]
        return r <= cx <= room_w - r and r <= cy <= room_h - r
    half_w = app["w"] / 2
    half_h = app["h"] / 2
    return half_w <= cx <= room_w - half_w and half_h <= cy <= room_h - half_h


def _item_at(t: str, room_id: str, app: dict, cx: float, cy: float) -> dict:
    if "r" in app:
        return {"t": t, "room_id": room_id, "dcx": round(cx, 1), "dcy": round(cy, 1)}
    return {
        "t": t,
        "room_id": room_id,
        "dx": round(cx - app["w"] / 2, 1),
        "dy": round(cy - app["h"] / 2, 1),
    }


def plan(G: dict, selections: list[dict]) -> list[dict]:
    """Create placement-only furniture items for validated room selections.

    Unknown rooms/types are skipped defensively; validation should normally have
    removed them before this point. Counts are capped by available fitting slots.
    """
    rooms = _room_map(G)
    out: list[dict] = []
    for room_sel in selections or []:
        room_id = room_sel.get("room_id")
        room = rooms.get(room_id)
        if not room:
            continue
        rect = room.get("rect") or [0, 0, 0, 0]
        room_w = float(rect[2])
        room_h = float(rect[3])
        used: set[tuple[float, float]] = set()
        slots = _slots(room_w, room_h, 32)
        for spec in room_sel.get("items", []) or []:
            t = spec.get("t")
            app = catalog.appearance(t)
            if app is None:
                continue
            try:
                count = max(0, min(int(spec.get("count", 1)), 8))
            except (TypeError, ValueError):
                count = 1
            placed = 0
            for cx, cy in slots:
                key = (cx, cy)
                if key in used or not _fits(app, room_w, room_h, cx, cy):
                    continue
                out.append(_item_at(t, room_id, app, cx, cy))
                used.add(key)
                placed += 1
                if placed >= count:
                    break
    return out
