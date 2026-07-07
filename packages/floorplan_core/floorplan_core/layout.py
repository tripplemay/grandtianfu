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
# 高件 (z>=阈值 mm) 不贴落地窗墙: 窗前净深 (px)。
TALL_Z_MM = 1200.0
WINDOW_CLEARANCE = 8.0
# 有方向语义的类型: 落位时按贴靠最近墙写 orient (床头/沙发背/柜背靠墙)。
# 从家具目录 (catalog.directional) 单一真源推导 —— 新增方向件只需在目录标 directional=True。
DIRECTIONAL_TYPES = set(catalog.DIRECTIONAL_TYPES)


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


def _window_zones(rect, windows, eps, depth: float = WINDOW_CLEARANCE):
    """落地窗前净空区 (仅 wtype=full): 高件不得贴窗摆放 (挡光/视觉阻断)。"""
    x, y, w, h = [float(v) for v in rect]
    zones: list[tuple[float, float, float, float]] = []
    for op in windows or []:
        if op.get("wtype") != "full":
            continue
        axis = op.get("axis")
        at = op.get("at")
        span = op.get("span") or [0, 0]
        if axis is None or at is None:
            continue
        s0, s1 = float(span[0]), float(span[1])
        if axis == "v" and s1 > y and s0 < y + h:
            if abs(at - x) <= eps:
                zones.append((0.0, s0 - y, depth, s1 - y))
            elif abs(at - (x + w)) <= eps:
                zones.append((w - depth, s0 - y, w, s1 - y))
        elif axis == "h" and s1 > x and s0 < x + w:
            if abs(at - y) <= eps:
                zones.append((s0 - x, 0.0, s1 - x, depth))
            elif abs(at - (y + h)) <= eps:
                zones.append((s0 - x, h - depth, s1 - x, h))
    return zones


def _nearest_wall(fp, room_w: float, room_h: float) -> str:
    """footprint 最近的墙 (N/W/S/E), 供有方向语义的家具写 orient。"""
    d = {"N": fp[1], "W": fp[0], "S": room_h - fp[3], "E": room_w - fp[2]}
    return min(d, key=lambda k: (d[k], k))


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


# --------------------------------------------------------------------------- #
#  合并组 (异形二期 b): L 形/并集空间落位。room_brief 已把组折叠成一条 rep 简报
#  (尺寸=并集 bbox), 但 layout 若只在 rep 单腿落位, 另一条腿永远空置且假性放不下。
#  这里把整个并集当一个房间: 候选跨各成员腿采样, footprint 须被并集覆盖 (排除 L 凹口),
#  门/窗净空取外墙并集 (内部共享边抑制), 每件按落入的成员腿归属 + 腿内相对坐标 emit ——
#  与 scene.py 用 rect_of[room_id] 原点还原、prompt_gen base_off 成员腿重投影的契约一致。
# --------------------------------------------------------------------------- #
def _group_slots(member_rects) -> list[tuple[tuple, float, float]]:
    """并集候选 (leg, 绝对cx, 绝对cy): 各成员腿墙向内分数网格, round-robin 交错跨腿。

    交错而非顺序拼接 —— 否则贪心落位会填满第一条腿, 另一条腿永远空置 (异形二期 b 的病灶)。
    每候选携带其所属成员腿, 供 per-leg 落位 (footprint 完全落该腿, 排凹口+不骑缝)。
    """
    per_leg: list[list[tuple[tuple, float, float]]] = []
    for mr in member_rects:
        x0, y0, x1, y1 = mr[1], mr[2], mr[3], mr[4]
        seen_leg: set[tuple[float, float]] = set()
        legslots: list[tuple[tuple, float, float]] = []
        for sx, sy in _slots(x1 - x0, y1 - y0, 32):
            c = (round(x0 + sx, 3), round(y0 + sy, 3))
            if c not in seen_leg:
                seen_leg.add(c)
                legslots.append((mr, c[0], c[1]))
        per_leg.append(legslots)
    out: list[tuple[tuple, float, float]] = []
    seen: set[tuple[float, float]] = set()
    for i in range(max((len(p) for p in per_leg), default=0)):
        for legslots in per_leg:
            if i < len(legslots):
                mr, cx, cy = legslots[i]
                if (cx, cy) not in seen:
                    seen.add((cx, cy))
                    out.append((mr, cx, cy))
    return out


def _group_opening_zones(member_rects, openings, eps, kind: str):
    """并集外墙开洞净空区 (绝对坐标)。kind='door' 复用 _door_zones, 'window' 复用
    _window_zones (仅 full 落地窗) —— 内部/共享边开洞由 group_exterior_openings 几何抑制。"""
    zones: list[tuple[float, float, float, float]] = []
    ext = _geometry.group_exterior_openings(member_rects, openings, eps)
    for _wall, (_mid, mx0, my0, mx1, my1), op, _rel in ext:
        rect = (mx0, my0, mx1 - mx0, my1 - my0)
        mzones = (
            _door_zones(rect, [op], eps)
            if kind == "door"
            else _window_zones(rect, [op], eps)
        )
        for zx0, zy0, zx1, zy1 in mzones:
            zones.append((zx0 + mx0, zy0 + my0, zx1 + mx0, zy1 + my0))
    return zones


