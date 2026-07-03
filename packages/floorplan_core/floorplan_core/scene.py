# -*- coding: utf-8 -*-
"""Canonical scene assembly and validation for render/AI workflows.

The source of truth remains structured geometry + furniture JSON. SVG/PNG are
derived artifacts. This module builds a deterministic scene payload that carries
both the original 2D-resolved furniture coordinates and the axon-safe furniture
coordinates used by 3D/isometric rendering.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable

from . import catalog as _catalog

WALL_CLEARANCE = 13.0
WALL_COLLISION_TOLERANCE = 3.0
DEFAULT_WALL_HEIGHT = 1450.0
FURNITURE_TOP_CLEARANCE = 50.0
DEFAULT_MAX_FURNITURE_HEIGHT = DEFAULT_WALL_HEIGHT - FURNITURE_TOP_CLEARANCE

# Renderers for these furniture types have high built-in defaults even when the
# input JSON omits `z`. They must still obey the scene's wall-height contract.
# 高件集合从家具目录 (catalog.tall) 单一真源推导 —— 新增高件只需在目录标 tall=True。
HEIGHT_CONSTRAINED_DEFAULTS = {
    t: DEFAULT_MAX_FURNITURE_HEIGHT for t in _catalog.HEIGHT_CONSTRAINED_TYPES
}

# Wall-like objects are not movable furniture and intentionally follow wall
# height rules elsewhere in the renderer.
STRUCTURAL_HEIGHT_TYPES = {"entry_door", "partition"}


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _json_num(value: float) -> float | int:
    return int(value) if float(value).is_integer() else round(float(value), 3)


def _wall_height(G: dict[str, Any]) -> float:
    value = _num(G.get("meta", {}).get("wall_height_mm"), DEFAULT_WALL_HEIGHT)
    if value is None or value <= 0:
        return DEFAULT_WALL_HEIGHT
    return value


def _max_furniture_height(wall_height: float) -> float:
    return max(0.0, wall_height - FURNITURE_TOP_CLEARANCE)


def _wall_thickness(wall: tuple | list) -> float:
    _, _, _, _, ext, style, _ = wall[:7]
    if ext:
        return 24.0
    if style == "thin":
        return 6.0
    return 14.0


def _wall_bbox(wall: tuple | list) -> dict[str, Any]:
    ax, ay, bx, by, ext, style, lowz = wall[:7]
    t = _wall_thickness(wall)
    horiz = abs(ay - by) < abs(ax - bx)
    if horiz:
        x0, x1 = min(ax, bx), max(ax, bx)
        y0, y1 = ay - t / 2.0, ay + t / 2.0
    else:
        x0, x1 = ax - t / 2.0, ax + t / 2.0
        y0, y1 = min(ay, by), max(ay, by)
    return {
        "x0": float(x0),
        "y0": float(y0),
        "x1": float(x1),
        "y1": float(y1),
        "axis": "h" if horiz else "v",
        "at": float(ay if horiz else ax),
        "thickness": float(t),
        "style": style or "solid",
        "external": bool(ext),
        "lowz": bool(lowz),
        "wall": list(wall[:7]),
    }


def _rect_intersection(a: dict[str, float], b: dict[str, float]) -> tuple[float, float]:
    ox = max(0.0, min(a["x1"], b["x1"]) - max(a["x0"], b["x0"]))
    oy = max(0.0, min(a["y1"], b["y1"]) - max(a["y0"], b["y0"]))
    return ox, oy


def _as_box(it: dict[str, Any]) -> dict[str, float] | None:
    if all(k in it for k in ("x", "y", "w", "h")):
        return {
            "x0": float(it["x"]),
            "y0": float(it["y"]),
            "x1": float(it["x"] + it["w"]),
            "y1": float(it["y"] + it["h"]),
        }
    if all(k in it for k in ("cx", "cy", "r")):
        return {
            "x0": float(it["cx"] - it["r"]),
            "y0": float(it["cy"] - it["r"]),
            "x1": float(it["cx"] + it["r"]),
            "y1": float(it["cy"] + it["r"]),
        }
    return None


def _furniture_render_height(it: dict[str, Any]) -> float | None:
    if str(it.get("t")) in STRUCTURAL_HEIGHT_TYPES:
        return None
    explicit = _num(it.get("z"))
    if explicit is not None:
        return explicit
    return HEIGHT_CONSTRAINED_DEFAULTS.get(str(it.get("t")))


def _center(box: dict[str, float]) -> tuple[float, float]:
    return (box["x0"] + box["x1"]) / 2.0, (box["y0"] + box["y1"]) / 2.0


def _point_in_rect(px: float, py: float, rect: list[float]) -> bool:
    x, y, w, h = rect
    return x <= px <= x + w and y <= py <= y + h


def _room_map(G: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(r["id"]): r for r in G.get("rooms", []) if "id" in r and "rect" in r}


def resolve_furniture(furniture: Iterable[dict[str, Any]], G: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Resolve room-relative furniture coordinates to absolute geometry coords.

    Kept here as the canonical structured-data resolver. `axon.resolve_furniture`
    delegates to this function for backward compatibility.
    """
    if not G:
        return list(furniture)
    rect_of = {rid: room["rect"] for rid, room in _room_map(G).items()}
    out: list[dict[str, Any]] = []
    for it in furniture:
        rid = it.get("room_id")
        if rid is None:
            out.append(it)
            continue
        rect = rect_of.get(str(rid))
        if rect is None:
            continue
        rx, ry = rect[0], rect[1]
        ni = {
            k: deepcopy(v)
            for k, v in it.items()
            if k not in ("room_id", "dx", "dy", "dcx", "dcy")
        }
        if "dcx" in it or "dcy" in it:
            ni["cx"] = rx + it["dcx"]
            ni["cy"] = ry + it["dcy"]
        else:
            ni["x"] = rx + it["dx"]
            ni["y"] = ry + it["dy"]
        out.append(ni)
    return out


