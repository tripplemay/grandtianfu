"""calib-route-a1 F001 — 从 geometry.json 提取**无歧义**的候选世界点。

世界系与产品逐字一致（见 main.py::_calibration_wireframe）：
    world_mm = rect_px * meta.mm_per_px   （**不减 meta.origin**）
    X = 东(+)，Y = 南(+)，Z = 上(+)；地面 z=0，天花 z=_REAL_CEILING_MM=2700。

只收录**人在照片里能唯一指认**的点：房间矩形的 8 个角、门窗洞口的框角。
刻意**不**收录地板拼缝、墙面分格等 —— 那些在照片上找得到，但在 geometry 里
没有对应坐标，凑数会把不可信的当真值（spec §D1 明令禁止）。
"""
from __future__ import annotations

from typing import NamedTuple

CEILING_MM = 2700.0        # 实拍世界层高，见 perspective._REAL_CEILING_MM
DOOR_HEAD_MM = 2050.0      # 门顶，见 studioApi.ts 的 door_head
WINDOW_FULL_HEAD_MM = CEILING_MM   # 落地窗(wtype=full) 顶 = 层高


class WorldPoint(NamedTuple):
    id: str
    xyz: tuple[float, float, float]
    label: str          # 给人看的中文描述，标注工具直接显示这句
    kind: str           # room_corner | door_jamb | window_jamb


def _mm_per_px(G: dict) -> float:
    return float((G.get("meta") or {}).get("mm_per_px", 10))


def _merge_members(G: dict, room_id: str) -> list[dict]:
    """房间所在 merge 组的全部成员（无 merge 则只有自己）。

    与产品 _calibration_wireframe 同口径：线框覆盖整个 merge 组，故真值点也应
    覆盖整组 —— 否则用户在照片里看到的墙角有一半找不到坐标（b3 F009 的教训）。
    """
    rooms = {str(r["id"]): r for r in G.get("rooms", []) if "id" in r}
    me = rooms.get(str(room_id))
    if me is None:
        return []
    grp = me.get("merge")
    if not grp:
        return [me]
    return [r for r in G.get("rooms", []) if r.get("merge") == grp]


_CORNER_ZH = {"NW": "西北", "NE": "东北", "SE": "东南", "SW": "西南"}


def _covered_quadrants(px: float, py: float, rects: list, eps: float = 0.5) -> int:
    """角点四周被 merge 组覆盖的象限数（0-4）。"""
    n = 0
    for dx, dy in ((-eps, -eps), (eps, -eps), (eps, eps), (-eps, eps)):
        qx, qy = px + dx, py + dy
        if any(x <= qx <= x + w and y <= qy <= y + h for x, y, w, h in rects):
            n += 1
    return n


def _is_identifiable_corner(px: float, py: float, rects: list) -> bool:
    """该角点在照片里是否是**看得见的墙角**。

    覆盖象限数：
      1 = 凸角（墙角凸向房内）      -> 可指认 ✓
      3 = 凹角（两墙相交的内角）    -> 可指认 ✓
      2 = 落在一段直墙上，没有视觉角 -> 不可指认 ✗
      4 = 开放地面正中，纯属虚构     -> 不可指认 ✗

    merge 组把多个 rect 拼成一个开放空间后，**组内部的 rect 分界角全是 2 或 4**。
    把它们递给用户「请点这个角」= 让人去指认一个照片上不存在的东西 —— 那正是
    calib-cure-b3 F009「专家模式仍给虚拟角」的原样重演。
    """
    return _covered_quadrants(px, py, rects) in (1, 3)


def room_corners(G: dict, room_id: str) -> list[WorldPoint]:
    s = _mm_per_px(G)
    members = sorted(_merge_members(G, room_id), key=lambda r: str(r["id"]))
    rects = [tuple(r["rect"]) for r in members]
    multi = len(members) > 1
    out: list[WorldPoint] = []
    for room in members:
        rid = str(room["id"])
        x, y, w, h = room["rect"]
        corners = {
            "NW": (x, y), "NE": (x + w, y), "SE": (x + w, y + h), "SW": (x, y + h),
        }
        zh = ((room.get("label") or {}).get("zh")) or rid
        for name, (cxp, cyp) in corners.items():
            if not _is_identifiable_corner(cxp, cyp, rects):
                continue
            # merge 组内多个成员常共用同一个 label.zh（D 户型三个成员都叫「客厅」），
            # 不带 rid 会产出多组重名点 —— calib-cure-b3 F008「标签重名 8 组」的病根。
            who = f"{zh}[{rid}]" if multi else zh
            for z, ztag, zzh in ((0.0, "floor", "地面"), (CEILING_MM, "ceil", "天花")):
                out.append(WorldPoint(
                    id=f"{rid}.{name}.{ztag}",
                    xyz=(cxp * s, cyp * s, z),
                    label=f"{who} {_CORNER_ZH[name]}角 · {zzh}",
                    kind="room_corner",
                ))
    return out


def _on_room_boundary(wall: dict, rect: list) -> bool:
    x, y, w, h = rect
    at, sp = wall["at"], wall["span"]
    if wall["axis"] == "h":
        return at in (y, y + h) and not (sp[1] <= x or sp[0] >= x + w)
    return at in (x, x + w) and not (sp[1] <= y or sp[0] >= y + h)


def opening_points(G: dict, room_id: str) -> list[WorldPoint]:
    """落在房间矩形边界上的门/窗，取两侧框角（地面 + 顶）。"""
    s = _mm_per_px(G)
    out: list[WorldPoint] = []
    for room in sorted(_merge_members(G, room_id), key=lambda r: str(r["id"])):
        rect = room["rect"]
        for op in G.get("openings", []):
            wall = op.get("wall") or {}
            if not wall or not _on_room_boundary(wall, rect):
                continue
            oid = str(op.get("id", "?"))
            is_win = op.get("kind") == "window"
            top = WINDOW_FULL_HEAD_MM if (is_win and op.get("wtype") == "full") else DOOR_HEAD_MM
            noun = "窗" if is_win else "门"
            at, sp = wall["at"] * s, [v * s for v in wall["span"]]
            for side, sv in (("lo", sp[0]), ("hi", sp[1])):
                wx, wy = (sv, at) if wall["axis"] == "h" else (at, sv)
                for z, ztag, zzh in ((0.0, "base", "底"), (top, "head", f"顶({top:.0f}mm)")):
                    out.append(WorldPoint(
                        id=f"{oid}.{side}.{ztag}",
                        xyz=(wx, wy, z),
                        label=f"{noun}{oid} {'左' if side == 'lo' else '右'}框 · {zzh}",
                        kind="window_jamb" if is_win else "door_jamb",
                    ))
    return out


def candidates(G: dict, room_id: str) -> list[WorldPoint]:
    """房间的全部候选世界点，按坐标去重（洞口框角常与房间角重合）。"""
    seen: dict[tuple, WorldPoint] = {}
    for p in room_corners(G, room_id) + opening_points(G, room_id):
        key = tuple(round(v, 3) for v in p.xyz)
        if key not in seen:                 # 先到先得：房间角优先于洞口框角
            seen[key] = p
    return list(seen.values())


def non_coplanar(points: list[WorldPoint]) -> bool:
    """候选点是否张成 3 维（共面 = DLT 退化，b2/b3 的老病）。"""
    import numpy as np
    if len(points) < 4:
        return False
    W = np.array([p.xyz for p in points], float)
    return int(np.linalg.matrix_rank(W - W.mean(0), tol=1e-6)) >= 3
