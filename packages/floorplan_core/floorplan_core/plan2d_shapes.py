# -*- coding: utf-8 -*-
"""声明式俯视外形 (软装重构 Phase C-3 / 画家具外形 #3-2)。

家具在 2D 平面 / 编辑器画布上, 除底框外再叠一层"内部细节图元"——床头板、沙发扶手/靠背、
便器盆、浴缸内胆、柜门线——让方格变成可辨识的外形, 且随 orient 自动贴到对应墙侧。
本模块是纯函数解释器: (footprint x/y/w/h + orient + spec) -> 一组绘制原语 (rect/line)。
前端 furniture.ts 有一份等价孪生解释器, 消费同一份 catalog.plan2d_spec (单一真源)。

spec 是 part 列表, 每个 part 的 k 决定形状:
  - edge : 贴 orient 边的实条 (床头板/靠背/柜背)。 {depth}
  - arms : orient 轴两侧的实条 (沙发扶手)。         {depth, width}
  - inner: 内嵌 (圆角)矩形 (盆/内胆/床垫)。        {inset:[l,t,r,b], rx?}
  - doors: 沿墙面的等分门线。                        {n}
坐标为家具 footprint 绝对坐标 (未旋转); rot 旋转由调用方在外层包裹。
"""
from __future__ import annotations

_ORIENTS = ("N", "S", "W", "E")


def _edge_rect(x: float, y: float, w: float, h: float, orient: str, depth: float) -> dict:
    depth = max(0.0, min(0.9, depth))
    if orient == "S":
        return {"k": "rect", "x": x, "y": y + h * (1 - depth), "w": w, "h": h * depth}
    if orient == "W":
        return {"k": "rect", "x": x, "y": y, "w": w * depth, "h": h}
    if orient == "E":
        return {"k": "rect", "x": x + w * (1 - depth), "y": y, "w": w * depth, "h": h}
    return {"k": "rect", "x": x, "y": y, "w": w, "h": h * depth}  # N (默认)


def _arm_rects(
    x: float, y: float, w: float, h: float, orient: str, depth: float, width: float
) -> list[dict]:
    depth = max(0.0, min(1.0, depth))
    width = max(0.0, min(0.45, width))
    if orient in ("N", "S"):  # 竖向靠背 -> 扶手在左右, 沿 y 从靠背侧伸出
        y0 = y if orient == "N" else y + h * (1 - depth)
        hh = h * depth
        return [
            {"k": "rect", "x": x, "y": y0, "w": w * width, "h": hh},
            {"k": "rect", "x": x + w * (1 - width), "y": y0, "w": w * width, "h": hh},
        ]
    # 横向靠背 (W/E) -> 扶手在上下, 沿 x 从靠背侧伸出
    x0 = x if orient == "W" else x + w * (1 - depth)
    ww = w * depth
    return [
        {"k": "rect", "x": x0, "y": y, "w": ww, "h": h * width},
        {"k": "rect", "x": x0, "y": y + h * (1 - width), "w": ww, "h": h * width},
    ]


def _inner_rect(x: float, y: float, w: float, h: float, inset, rx: float) -> dict:
    left, top, right, bot = (inset + [0, 0, 0, 0])[:4]
    iw = w * max(0.0, 1 - left - right)
    ih = h * max(0.0, 1 - top - bot)
    return {"k": "rect", "x": x + w * left, "y": y + h * top, "w": iw, "h": ih, "rx": rx, "hollow": True}


def _door_lines(x: float, y: float, w: float, h: float, orient: str, n: int) -> list[dict]:
    n = max(1, int(n))
    lines = []
    if orient in ("N", "S"):  # 墙水平 -> 门沿宽度等分 (竖线)
        for i in range(1, n):
            lx = x + w * i / n
            lines.append({"k": "line", "x1": lx, "y1": y, "x2": lx, "y2": y + h})
    else:  # 墙竖直 -> 门沿高度等分 (横线)
        for i in range(1, n):
            ly = y + h * i / n
            lines.append({"k": "line", "x1": x, "y1": ly, "x2": x + w, "y2": ly})
    return lines


def detail_prims(
    x: float, y: float, w: float, h: float, orient: str | None, spec: list[dict]
) -> list[dict]:
    """spec -> 绘制原语列表。rect 原语默认实填(叠深色), hollow=True 为描边内胆; line 为门线。"""
    o = orient if orient in _ORIENTS else "N"
    prims: list[dict] = []
    for part in spec or []:
        if not isinstance(part, dict):
            continue
        k = part.get("k")
        if k == "edge":
            prims.append(_edge_rect(x, y, w, h, o, float(part.get("depth", 0.15))))
        elif k == "arms":
            prims.extend(
                _arm_rects(x, y, w, h, o, float(part.get("depth", 0.8)), float(part.get("width", 0.12)))
            )
        elif k == "inner":
            prims.append(
                _inner_rect(x, y, w, h, list(part.get("inset", [0.1, 0.1, 0.1, 0.1])), float(part.get("rx", 3)))
            )
        elif k == "doors":
            prims.extend(_door_lines(x, y, w, h, o, part.get("n", 2)))
    return prims