def _adjust_rect_to_inner_clearance(
    it: dict[str, Any],
    room_rect: list[float],
    clearance: float,
) -> tuple[dict[str, Any], list[str]]:
    """Clamp rectangular furniture into the room's render-safe inner bounds."""
    if not all(k in it for k in ("x", "y", "w", "h")):
        return it, []
    rx, ry, rw, rh = [float(v) for v in room_rect]
    w, h = float(it["w"]), float(it["h"])
    min_x = rx + clearance
    max_x = rx + rw - clearance - w
    min_y = ry + clearance
    max_y = ry + rh - clearance - h
    if max_x < min_x:
        min_x, max_x = rx, rx + rw - w
    if max_y < min_y:
        min_y, max_y = ry, ry + rh - h
    nx = min(max_x, max(min_x, float(it["x"]))) if max_x >= min_x else float(it["x"])
    ny = min(max_y, max(min_y, float(it["y"]))) if max_y >= min_y else float(it["y"])
    if nx == float(it["x"]) and ny == float(it["y"]):
        return it, []
    out = {**it, "x": nx, "y": ny}
    return out, [f"axon-clearance-shift dx={nx - float(it['x']):.1f} dy={ny - float(it['y']):.1f}"]


def _adjust_rect_size_to_inner_bounds(
    it: dict[str, Any],
    room_rect: list[float],
    clearance: float,
) -> tuple[dict[str, Any], list[str]]:
    """Shrink oversized axon furniture to the room's safe inner rectangle.

    This is a render-scene normalization only. The source furniture JSON remains
    unchanged, but downstream SVG/AI receive a drawable item that can be placed
    inside the room and then moved away from wall thickness.
    """
    if not all(k in it for k in ("x", "y", "w", "h")):
        return it, []
    _rx, _ry, rw, rh = [float(v) for v in room_rect]
    w, h = float(it["w"]), float(it["h"])
    max_w = max(1.0, rw - clearance * 2)
    max_h = max(1.0, rh - clearance * 2)
    nw = min(w, max_w)
    nh = min(h, max_h)
    if nw == w and nh == h:
        return it, []
    out = {**it, "w": _json_num(nw), "h": _json_num(nh)}
    return out, [f"axon-size-clamp dw={nw - w:.1f} dh={nh - h:.1f}"]


