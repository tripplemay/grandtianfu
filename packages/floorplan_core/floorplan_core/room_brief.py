# -*- coding: utf-8 -*-
"""room-brief: 喂给 AI 摆家具 LLM 的逐房简报 (Phase 1.5a)。

每房输出: id / 中文名 / 类型 / 净尺寸(mm) / 门(墙向+沿墙中心+洞宽, 供避让) / 窗 / 可选家具类型。
门窗位置取 derive() 解析后的坐标 (审查🟠: 不喂 geometry 内部 openings 的 axis/at/span 原格式),
并几何匹配到房间四壁 (N/S/E/W) + 沿墙相对中心 —— 不依赖 openings.between 命名。
公共区 (type=public) 跳过 (无软装)。
"""
from __future__ import annotations

from . import catalog
from . import geometry as _geometry


def _edge_openings(rect, openings, eps):
    """匹配落在 rect 四壁上的开洞 -> [(wall, rel_center, opening)]。

    door/window 同结构: axis=v 竖墙在 x=at, span 沿 y; axis=h 横墙在 y=at, span 沿 x。
    wall: N(上/y小) S(下) W(左/x小) E(右); rel_center = 沿该墙方向相对房间原点的中心。
    """
    x, y, w, h = rect
    out = []
    for op in openings:
        axis = op.get("axis")
        at = op.get("at")
        span = op.get("span") or [0, 0]
        mid = (span[0] + span[1]) / 2.0
        if axis == "v" and span[1] > y and span[0] < y + h:
            if abs(at - x) <= eps:
                out.append(("W", mid - y, op))
            elif abs(at - (x + w)) <= eps:
                out.append(("E", mid - y, op))
        elif axis == "h" and span[1] > x and span[0] < x + w:
            if abs(at - y) <= eps:
                out.append(("N", mid - x, op))
            elif abs(at - (y + h)) <= eps:
                out.append(("S", mid - x, op))
    return out


def _group_brief(grp: dict, G: dict, doors, windows, mm, eps) -> dict:
    """merge 组 -> 一条逻辑房简报 (P3 简报聚合): 代表 id + 组标签 + 并集尺寸/门窗。

    门窗取所有成员四壁并集, rel_center 重基到组并集原点, 内部共享边开洞 (同一 op 匹配 >=2
    成员) 抑制; furniture_options 取成员类型并集 (保序去重)。"""
    member_rects = grp["member_rects"]  # [(id, x0,y0,x1,y1)]
    ux, uy, ux1, uy1 = grp["bbox"]
    rooms_by_id = {r["id"]: r for r in G["rooms"]}
    rep_room = rooms_by_id[grp["rep"]]
    rt = rep_room.get("type", "living")
    name = (rep_room.get("label") or {}).get("zh")
    if not name:
        for mid in grp["members"]:
            lz = (rooms_by_id[mid].get("label") or {}).get("zh")
            if lz:
                name = lz
                break
    name = name or grp["rep"]

    def _collect(openings, is_window):
        per = []          # (wall, rel_union, op)
        seen_count: dict = {}
        for (_mid, mx0, my0, mx1, my1) in member_rects:
            rect = (mx0, my0, mx1 - mx0, my1 - my0)
            for wall, rel, op in _edge_openings(rect, openings, eps):
                rel_u = (rel + my0 - uy) if wall in ("W", "E") else (rel + mx0 - ux)
                per.append((wall, rel_u, op))
                seen_count[id(op)] = seen_count.get(id(op), 0) + 1
        items = []
        for wall, rel_u, op in per:
            if seen_count[id(op)] >= 2:
                continue  # 内部共享边开洞 -> 逻辑房内部, 不喂 LLM
            if is_window:
                items.append({"wall": wall, "center_mm": round(rel_u * mm),
                              "type": op.get("wtype", "full")})
            else:
                span = op.get("span") or [0, 0]
                width_px = op.get("width") or (float(span[1]) - float(span[0]))
                items.append({"wall": wall, "center_mm": round(rel_u * mm),
                              "width_mm": round(width_px * mm)})
        return items

    ft: list = []
    seen: set = set()
    for mid in grp["members"]:
        for t in catalog.types_for_room(rooms_by_id[mid].get("type", "living")):
            if t not in seen:
                seen.add(t)
                ft.append(t)
    return {
        "room_id": grp["rep"],
        "name": name,
        "type": rt,
        "width_mm": round((ux1 - ux) * mm),
        "depth_mm": round((uy1 - uy) * mm),
        "doors": _collect(doors, False),
        "windows": _collect(windows, True),
        "furniture_options": ft,
    }


def build_briefs(G: dict, geo: dict | None = None) -> list[dict]:
    """逐房简报 (跳过 public)。geo 省略时内部 derive。

    P3 异形: 属 merge 组的房聚成一条逻辑房简报 (代表 id); 无 merge 房走单房路径, 与改造前
    逐字节一致。"""
    if geo is None:
        geo = _geometry.derive(G)
    meta = G.get("meta", {})
    mm = meta.get("mm_per_px", 10)
    eps = meta.get("eps", 1)
    # 门 + 通道口一并给 LLM (通道口是无扇洞口, 同样需要避让); 宽度缺失用 span 长兜底
    # (推拉门 build_door 不产 width, 此前给 LLM「0mm 宽的门」)。
    doors = list(geo.get("doors", [])) + list(geo.get("passages", []))
    windows = geo.get("windows", [])

    mg = _geometry.merge_groups(G)
    grp_of = {rid: gid for gid, gr in mg.items() for rid in gr["members"]}
    emitted: set = set()

    briefs = []
    for r in G.get("rooms", []):
        rt = r.get("type", "living")
        if rt == "public":
            continue
        gid = grp_of.get(r["id"])
        if gid is not None:                      # merge 组: 一条逻辑房简报
            if gid in emitted:
                continue
            emitted.add(gid)
            briefs.append(_group_brief(mg[gid], G, doors, windows, mm, eps))
            continue
        # —— 单房 (无 merge): 与改造前逐字节一致 —— #
        rect = r["rect"]
        x, y, w, h = rect
        name = (r.get("label") or {}).get("zh") or r["id"]
        doors_b = []
        for wall, rel, op in _edge_openings(rect, doors, eps):
            span = op.get("span") or [0, 0]
            width_px = op.get("width") or (float(span[1]) - float(span[0]))
            doors_b.append(
                {"wall": wall, "center_mm": round(rel * mm), "width_mm": round(width_px * mm)}
            )
        windows_b = [
            {"wall": wall, "center_mm": round(rel * mm), "type": op.get("wtype", "full")}
            for wall, rel, op in _edge_openings(rect, windows, eps)
        ]
        briefs.append(
            {
                "room_id": r["id"],
                "name": name,
                "type": rt,
                "width_mm": round(w * mm),
                "depth_mm": round(h * mm),
                "doors": doors_b,
                "windows": windows_b,
                "furniture_options": catalog.types_for_room(rt),
            }
        )
    return briefs
