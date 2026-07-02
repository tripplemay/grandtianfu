# -*- coding: utf-8 -*-
"""Deterministic furniture placement from controlled type/count selections.

The LLM selects furniture types and counts only. This module converts those
validated selections into room-relative placements that the editor can refine.

Placement rules (all deterministic):
- furniture center stays inside the target room (existing invariant);
- footprints must not intersect door clearance zones (门口净空, 避免家具挡门);
- footprints must not overlap other placed furniture in the same room (留 gap);
- items that cannot fit produce a human-readable warning instead of vanishing.
"""
from __future__ import annotations

from . import catalog
from . import geometry as _geometry

# 同房家具间最小间隙 (px, 1px=10mm)。
ITEM_GAP = 2.0
# 门口净空沿墙方向外扩 (px)。
DOOR_MARGIN = 2.0


def _room_map(G: dict) -> dict[str, dict]:
    return {r.get("id"): r for r in G.get("rooms", []) if r.get("id")}


def _door_zones(rect, doors, eps) -> list[tuple[float, float, float, float]]:
    """房间内的门口净空区 (room-relative x0,y0,x1,y1)。

    与 room_brief._edge_openings 相同的四壁匹配逻辑; 净空深度 = 门洞宽 (门扇回转半径),
    沿墙方向 = 门洞 span ± DOOR_MARGIN。家具 footprint 不得与净空区相交。
    """
    x, y, w, h = [float(v) for v in rect]
    zones: list[tuple[float, float, float, float]] = []
    for op in doors or []:
        axis = op.get("axis")
        at = op.get("at")
        span = op.get("span") or [0, 0]
        if axis is None or at is None:
            continue
        s0, s1 = float(span[0]), float(span[1])
        depth = max(float(op.get("width") or 0), s1 - s0)
        if depth <= 0:
            continue
        if axis == "v" and s1 > y and s0 < y + h:
            lo, hi = s0 - y - DOOR_MARGIN, s1 - y + DOOR_MARGIN
            if abs(at - x) <= eps:  # W 墙
                zones.append((0.0, lo, depth, hi))
            elif abs(at - (x + w)) <= eps:  # E 墙
                zones.append((w - depth, lo, w, hi))
        elif axis == "h" and s1 > x and s0 < x + w:
            lo, hi = s0 - x - DOOR_MARGIN, s1 - x + DOOR_MARGIN
            if abs(at - y) <= eps:  # N 墙
                zones.append((lo, 0.0, hi, depth))
            elif abs(at - (y + h)) <= eps:  # S 墙
                zones.append((lo, h - depth, hi, h))
    return zones


def _footprint(app: dict, cx: float, cy: float) -> tuple[float, float, float, float]:
    if "r" in app:
        r = float(app["r"])
        return (cx - r, cy - r, cx + r, cy + r)
    half_w = float(app["w"]) / 2
    half_h = float(app["h"]) / 2
    return (cx - half_w, cy - half_h, cx + half_w, cy + half_h)


def _boxes_intersect(a, b, gap: float = 0.0) -> bool:
    return (
        a[0] < b[2] + gap
        and b[0] < a[2] + gap
        and a[1] < b[3] + gap
        and b[1] < a[3] + gap
    )


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


def plan_report(G: dict, selections: list[dict]) -> tuple[list[dict], list[str]]:
    """Create placement-only furniture items + human-readable warnings.

    Unknown rooms/types are skipped defensively; validation should normally have
    removed them before this point. Counts are capped by available fitting slots;
    slots must avoid door clearance zones and already-placed footprints. Items
    that cannot fit are reported in warnings instead of vanishing silently.
    """
    rooms = _room_map(G)
    # 门几何: 从派生结果取 (与 room_brief 同源); 极简测试 G 可能无法 derive, 安全回退无门。
    try:
        doors = _geometry.derive(G).get("doors", []) or []
    except Exception:  # noqa: BLE001 - 布局对派生失败降级为无门避让, 不阻断。
        doors = []
    try:
        eps = float((G.get("meta") or {}).get("eps", 1) or 1)
    except (TypeError, ValueError):
        eps = 1.0
    out: list[dict] = []
    warnings: list[str] = []
    for room_sel in selections or []:
        room_id = room_sel.get("room_id")
        room = rooms.get(room_id)
        if not room:
            continue
        rect = room.get("rect") or [0, 0, 0, 0]
        room_w = float(rect[2])
        room_h = float(rect[3])
        room_name = (room.get("label") or {}).get("zh") or room_id
        zones = _door_zones(rect, doors, eps)
        used: set[tuple[float, float]] = set()
        placed_boxes: list[tuple[float, float, float, float]] = []
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
                fp = _footprint(app, cx, cy)
                if any(_boxes_intersect(fp, z) for z in zones):
                    continue
                if any(_boxes_intersect(fp, b, ITEM_GAP) for b in placed_boxes):
                    continue
                out.append(_item_at(t, room_id, app, cx, cy))
                used.add(key)
                placed_boxes.append(fp)
                placed += 1
                if placed >= count:
                    break
            if placed < count:
                warnings.append(
                    f"{room_name}: {t} 仅放下 {placed}/{count} 件"
                    "(空间不足或需避让门口/其他家具)"
                )
    return out, warnings


def plan(G: dict, selections: list[dict]) -> list[dict]:
    """Backwards-compatible wrapper: placements only, warnings dropped."""
    return plan_report(G, selections)[0]