def _axis_bounds(origin: float, size: float, item_size: float, clearance: float) -> tuple[float, float]:
    lo = origin + clearance
    hi = origin + size - clearance - item_size
    if hi < lo:
        lo, hi = origin, origin + size - item_size
    return lo, hi


def _clamp_axis(value: float, lo: float, hi: float) -> float:
    if hi < lo:
        return value
    return min(hi, max(lo, value))


def _wall_collision_score(
    box: dict[str, float],
    walls: list[dict[str, Any]],
) -> tuple[float, list[tuple[dict[str, Any], float, float]]]:
    score = 0.0
    collisions: list[tuple[dict[str, Any], float, float]] = []
    for wall in walls:
        ox, oy = _rect_intersection(box, wall)
        if ox > WALL_COLLISION_TOLERANCE and oy > WALL_COLLISION_TOLERANCE:
            score += ox * oy
            collisions.append((wall, ox, oy))
    return score, collisions


def _box_for(x: float, y: float, w: float, h: float) -> dict[str, float]:
    return {
        "x0": x,
        "y0": y,
        "x1": x + w,
        "y1": y + h,
    }


def _box_at(it: dict[str, Any], x: float, y: float) -> dict[str, float]:
    return _box_for(x, y, float(it["w"]), float(it["h"]))


def _intersects(a: dict[str, float], b: dict[str, float]) -> bool:
    return min(a["x1"], b["x1"]) > max(a["x0"], b["x0"]) and min(a["y1"], b["y1"]) > max(
        a["y0"], b["y0"]
    )


def _expanded_box(box: dict[str, Any], margin: float) -> dict[str, float]:
    return {
        "x0": float(box["x0"]) - margin,
        "y0": float(box["y0"]) - margin,
        "x1": float(box["x1"]) + margin,
        "y1": float(box["y1"]) + margin,
    }


def _subtract_obstacle(
    free: dict[str, float],
    obstacle: dict[str, float],
) -> list[dict[str, float]]:
    if not _intersects(free, obstacle):
        return [free]
    ix0 = max(free["x0"], obstacle["x0"])
    iy0 = max(free["y0"], obstacle["y0"])
    ix1 = min(free["x1"], obstacle["x1"])
    iy1 = min(free["y1"], obstacle["y1"])
    out: list[dict[str, float]] = []
    if ix0 > free["x0"]:
        out.append({"x0": free["x0"], "y0": free["y0"], "x1": ix0, "y1": free["y1"]})
    if ix1 < free["x1"]:
        out.append({"x0": ix1, "y0": free["y0"], "x1": free["x1"], "y1": free["y1"]})
    if iy0 > free["y0"]:
        out.append({"x0": free["x0"], "y0": free["y0"], "x1": free["x1"], "y1": iy0})
    if iy1 < free["y1"]:
        out.append({"x0": free["x0"], "y0": iy1, "x1": free["x1"], "y1": free["y1"]})
    return [r for r in out if r["x1"] - r["x0"] >= 1.0 and r["y1"] - r["y0"] >= 1.0]


def _room_free_rects(
    room_rect: list[float],
    walls: list[dict[str, Any]],
    clearance: float,
) -> list[dict[str, float]]:
    rx, ry, rw, rh = [float(v) for v in room_rect]
    base = {
        "x0": rx + clearance,
        "y0": ry + clearance,
        "x1": rx + rw - clearance,
        "y1": ry + rh - clearance,
    }
    if base["x1"] <= base["x0"] or base["y1"] <= base["y0"]:
        base = {"x0": rx, "y0": ry, "x1": rx + rw, "y1": ry + rh}
    rects = [base]
    margin = WALL_COLLISION_TOLERANCE + 1.0
    for wall in walls:
        obstacle = _expanded_box(wall, margin)
        if not _intersects(base, obstacle):
            continue
        next_rects: list[dict[str, float]] = []
        for rect in rects:
            next_rects.extend(_subtract_obstacle(rect, obstacle))
        rects = next_rects or rects
    return rects


