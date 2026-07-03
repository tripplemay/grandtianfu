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


def build_briefs(G: dict, geo: dict | None = None) -> list[dict]:
    """逐房简报 (跳过 public)。geo 省略时内部 derive。"""
    if geo is None:
        geo = _geometry.derive(G)
    meta = G.get("meta", {})
    mm = meta.get("mm_per_px", 10)
    eps = meta.get("eps", 1)
    # 门 + 通道口一并给 LLM (通道口是无扇洞口, 同样需要避让); 宽度缺失用 span 长兜底
    # (推拉门 build_door 不产 width, 此前给 LLM「0mm 宽的门」)。
    doors = list(geo.get("doors", [])) + list(geo.get("passages", []))
    windows = geo.get("windows", [])

    briefs = []
    for r in G.get("rooms", []):
        rt = r.get("type", "living")
        if rt == "public":
            continue
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