def _nearest_exterior_wall(member_rects, leg, cx, cy, fp_leg, eps) -> str:
    """方向件贴靠的最近【外墙】(N/W/S/E): 跳过与相邻/重叠腿相接的内部边 (骑缝/共享边)。

    某墙外侧点 (沿件中心、跨该腿墙向外) 落在另一成员内 -> 内部边, 排除。全内部时退回最近墙。
    """
    x0, y0, x1, y1 = leg[1], leg[2], leg[3], leg[4]
    lw, lh = x1 - x0, y1 - y0
    step = max(float(eps), 1.0)
    others = [m for m in member_rects if m[0] != leg[0]]
    cand = {
        "N": (fp_leg[1], (cx, y0 - step)),
        "W": (fp_leg[0], (x0 - step, cy)),
        "S": (lh - fp_leg[3], (cx, y1 + step)),
        "E": (lw - fp_leg[2], (x1 + step, cy)),
    }
    ext = {
        w: d for w, (d, pt) in cand.items()
        if not _geometry.point_in_any(others, pt[0], pt[1])
    }
    pool = ext or {w: d for w, (d, _pt) in cand.items()}
    return min(pool, key=lambda k: (pool[k], k))


def _place_group(grp, room_sel, rooms, doors, windows, eps, out, warnings) -> None:
    """把 rep 选择在整个并集内展开落位: 每件完全落入某一成员腿 (不骑缝/不入凹口),
    归属该腿 + 腿内相对坐标 emit; 门净空/件间避让在绝对系跨腿判定。"""
    member_rects = grp["member_rects"]
    rep_room = rooms.get(grp["rep"]) or {}
    room_name = (rep_room.get("label") or {}).get("zh") or grp["rep"]
    zones = _group_opening_zones(member_rects, doors, eps, "door")
    win_zones = _group_opening_zones(member_rects, windows, eps, "window")
    slots = _group_slots(member_rects)
    used: set[tuple[float, float]] = set()
    placed_boxes: list[tuple[float, float, float, float]] = []
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
        for leg, cx, cy in slots:
            key = (cx, cy)
            lx0, ly0 = leg[1], leg[2]
            lcx, lcy = cx - lx0, cy - ly0
            # footprint 完全落在本腿内 (per-leg _fits): 排 L 凹口, 且不骑缝 ->
            # 下游 scene 组感知夹取 (中心在本腿则本 rect) 不再位移 layout 已算好的落位。
            if key in used or not _fits(app, leg[3] - lx0, leg[4] - ly0, lcx, lcy):
                continue
            fp = _footprint(app, cx, cy)  # 绝对
            if any(_boxes_intersect(fp, z) for z in zones):
                continue
            if float(app.get("z") or 0) >= TALL_Z_MM and any(
                _boxes_intersect(fp, z) for z in win_zones
            ):
                continue
            if any(_boxes_intersect(fp, b, ITEM_GAP) for b in placed_boxes):
                continue
            item = _item_at(t, leg[0], app, lcx, lcy)
            if t in DIRECTIONAL_TYPES:
                fp_leg = _footprint(app, lcx, lcy)
                item["orient"] = _nearest_exterior_wall(member_rects, leg, cx, cy, fp_leg, eps)
            out.append(item)
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
    # 合并组: rep/成员 id -> 组 (异形二期 b); 无 merge 数据空表, 全走单房路径 (逐字节不变)。
    mg = _geometry.merge_groups(G)
    group_of = {rid: gid for gid, gr in mg.items() for rid in gr["members"]}
    # 门几何: 从派生结果取 (与 room_brief 同源); 极简测试 G 可能无法 derive, 安全回退无门。
    try:
        geo_d = _geometry.derive(G)
        # 门 + 通道口都要避让 (通道口是无扇洞口, 堵住即堵动线)。
        doors = (geo_d.get("doors") or []) + (geo_d.get("passages") or [])
        windows = geo_d.get("windows") or []
    except Exception:  # noqa: BLE001 - 布局对派生失败降级为无门避让, 不阻断。
        doors = []
        windows = []
    try:
        eps = float((G.get("meta") or {}).get("eps", 1) or 1)
    except (TypeError, ValueError):
        eps = 1.0
    out: list[dict] = []
    warnings: list[str] = []
    for room_sel in selections or []:
        room_id = room_sel.get("room_id")
        # 合并组: 在整个并集内展开落位 (每件归属所落成员腿)。
        gid = group_of.get(room_id)
        if gid is not None:
            _place_group(mg[gid], room_sel, rooms, doors, windows, eps, out, warnings)
            continue
        room = rooms.get(room_id)
        if not room:
            continue
        rect = room.get("rect") or [0, 0, 0, 0]
        room_w = float(rect[2])
        room_h = float(rect[3])
        room_name = (room.get("label") or {}).get("zh") or room_id
        zones = _door_zones(rect, doors, eps)
        win_zones = _window_zones(rect, windows, eps)
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
                # 高件不贴落地窗墙 (挡光): 仅 z>=TALL_Z_MM 的类型受此约束。
                if float(app.get("z") or 0) >= TALL_Z_MM and any(
                    _boxes_intersect(fp, z) for z in win_zones
                ):
                    continue
                if any(_boxes_intersect(fp, b, ITEM_GAP) for b in placed_boxes):
                    continue
                item = _item_at(t, room_id, app, cx, cy)
                if t in DIRECTIONAL_TYPES:
                    item["orient"] = _nearest_wall(fp, room_w, room_h)
                out.append(item)
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