def _fit_rect_to_wall_free_space(
    it: dict[str, Any],
    walls: list[dict[str, Any]],
    room_rect: list[float],
    clearance: float,
) -> tuple[dict[str, Any], list[str]]:
    if not all(k in it for k in ("x", "y", "w", "h")):
        return it, []
    x, y = float(it["x"]), float(it["y"])
    w, h = float(it["w"]), float(it["h"])
    current_score, _ = _wall_collision_score(_box_at(it, x, y), walls)
    if current_score <= 0:
        return it, []

    best: tuple[float, float, float, float, float, float, dict[str, float]] | None = None
    for rect in _room_free_rects(room_rect, walls, clearance):
        fw = rect["x1"] - rect["x0"]
        fh = rect["y1"] - rect["y0"]
        if fw < 1.0 or fh < 1.0:
            continue
        nw = min(w, fw)
        nh = min(h, fh)
        nx = _clamp_axis(x, rect["x0"], rect["x1"] - nw)
        ny = _clamp_axis(y, rect["y0"], rect["y1"] - nh)
        new_score, _ = _wall_collision_score(_box_for(nx, ny, nw, nh), walls)
        shrink_loss = max(0.0, w * h - nw * nh)
        dist = abs(nx - x) + abs(ny - y)
        ranked = (new_score, shrink_loss, dist, -nw * nh, nx, ny, rect)
        if best is None or ranked < best:
            best = ranked

    if best is None:
        return it, []
    new_score, _shrink_loss, _dist, _neg_area, nx, ny, rect = best
    if new_score >= current_score:
        return it, []
    nw = min(w, rect["x1"] - rect["x0"])
    nh = min(h, rect["y1"] - rect["y0"])
    out = {**it, "x": nx, "y": ny, "w": _json_num(nw), "h": _json_num(nh)}
    return out, [
        "axon-free-space-fit "
        f"dx={nx - x:.1f} dy={ny - y:.1f} "
        f"dw={nw - w:.1f} dh={nh - h:.1f}"
    ]


def _adjust_rect_away_from_wall_bboxes(
    it: dict[str, Any],
    walls: list[dict[str, Any]],
    room_rect: list[float],
    clearance: float,
) -> tuple[dict[str, Any], list[str]]:
    """Resolve residual wall-thickness collisions using actual derived wall boxes.

    Room-rect clamping handles the normal case. This second pass covers persisted
    production data where furniture may be slightly larger/shifted or where a
    partial derived wall segment does not align exactly with the room rectangle.
    """
    if not all(k in it for k in ("x", "y", "w", "h")):
        return it, []

    rx, ry, rw, rh = [float(v) for v in room_rect]
    w, h = float(it["w"]), float(it["h"])
    min_x, max_x = _axis_bounds(rx, rw, w, clearance)
    min_y, max_y = _axis_bounds(ry, rh, h, clearance)
    move_clearance = max(float(clearance), WALL_COLLISION_TOLERANCE + 1.0)

    out = dict(it)
    notes: list[str] = []
    for _ in range(10):
        box = _as_box(out)
        if box is None:
            return out, notes
        score, collisions = _wall_collision_score(box, walls)
        if score <= 0:
            return out, notes

        x, y = float(out["x"]), float(out["y"])
        candidates: list[tuple[float, float]] = []
        for wall, _ox, _oy in collisions:
            candidates.extend(
                [
                    (wall["x0"] - move_clearance - w, y),
                    (wall["x1"] + move_clearance, y),
                    (x, wall["y0"] - move_clearance - h),
                    (x, wall["y1"] + move_clearance),
                ]
            )

        best: tuple[float, float, float, float] | None = None
        for cand_x, cand_y in candidates:
            nx = _clamp_axis(cand_x, min_x, max_x)
            ny = _clamp_axis(cand_y, min_y, max_y)
            new_score, _new_collisions = _wall_collision_score(_box_at(out, nx, ny), walls)
            dist = abs(nx - x) + abs(ny - y)
            if new_score >= score or dist == 0:
                continue
            ranked = (new_score, dist, nx, ny)
            if best is None or ranked < best:
                best = ranked

        if best is None:
            out, fit_notes = _fit_rect_to_wall_free_space(
                out,
                walls,
                room_rect,
                clearance,
            )
            notes.extend(fit_notes)
            break

        _new_score, _dist, nx, ny = best
        notes.append(
            f"axon-wall-avoid dx={nx - x:.1f} dy={ny - y:.1f}"
        )
        out["x"], out["y"] = nx, ny

    return out, notes


