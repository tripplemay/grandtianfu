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

WALL_CLEARANCE = 13.0
WALL_COLLISION_TOLERANCE = 3.0
DEFAULT_WALL_HEIGHT = 1450.0
FURNITURE_TOP_CLEARANCE = 50.0
DEFAULT_MAX_FURNITURE_HEIGHT = DEFAULT_WALL_HEIGHT - FURNITURE_TOP_CLEARANCE

# Renderers for these furniture types have high built-in defaults even when the
# input JSON omits `z`. They must still obey the scene's wall-height contract.
HEIGHT_CONSTRAINED_DEFAULTS = {
    "wardrobe": DEFAULT_MAX_FURNITURE_HEIGHT,
    "tall_cabinet": DEFAULT_MAX_FURNITURE_HEIGHT,
    "bookshelf": DEFAULT_MAX_FURNITURE_HEIGHT,
    "fridge": DEFAULT_MAX_FURNITURE_HEIGHT,
    "washer_dryer": DEFAULT_MAX_FURNITURE_HEIGHT,
    "shower": DEFAULT_MAX_FURNITURE_HEIGHT,
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
    walls = [tuple(w[:7]) for w in geo.get("walls", [])]
    rooms_by_id = _room_map(G)
    wall_height = _wall_height(G)
    max_furniture_height = _max_furniture_height(wall_height)
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
        "wall_bboxes": [_wall_bbox(w) for w in walls],
        "doors": deepcopy(geo.get("doors", [])),
        "windows": deepcopy(geo.get("windows", [])),
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
        for wall in walls:
            ox, oy = _rect_intersection(box, wall)
            if ox > WALL_COLLISION_TOLERANCE and oy > WALL_COLLISION_TOLERANCE:
                issues.append(
                    _issue(
                        "ERROR",
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