def _adjust_height_to_wall(
    it: dict[str, Any],
    max_height: float,
) -> tuple[dict[str, Any], list[str], float | None]:
    """Clamp furniture render height below the wall top before axon projection."""
    height = _furniture_render_height(it)
    if height is None:
        return it, [], height
    if "z" not in it:
        return {**it, "z": _json_num(min(height, max_height))}, [], height
    if height <= max_height:
        return it, [], height
    out = {**it, "z": _json_num(max_height)}
    return out, [
        f"axon-height-clamp dz={max_height - height:.1f} max={max_height:.1f}"
    ], height


def build_scene(
    G: dict[str, Any],
    geo: dict[str, Any],
    furniture: list[dict[str, Any]],
    *,
    project_id: str | None = None,
    baseline_version_id: str | None = None,
    scheme_id: str | None = None,
    wall_clearance: float = WALL_CLEARANCE,
) -> dict[str, Any]:
    """Build canonical render scene from structured geometry and furniture."""
    # 单位契约显式化 (审计 P1-6): axon 的 ZK/墙厚常量按 1px=10mm 标定, 非 10 的项目
    # 平面正确但轴测整体错比例 —— 隐式假设变显式失败, 好过静默出错图。
    mpp = (G.get("meta") or {}).get("mm_per_px", 10)
    try:
        mpp_val = float(mpp if mpp is not None else 10)
    except (TypeError, ValueError):
        mpp_val = 10.0
    if mpp_val != 10.0:
        raise ValueError(f"暂仅支持 mm_per_px=10 (当前 {mpp!r}); axon 常量按 10mm/px 标定")
    walls = [tuple(w[:7]) for w in geo.get("walls", [])]
    rooms_by_id = _room_map(G)
    wall_height = _wall_height(G)
    max_furniture_height = _max_furniture_height(wall_height)
    wall_bboxes = [_wall_bbox(w) for w in walls]
    resolved: list[dict[str, Any]] = []
    axon_items: list[dict[str, Any]] = []
    adjustments: list[dict[str, Any]] = []
    dangling: list[dict[str, Any]] = []

    for idx, raw in enumerate(furniture):
        rid = raw.get("room_id")
        if rid is not None and str(rid) not in rooms_by_id:
            dangling.append(
                {
                    "index": idx,
                    "room_id": rid,
                    "type": raw.get("t"),
                    "message": f"家具 {raw.get('t', '?')} 引用了不存在的房间 {rid}",
                }
            )
            continue
        item = resolve_furniture([raw], G)[0] if rid is not None else deepcopy(raw)
        item["_index"] = idx
        if rid is not None:
            item["_room_id"] = str(rid)
        resolved.append(item)

        ax_item = deepcopy(item)
        notes: list[str] = []
        adjustment_from: dict[str, Any] = {}
        adjustment_to: dict[str, Any] = {}
        if rid is not None and all(k in ax_item for k in ("x", "y", "w", "h")):
            before_w, before_h = ax_item.get("w"), ax_item.get("h")
            ax_item, size_notes = _adjust_rect_size_to_inner_bounds(
                ax_item,
                rooms_by_id[str(rid)]["rect"],
                wall_clearance,
            )
            if size_notes:
                notes.extend(size_notes)
                adjustment_from.update({"w": before_w, "h": before_h})
                adjustment_to.update({"w": ax_item.get("w"), "h": ax_item.get("h")})
            before_x, before_y = ax_item.get("x"), ax_item.get("y")
            ax_item, xy_notes = _adjust_rect_to_inner_clearance(
                ax_item,
                rooms_by_id[str(rid)]["rect"],
                wall_clearance,
            )
            if xy_notes:
                notes.extend(xy_notes)
                adjustment_from.update({"x": before_x, "y": before_y})
                adjustment_to.update({"x": ax_item.get("x"), "y": ax_item.get("y")})
            before_x, before_y = ax_item.get("x"), ax_item.get("y")
            ax_item, wall_notes = _adjust_rect_away_from_wall_bboxes(
                ax_item,
                wall_bboxes,
                rooms_by_id[str(rid)]["rect"],
                wall_clearance,
            )
            if wall_notes:
                notes.extend(wall_notes)
                adjustment_from.setdefault("x", before_x)
                adjustment_from.setdefault("y", before_y)
                adjustment_to.update(
                    {
                        "x": ax_item.get("x"),
                        "y": ax_item.get("y"),
                        "w": ax_item.get("w"),
                        "h": ax_item.get("h"),
                    }
                )
        ax_item, height_notes, height_before = _adjust_height_to_wall(
            ax_item,
            max_furniture_height,
        )
        if height_notes:
            notes.extend(height_notes)
            adjustment_from["z"] = _json_num(height_before or 0.0)
            adjustment_to["z"] = ax_item.get("z")
        if notes:
            adjustments.append(
                {
                    "index": idx,
                    "room_id": rid,
                    "type": raw.get("t"),
                    "from": adjustment_from,
                    "to": adjustment_to,
                    "notes": notes,
                }
            )
        # 审计 P1-8: 回填「调整后」room-relative 坐标 —— 提示词方位短语必须与底图一致
        # (归一化可位移家具, 用原始 dx/dy 会说 against north wall 而底图画在房中央)。
        if rid is not None:
            rect = rooms_by_id[str(rid)]["rect"]
            if all(k in ax_item for k in ("x", "y")):
                ax_item["_dx"] = ax_item["x"] - rect[0]
                ax_item["_dy"] = ax_item["y"] - rect[1]
            elif all(k in ax_item for k in ("cx", "cy")):
                ax_item["_dcx"] = ax_item["cx"] - rect[0]
                ax_item["_dcy"] = ax_item["cy"] - rect[1]
        axon_items.append(ax_item)

    scene = {
        "version": 1,
        "project_id": project_id,
        "baseline_version_id": baseline_version_id,
        "scheme_id": scheme_id,
        "units": {
            "mm_per_px": G.get("meta", {}).get("mm_per_px", 10),
            "wall_clearance_px": wall_clearance,
            "wall_height_mm": _json_num(wall_height),
            "furniture_top_clearance_mm": _json_num(FURNITURE_TOP_CLEARANCE),
            "max_furniture_height_mm": _json_num(max_furniture_height),
        },
        "rooms": deepcopy(G.get("rooms", [])),
        "walls": [list(w) for w in walls],
        "wall_bboxes": wall_bboxes,
        "doors": deepcopy(geo.get("doors", [])),
        "windows": deepcopy(geo.get("windows", [])),
        "passages": deepcopy(geo.get("passages", [])),
        "dims": deepcopy(geo.get("dims", {})),
        "annotations": deepcopy(G.get("annotations", [])),
        "furniture": resolved,
        "axon_furniture": axon_items,
        "adjustments": adjustments,
        "dangling_furniture": dangling,
    }
    scene["validation"] = validate_scene(scene)
    return scene


def _issue(level: str, code: str, message: str, **meta: Any) -> dict[str, Any]:
    return {"level": level, "code": code, "message": message, **meta}


def _validate_items(
    items: list[dict[str, Any]],
    scene: dict[str, Any],
    *,
    code_prefix: str,
    label: str,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    rooms = _room_map({"rooms": scene.get("rooms", [])})
    walls = scene.get("wall_bboxes", [])
    max_height = _num(scene.get("units", {}).get("max_furniture_height_mm"))
    for it in items:
        box = _as_box(it)
        if max_height is not None:
            height = _furniture_render_height(it)
            if height is not None and height > max_height:
                level = "ERROR" if code_prefix == "AXON" else "WARN"
                issues.append(
                    _issue(
                        level,
                        f"{code_prefix}_HEIGHT_EXCEEDS_WALL",
                        f"{label}家具 {it.get('t', '?')} 高度 {height:.0f} 超过墙体安全高度 {max_height:.0f}",
                        index=it.get("_index"),
                        room_id=it.get("_room_id"),
                        height=_json_num(height),
                        max_height=_json_num(max_height),
                    )
                )
        if box is None:
            continue
        cx, cy = _center(box)
        rid = it.get("_room_id")
        room = rooms.get(str(rid)) if rid is not None else None
        if rid is not None and room is not None:
            if not _point_in_rect(cx, cy, room["rect"]):
                level = "ERROR" if code_prefix == "AXON" else "WARN"
                issues.append(
                    _issue(
                        level,
                        f"{code_prefix}_CENTER_OUTSIDE_ROOM",
                        f"{label}家具 {it.get('t', '?')} 中心不在房间 {rid} 内",
                        index=it.get("_index"),
                        room_id=rid,
                    )
                )
            rx, ry, rw, rh = [float(v) for v in room["rect"]]
            if box["x0"] < rx or box["y0"] < ry or box["x1"] > rx + rw or box["y1"] > ry + rh:
                level = "ERROR" if code_prefix == "AXON" else "WARN"
                issues.append(
                    _issue(
                        level,
                        f"{code_prefix}_OUTSIDE_ROOM_BBOX",
                        f"{label}家具 {it.get('t', '?')} 超出房间 {rid} 边界",
                        index=it.get("_index"),
                        room_id=rid,
                    )
                )
        # 圆形件 (cx/cy/r) 与无 room_id 的绝对件不经过 build_scene 的归一化 (无法自愈),
        # 其墙碰撞降为 WARN 而非 ERROR —— 避免植物/圆桌贴墙即永久硬阻断 AI 出图。
        normalizable = it.get("_room_id") is not None and all(
            k in it for k in ("x", "y", "w", "h")
        )
        for wall in walls:
            ox, oy = _rect_intersection(box, wall)
            if ox > WALL_COLLISION_TOLERANCE and oy > WALL_COLLISION_TOLERANCE:
                issues.append(
                    _issue(
                        "ERROR" if normalizable else "WARN",
                        f"{code_prefix}_WALL_THICKNESS_COLLISION",
                        f"{label}家具 {it.get('t', '?')} 与墙体厚度相交",
                        index=it.get("_index"),
                        room_id=rid,
                        wall=wall.get("wall"),
                        overlap={"x": round(ox, 3), "y": round(oy, 3)},
                    )
                )
                break
    return issues


def validate_scene(scene: dict[str, Any]) -> dict[str, Any]:
    """Validate canonical scene.

    Raw 2D furniture collisions are WARN because they explain why axon may need
    inward clearance. Axon-safe furniture collisions are ERROR and block AI.
    """
    issues: list[dict[str, Any]] = []
    # 目录外类型 WARN (升级计划 P0): 轴测已有通用盒兜底不再隐身, 但仍应显式提示
    # (可能是拼写错误或目录待补), 不阻断出图。
    for it in scene.get("furniture", []):
        t = it.get("t")
        # partition/entry_door 是结构件 (不入目录); rug 已升格入目录 (appearance 非空自然不触发)。
        if isinstance(t, str) and t and _catalog.appearance(t) is None and t not in (
            "partition",
            "entry_door",
        ):
            issues.append(
                _issue(
                    "WARN",
                    "CATALOG_UNKNOWN_TYPE",
                    f"家具类型 {t!r} 不在目录中 (轴测以通用盒渲染)",
                    index=it.get("_index"),
                    room_id=it.get("_room_id"),
                )
            )
    for dangling in scene.get("dangling_furniture", []):
        issues.append(
            _issue(
                "ERROR",
                "DANGLING_FURNITURE_ROOM",
                dangling["message"],
                index=dangling.get("index"),
                room_id=dangling.get("room_id"),
            )
        )
    # 挡门校验 (升级计划 P1): 家具 footprint 与门/通道口净空区相交 -> WARN (不阻断)。
    # 复用 layout 的净空区数学 (room-relative), 与 AI 落位避让同一套语义。
    from . import layout as _layout

    door_like = list(scene.get("doors", [])) + list(scene.get("passages", []))
    rooms_map = _room_map({"rooms": scene.get("rooms", [])})
    if door_like:
        for it in scene.get("furniture", []):
            rid = it.get("_room_id")
            room = rooms_map.get(str(rid)) if rid is not None else None
            box = _as_box(it)
            if room is None or box is None:
                continue
            rx, ry = float(room["rect"][0]), float(room["rect"][1])
            fp = (box["x0"] - rx, box["y0"] - ry, box["x1"] - rx, box["y1"] - ry)
            zones = _layout._door_zones(room["rect"], door_like, 1.0)
            if any(_layout._boxes_intersect(fp, z) for z in zones):
                issues.append(
                    _issue(
                        "WARN",
                        "FURNITURE_BLOCKS_DOOR",
                        f"家具 {it.get('t', '?')} 挡住了房间 {rid} 的门口/通道口净空",
                        index=it.get("_index"),
                        room_id=rid,
                    )
                )
    for raw_issue in _validate_items(
        scene.get("furniture", []), scene, code_prefix="RAW", label="原始"
    ):
        if raw_issue["code"] == "RAW_WALL_THICKNESS_COLLISION":
            raw_issue["level"] = "WARN"
        issues.append(raw_issue)
    issues.extend(
        _validate_items(
            scene.get("axon_furniture", []), scene, code_prefix="AXON", label="轴侧"
        )
    )
    errors = [i for i in issues if i.get("level") == "ERROR"]
    warnings = [i for i in issues if i.get("level") == "WARN"]
    return {
        "ok": not errors,
        "issues": issues,
        "errors": errors,
        "warnings": warnings,
        "adjustments": scene.get("adjustments", []),
    }


def render_manifest(scene: dict[str, Any], *, mode: str, prompt: str | None = None) -> dict[str, Any]:
    """Small serializable manifest for generated AI/render artifacts."""
    validation = scene.get("validation", {})
    scene_for_hash = {k: v for k, v in scene.items() if k != "validation"}
    scene_hash = hashlib.sha256(
        json.dumps(scene_for_hash, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    furniture_hash = hashlib.sha256(
        json.dumps(scene.get("furniture", []), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    axon_furniture_hash = hashlib.sha256(
        json.dumps(scene.get("axon_furniture", []), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    prompt_hash = (
        hashlib.sha256(prompt.encode("utf-8")).hexdigest() if prompt is not None else None
    )
    return {
        "scene_version": scene.get("version"),
        "project_id": scene.get("project_id"),
        "baseline_version_id": scene.get("baseline_version_id"),
        "scheme_id": scene.get("scheme_id"),
        "mode": mode,
        "scene_hash": scene_hash,
        "furniture_hash": furniture_hash,
        "axon_furniture_hash": axon_furniture_hash,
        "prompt_hash": prompt_hash,
        "validation": {
            "ok": bool(validation.get("ok")),
            "errors": len(validation.get("errors", [])),
            "warnings": len(validation.get("warnings", [])),
            "adjustments": len(validation.get("adjustments", [])),
        },
        "prompt_chars": len(prompt or ""),
    }
