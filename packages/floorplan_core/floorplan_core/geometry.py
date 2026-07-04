#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""geometry.py — 房间驱动 / 派生墙体 (方案B) 的纯函数核心.

实现 几何编辑器-实现规格.md 的 §②(derive 伪码 + 黄金断言)、§③(门)、§④(尺寸).

公共 API:
    load(path)        -> dict     读取 geometry.json
    derive(G)         -> dict      房间 -> 墙/门/窗/尺寸 (无副作用, 可单测)
    validate(G)       -> list      返回 (level, msg) 列表 (ERROR/WARN)
    candidate_walls(G)-> dict       (axis,at) -> 合并区间 (开洞前; 供 svg2geometry gap 反推)

derive() 返回:
    {
      "walls":     [(ax,ay,bx,by,ext,style,lowz), ...]   7 元组
      "doors":     [ {...}, ... ]
      "windows":   [ {...}, ... ]
      "dims":      {"top":[...], "left":[...], ...}
      "conflicts": [str, ...]   # ERROR
      "warns":     [str, ...]   # WARN
    }

坐标系: 组内坐标, 1px=10mm, rect 边=结构轴线中线 (规格 D7).
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
#  常量 / 默认
# --------------------------------------------------------------------------- #
DEFAULT_THICKNESS_MM = {
    "exterior": 240, "demarcation": 200, "interior": 140,
    "outdoor": 240, "thin": 60, "public": 60,
}
DEFAULT_STYLE = {
    "exterior": "solid", "demarcation": "solid", "interior": "solid",
    "outdoor": "solid", "thin": "thin", "public": "dashed",
}
LOWZ_ROLES = {"thin", "public"}
EXT_ROLES = {"exterior", "outdoor"}


# --------------------------------------------------------------------------- #
#  IO
# --------------------------------------------------------------------------- #
SUPPORTED_SCHEMA_VERSION = 2


def load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    # 版本闸门 (审计 P2-1): schema_version 此前写而不读 —— 新格式落盘后旧代码会
    # 静默错读; 显式快速失败, 提示升级服务而非产出错误结果。缺失按 v1/v2 兼容读。
    sv = (data.get("meta") or {}).get("schema_version")
    if isinstance(sv, (int, float)) and sv > SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"geometry schema_version {sv} 不受支持 (最高 {SUPPORTED_SCHEMA_VERSION}), 请升级服务"
        )
    return data


# --------------------------------------------------------------------------- #
#  区间工具 (1D)
# --------------------------------------------------------------------------- #
def merge_intervals(segs: List[List[float]], eps: float = 1.0) -> List[List[float]]:
    """合并重叠 / 相邻 (gap<=eps) 的 1D 区间."""
    segs = sorted([list(s) for s in segs if s[1] - s[0] > 1e-9])
    if not segs:
        return []
    out = [segs[0][:]]
    for lo, hi in segs[1:]:
        if lo <= out[-1][1] + eps:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out


def subtract_one(seg: List[float], cut: List[float]) -> List[List[float]]:
    """seg 减去 cut, 返回 0/1/2 段."""
    lo, hi = seg
    c0, c1 = cut
    if c1 <= lo or c0 >= hi:          # 不相交
        return [[lo, hi]]
    res = []
    if c0 > lo:
        res.append([lo, c0])
    if c1 < hi:
        res.append([c1, hi])
    return res


def subtract_intervals(segs: List[List[float]], cut: List[float],
                       eps: float = 0.0) -> List[List[float]]:
    out = []
    for s in segs:
        out.extend(subtract_one(s, cut))
    return [s for s in out if s[1] - s[0] > eps]


def diff_intervals(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    """a - b (集合差)."""
    res = [list(s) for s in a]
    for cut in b:
        nxt = []
        for s in res:
            nxt.extend(subtract_one(s, cut))
        res = nxt
    return [s for s in res if s[1] - s[0] > 1e-9]


# --------------------------------------------------------------------------- #
#  分类: space -> category ; classify(A,B)
# --------------------------------------------------------------------------- #
def _cat_of(G: dict, space: Optional[str]) -> str:
    if space is None:
        return "void"
    return G["spaces"][space]["category"]


def classify(a_space, a_cat, b_space, b_cat) -> Optional[str]:
    """A=side- , B=side+. 返回 role 或 None(开放无墙). 规格 §② classify."""
    if a_space is not None and b_space is not None and a_space == b_space:
        return None
    ia, ib = (a_cat == "interior"), (b_cat == "interior")
    oa, ob = (a_cat == "outdoor"), (b_cat == "outdoor")
    sa, sb = (a_cat == "shared"), (b_cat == "shared")
    va, vb = (a_cat == "void"), (b_cat == "void")
    if va and vb:
        return None
    # outdoor 四规则 (D3)
    if oa and ob:
        return None
    if (oa and ib) or (ob and ia):
        return "outdoor"
    if (oa and vb) or (ob and va):
        return "exterior"
    if (oa and sb) or (ob and sa):
        return "exterior"
    # interior 系
    if ia and ib:
        return "interior"
    if (ia and vb) or (ib and va):
        return "exterior"
    if (ia and sb) or (ib and sa):
        return "demarcation"
    # shared 系
    if sa and sb:
        return None
    if (sa and vb) or (sb and va):
        return "public"
    return None


# --------------------------------------------------------------------------- #
#  房间 / occupancy
# --------------------------------------------------------------------------- #
def _rooms_xywh(G: dict):
    """返回 [(id, space, cat, x0,y0,x1,y1), ...]."""
    out = []
    for r in G["rooms"]:
        x, y, w, h = r["rect"]
        out.append((r["id"], r["space"], _cat_of(G, r["space"]),
                    x, y, x + w, y + h))
    return out


def _occ(rooms, px, py):
    """占据查询 -> (space, cat). 多 space 命中 -> 抛 ('CONFLICT', spaces)."""
    hits = [(sp, cat) for (_id, sp, cat, x0, y0, x1, y1) in rooms
            if x0 <= px <= x1 and y0 <= py <= y1]
    if not hits:
        return (None, "void")
    spaces = {h[0] for h in hits}
    if len(spaces) > 1:
        raise ValueError("CONFLICT@(%s,%s):%s" % (px, py, sorted(spaces)))
    return hits[0]


# --------------------------------------------------------------------------- #
#  cell decomposition -> 房间墙 (开洞前)
# --------------------------------------------------------------------------- #
def _room_walls(G: dict, conflicts: List[str]) -> List[dict]:
    rooms = _rooms_xywh(G)
    eps = G.get("meta", {}).get("eps", 1)
    d = 0.25  # 采样偏移 (亚像素)
    raw: List[dict] = []

    xs = sorted({v for (_i, _s, _c, x0, y0, x1, y1) in rooms for v in (x0, x1)})
    ys = sorted({v for (_i, _s, _c, x0, y0, x1, y1) in rooms for v in (y0, y1)})

    # 竖墙 (axis='v'): 常量 x = c, 沿 y 切
    for c in xs:
        for lo, hi in zip(ys, ys[1:]):
            if hi - lo < eps:
                continue
            m = (lo + hi) / 2.0
            try:
                A = _occ(rooms, c - d, m)
                B = _occ(rooms, c + d, m)
            except ValueError as e:
                conflicts.append(str(e))
                continue
            role = classify(A[0], A[1], B[0], B[1])
            if role:
                raw.append({"axis": "v", "at": c, "lo": lo, "hi": hi, "role": role})

    # 横墙 (axis='h'): 常量 y = c, 沿 x 切
    for c in ys:
        for lo, hi in zip(xs, xs[1:]):
            if hi - lo < eps:
                continue
            m = (lo + hi) / 2.0
            try:
                A = _occ(rooms, m, c - d)
                B = _occ(rooms, m, c + d)
            except ValueError as e:
                conflicts.append(str(e))
                continue
            role = classify(A[0], A[1], B[0], B[1])
            if role:
                raw.append({"axis": "h", "at": c, "lo": lo, "hi": hi, "role": role})

    return _merge_collinear(raw, eps)


def _merge_collinear(walls: List[dict], eps: float) -> List[dict]:
    """同 (axis, at, role) 且端点 gap<=eps 合并."""
    groups: Dict[Tuple, List[List[float]]] = {}
    style_of: Dict[Tuple, Optional[str]] = {}
    for w in walls:
        key = (w["axis"], w["at"], w["role"])
        groups.setdefault(key, []).append([w["lo"], w["hi"]])
        style_of[key] = w.get("style")
    out = []
    for (axis, at, role), segs in groups.items():
        for lo, hi in merge_intervals(segs, eps):
            out.append({"axis": axis, "at": at, "lo": lo, "hi": hi,
                        "role": role, "style": style_of[(axis, at, role)]})
    return out


def _add_free_walls(walls: List[dict], G: dict, eps: float) -> List[dict]:
    for fw in G.get("free_walls", []):
        walls.append({"axis": fw["axis"], "at": fw["at"],
                      "lo": fw["span"][0], "hi": fw["span"][1],
                      "role": fw["role"], "style": fw.get("style")})
    return _merge_collinear(walls, eps)


def candidate_walls(G: dict) -> Dict[Tuple[str, float], List[List[float]]]:
    """开洞前的派生墙 (含 free_walls), 按 (axis,at) 归并区间 (忽略 role).

    供 svg2geometry 做 gap 反推 (D10)."""
    conflicts: List[str] = []
    walls = _room_walls(G, conflicts)
    walls = _add_free_walls(walls, G, G.get("meta", {}).get("eps", 1))
    out: Dict[Tuple[str, float], List[List[float]]] = {}
    for w in walls:
        out.setdefault((w["axis"], w["at"]), []).append([w["lo"], w["hi"]])
    return {k: merge_intervals(v, G.get("meta", {}).get("eps", 1))
            for k, v in out.items()}


# --------------------------------------------------------------------------- #
#  开洞: subtract / find host
# --------------------------------------------------------------------------- #
def _subtract_opening(walls: List[dict], axis: str, at: float,
                      span: List[float]) -> Tuple[List[dict], float]:
    """从 axis,at 上的墙减去 span. 返回 (new_walls, removed_len).

    removed_len = span 与 (axis,at) 上派生墙并集 的重叠长度 (= span 被连续墙覆盖的长度,
    因为同 (axis,at) 墙段经 merge_collinear 后两两不相交). 供 D12 落墙判定使用."""
    out: List[dict] = []
    removed = 0.0
    for w in walls:
        if w["axis"] == axis and abs(w["at"] - at) < 1e-6:
            before = w["hi"] - w["lo"]
            pieces = subtract_one([w["lo"], w["hi"]], span)
            after = sum(p[1] - p[0] for p in pieces)
            removed += before - after
            for lo, hi in pieces:
                nw = dict(w)
                nw["lo"], nw["hi"] = lo, hi
                out.append(nw)
        else:
            out.append(w)
    return out, removed


def _flag_opening(op: dict, msg: str,
                  conflicts: List[str], warns: List[str]) -> None:
    """D12 落墙判定的统一上报: review 门降级为 WARN, 否则 ERROR(挡存)."""
    if op.get("review"):
        warns.append(msg + " (review)")
    else:
        conflicts.append(msg)


# --------------------------------------------------------------------------- #
#  门 (§③)
# --------------------------------------------------------------------------- #
def door_frame(op: dict):
    """由 axis/at/span/hinge/swing 计算 hinge/jamb/open_tip/width/perp."""
    axis = op["wall"]["axis"]
    at = op["wall"]["at"]
    lo, hi = op["wall"]["span"]
    w = hi - lo
    hingeC = lo if op.get("hinge") == "lo" else hi
    jambC = hi if op.get("hinge") == "lo" else lo
    perp = 1 if op.get("swing") == "+" else -1
    if axis == "v":
        hinge = (at, hingeC)
        jamb = (at, jambC)
        open_tip = (at + perp * w, hingeC)
    else:
        hinge = (hingeC, at)
        jamb = (jambC, at)
        open_tip = (hingeC, at + perp * w)
    return hinge, jamb, open_tip, w, perp


def _double_leaves(op: dict):
    """对开双扇 (P5 门批次): 跨中点对半, 两扇各铰接在【外侧】门垛, 中间对开。
    返回 [{hinge_pt, jamb_pt, open_tip, width}, ...] 两扇。"""
    axis = op["wall"]["axis"]
    at = op["wall"]["at"]
    lo, hi = op["wall"]["span"]
    mid = (lo + hi) / 2.0
    half = (hi - lo) / 2.0
    perp = 1 if op.get("swing") == "+" else -1

    def _leaf(hc, jc):
        if axis == "v":
            return {"hinge_pt": (at, hc), "jamb_pt": (at, jc),
                    "open_tip": (at + perp * half, hc), "width": half}
        return {"hinge_pt": (hc, at), "jamb_pt": (jc, at),
                "open_tip": (hc, at + perp * half), "width": half}

    return [_leaf(lo, mid), _leaf(hi, mid)]


def build_door(op: dict) -> dict:
    out = {
        "id": op["id"],
        "kind": "door",
        "door_type": op.get("door_type", "swing"),
        # 门材质 (P5): 默认 wood 零迁移 (现有 geometry.json 无 material 键 -> wood, 渲染不变);
        # glass 复用窗玻璃配方。仅内存键, 不进 SVG -> golden 逐字节不变。
        "material": op.get("material", "wood"),
        "axis": op["wall"]["axis"],
        "at": op["wall"]["at"],
        "span": list(op["wall"]["span"]),
        "review": op.get("review", False),
        "between": op.get("between"),
    }
    door_type = op.get("door_type")
    if door_type == "sliding":
        out["panels"] = op.get("panels", 2)
    elif door_type == "double":
        # 对开双扇 (P5): 修复「编辑器暴露 double 但引擎按单扇 swing 渲染」。两扇 leaves[]。
        out["swing"] = op.get("swing")
        out["leaves"] = _double_leaves(op)
    else:
        hinge, jamb, open_tip, w, perp = door_frame(op)
        out.update({"hinge": op.get("hinge"), "swing": op.get("swing"),
                    "hinge_pt": hinge, "jamb_pt": jamb,
                    "open_tip": open_tip, "width": w})
    return out


def window_rect(op: dict, mm_per_px: float, thickness: dict) -> dict:
    return {
        "id": op["id"],
        "kind": "window",
        "wtype": op.get("wtype", "normal"),
        "axis": op["wall"]["axis"],
        "at": op["wall"]["at"],
        "span": list(op["wall"]["span"]),
        "cut": op.get("cut", False),
    }


# --------------------------------------------------------------------------- #
#  尺寸 (§④)  —  顶/左尺寸链刻度
# --------------------------------------------------------------------------- #
def _footprint_columns(G: dict, axis: str):
    """沿 axis 方向把 footprint(interior+outdoor+shared) 切成常量段.

    axis='top'  -> 对每个 x-区间求 minY (silhouette).
    axis='left' -> 对每个 y-区间求 minX.
    返回 (breaks, sil) : breaks=排序坐标, sil[i]=区间[breaks[i],breaks[i+1]]的极值(None=无)."""
    rooms = [r for r in _rooms_xywh(G)
             if r[2] in ("interior", "outdoor", "shared")]
    if axis == "top":      # 沿 x 分段, 求 minY
        coords = sorted({v for r in rooms for v in (r[3], r[5])})
        sil = []
        for lo, hi in zip(coords, coords[1:]):
            mid = (lo + hi) / 2.0
            ys = [r[4] for r in rooms if r[3] <= mid <= r[5]]
            sil.append(min(ys) if ys else None)
        return coords, sil
    else:                  # left: 沿 y 分段, 求 minX
        coords = sorted({v for r in rooms for v in (r[4], r[6])})
        sil = []
        for lo, hi in zip(coords, coords[1:]):
            mid = (lo + hi) / 2.0
            xs = [r[3] for r in rooms if r[4] <= mid <= r[6]]
            sil.append(min(xs) if xs else None)
        return coords, sil


def gen_dims(G: dict, walls: List[dict]) -> Dict[str, List[float]]:
    """生成 top/left 尺寸链刻度 (规格 §④, finding20/21).

    规则: footprint 的 silhouette(极值线); 链从 "首个抵达全局极值的坐标" 起,
    到 footprint 末端止; 刻度 = 落在 silhouette 上的正交墙 at + 链端点."""
    eps = G.get("meta", {}).get("eps", 1)
    exclude = set(G.get("dims", {}).get("exclude_coords", []))
    sides = G.get("dims", {}).get("sides", ["top", "left"])
    result: Dict[str, List[float]] = {}

    # 墙 at 索引
    vwalls = [w for w in walls if w["axis"] == "v"]
    hwalls = [w for w in walls if w["axis"] == "h"]

    for side in sides:
        coords, sil = _footprint_columns(G, side)
        vals = [s for s in sil if s is not None]
        if not vals:
            result[side] = []
            continue
        gmin = min(vals)
        # 链起点 = 首个 silhouette==gmin 的区间左端
        start = None
        for i, s in enumerate(sil):
            if s is not None and abs(s - gmin) <= eps:
                start = coords[i]
                break
        end = coords[-1]

        def sil_at(c):
            """坐标 c 处相邻区间 silhouette 的最小值."""
            cand = []
            for i, (lo, hi) in enumerate(zip(coords, coords[1:])):
                if abs(lo - c) <= eps or abs(hi - c) <= eps:
                    if sil[i] is not None:
                        cand.append(sil[i])
            return min(cand) if cand else None

        perp = vwalls if side == "top" else hwalls
        ticks = set()
        for w in perp:
            at = w["at"]
            if at < start - eps or at > end + eps:
                continue
            top_end = min(w["lo"], w["hi"])   # 墙 "靠 silhouette" 端
            s = sil_at(at)
            if s is not None and abs(top_end - s) <= eps:
                ticks.add(at)
        ticks.add(start)
        ticks.add(end)
        result[side] = sorted(t for t in ticks if t not in exclude)

    return result


# --------------------------------------------------------------------------- #
#  derive (主入口)
# --------------------------------------------------------------------------- #
def _wall_to_tuple(w: dict) -> Tuple:
    axis, at = w["axis"], w["at"]
    if axis == "v":
        ax, ay, bx, by = at, w["lo"], at, w["hi"]
    else:
        ax, ay, bx, by = w["lo"], at, w["hi"], at
    ext = w["role"] in EXT_ROLES
    style = w.get("style") or DEFAULT_STYLE[w["role"]]
    lowz = w["role"] in LOWZ_ROLES
    return (ax, ay, bx, by, ext, style, lowz)


def derive(G: dict) -> dict:
    eps = G.get("meta", {}).get("eps", 1)
    mm = G.get("meta", {}).get("mm_per_px", 10)
    thick = G.get("meta", {}).get("wall_thickness_mm", DEFAULT_THICKNESS_MM)

    conflicts: List[str] = []
    warns: List[str] = []

    walls = _room_walls(G, conflicts)
    walls = _add_free_walls(walls, G, eps)

    doors: List[dict] = []
    windows: List[dict] = []
    passages: List[dict] = []

    for op in G.get("openings", []):
        kind = op.get("kind")
        if op.get("cut"):
            axis = op["wall"]["axis"]
            at = op["wall"]["at"]
            span = op["wall"]["span"]
            walls, removed = _subtract_opening(walls, axis, at, span)
            # D12: span 必须完整 ⊆ 某条连续派生墙(容差 EPS).
            # removed = span∩派生墙并集 的覆盖长度; uncovered = span 端部悬空长度.
            uncovered = (span[1] - span[0]) - removed
            if removed < eps:                        # 整段都不落墙
                _flag_opening(op, "opening %s 不落任何连续派生墙" % op["id"],
                              conflicts, warns)
            elif uncovered > eps:                    # 一/两端伸出墙端 (部分落墙)
                _flag_opening(op, "opening %s span 端部不落连续派生墙" % op["id"],
                              conflicts, warns)
        if kind == "door":
            doors.append(build_door(op))
        elif kind == "window":
            windows.append(window_rect(op, mm, thick))
        elif kind == "passage":
            # 审计 P1: 通道口此前仅切墙、不进任何派生产物 —— room_brief/layout 无法避让,
            # AI 可把家具正对开放通道口摆放堵死动线。作为无门扇的洞口进 passages。
            wall = op.get("wall") or {}
            passages.append(
                {
                    "id": op.get("id"),
                    "kind": "passage",
                    "axis": wall.get("axis", op.get("axis")),
                    "at": wall.get("at", op.get("at")),
                    "span": list(wall.get("span") or op.get("span") or [0, 0]),
                }
            )

    walls = _merge_collinear(walls, eps)
    wall_tuples = [_wall_to_tuple(w) for w in walls]
    dims = gen_dims(G, walls)

    return {
        "walls": wall_tuples,
        "doors": doors,
        "windows": windows,
        "passages": passages,
        "dims": dims,
        "conflicts": conflicts,
        "warns": warns,
        "_walls_raw": walls,   # 调试/对比用 (dict 形式)
    }


# --------------------------------------------------------------------------- #
#  validate (§⑤)
# --------------------------------------------------------------------------- #
def _overlap_area(a, b) -> float:
    ox = max(0.0, min(a[5], b[5]) - max(a[3], b[3]))
    oy = max(0.0, min(a[6], b[6]) - max(a[4], b[4]))
    return ox * oy


# --------------------------------------------------------------------------- #
#  异形空间 / merge groups (P3 一期): 把 r["merge"]=<group_id> 的同组房聚成逻辑房间。
#  纯只读聚合 —— derive()/validate() 不调用本区, 无 merge 数据全链路逐字节不变 (golden 只
#  校 derive)。所有下游 (scene/brief/prompt/slice/前端) 从这里取并集几何, 单一真源。
# --------------------------------------------------------------------------- #
def merge_groups(G: dict) -> dict:
    """{group_id: {members, member_rects, bbox, rep}} —— 仅收成员 >=2 的非空 merge 组。

    member_rects = [(room_id, x0, y0, x1, y1) ...] 按 id 稳定序 (绝对角点)。
    bbox = 成员并集包围盒。rep = 代表成员 (最大面积, 平局取最小 id) —— 供简报/标签用稳定 id。
    单成员组 / 无 merge 房不入表 -> 调用方回退单房路径 (byte-safe)。
    """
    buckets: dict = {}
    for r in G.get("rooms", []):
        mid = r.get("merge")
        if not mid:
            continue
        x, y, w, h = r["rect"]
        buckets.setdefault(mid, []).append(
            (r["id"], float(x), float(y), float(x) + float(w), float(y) + float(h))
        )
    out: dict = {}
    for mid, rects in buckets.items():
        if len(rects) < 2:
            continue
        member_rects = sorted(rects, key=lambda t: t[0])
        rep = min(
            member_rects, key=lambda t: (-(t[3] - t[1]) * (t[4] - t[2]), t[0])
        )[0]
        out[mid] = {
            "members": [t[0] for t in member_rects],
            "member_rects": member_rects,
            "bbox": (
                min(t[1] for t in member_rects),
                min(t[2] for t in member_rects),
                max(t[3] for t in member_rects),
                max(t[4] for t in member_rects),
            ),
            "rep": rep,
        }
    return out


def room_group_of(G: dict) -> dict:
    """room_id -> group_id (仅 >=2 成员组; 其余不在表)。"""
    return {rid: gid for gid, g in merge_groups(G).items() for rid in g["members"]}


def group_rep_map(G: dict) -> dict:
    """room_id -> 代表 room_id (仅组成员; 非组成员不在表 -> 调用方回退自身)。"""
    return {rid: g["rep"] for g in merge_groups(G).values() for rid in g["members"]}


def nearest_part(member_rects, px, py) -> str:
    """点 (px,py) -> 最近成员 room_id, 确定性 tie-break 距离→面积(大优先)→id。

    距离 = 点在某成员矩形内则 0, 否则到该矩形的欧氏间隙。member_rects=[(id,x0,y0,x1,y1)]。
    """
    def _key(t):
        rid, x0, y0, x1, y1 = t
        dx = max(x0 - px, 0.0, px - x1)
        dy = max(y0 - py, 0.0, py - y1)
        return ((dx * dx + dy * dy), -((x1 - x0) * (y1 - y0)), rid)

    return min(member_rects, key=_key)[0]


def point_in_any(member_rects, px, py) -> bool:
    """点是否落在任一成员矩形内 (L 形凹口自然排除, 因逐矩形判定)。"""
    return any(x0 <= px <= x1 and y0 <= py <= y1 for (_i, x0, y0, x1, y1) in member_rects)


def rect_covered_by(box, member_rects) -> bool:
    """轴对齐 box=(x0,y0,x1,y1) 是否被成员矩形【并集】完全覆盖 (坐标压缩逐格判定)。

    用并集覆盖而非并集包围盒 —— 后者会错纳 L 形凹口。member_rects=[(id,x0,y0,x1,y1)]。
    """
    bx0, by0, bx1, by1 = box
    if bx1 - bx0 <= 1e-6 or by1 - by0 <= 1e-6:
        return True
    xs = sorted(
        v for v in ({bx0, bx1} | {t[1] for t in member_rects} | {t[3] for t in member_rects})
        if bx0 - 1e-9 <= v <= bx1 + 1e-9
    )
    ys = sorted(
        v for v in ({by0, by1} | {t[2] for t in member_rects} | {t[4] for t in member_rects})
        if by0 - 1e-9 <= v <= by1 + 1e-9
    )
    for i in range(len(xs) - 1):
        cx = (xs[i] + xs[i + 1]) / 2.0
        for j in range(len(ys) - 1):
            cy = (ys[j] + ys[j + 1]) / 2.0
            if not any(x0 <= cx <= x1 and y0 <= cy <= y1 for (_i, x0, y0, x1, y1) in member_rects):
                return False
    return True


def validate(G: dict) -> List[Tuple[str, str]]:
    issues: List[Tuple[str, str]] = []
    rooms = _rooms_xywh(G)

    # 非正交 / 零面积
    for r in G["rooms"]:
        x, y, w, h = r["rect"]
        if w <= 0 or h <= 0:
            issues.append(("ERROR", "room %s 零/负面积" % r["id"]))

    # 净矩形重叠默认拦截 + 显式合并豁免 (D1).
    #   任意两房净矩形重叠 -> ERROR, 除非两房标记了相同且非空的「合并组」(merge).
    #   merge 仅为元数据, derive() 不读 (确保 build 不变); 仅 validate 在此消费.
    merge_of = {r["id"]: r.get("merge") for r in G["rooms"]}
    for i in range(len(rooms)):
        for j in range(i + 1, len(rooms)):
            a, b = rooms[i], rooms[j]
            if _overlap_area(a, b) <= 1e-6:
                continue
            ma, mb = merge_of.get(a[0]), merge_of.get(b[0])
            if ma and mb and ma == mb:
                continue                      # 同一合并组 -> 正当重叠, 豁免
            if a[1] != b[1]:
                issues.append(("ERROR", "跨 space 重叠: %s(%s) x %s(%s)"
                               % (a[0], a[1], b[0], b[1])))
            else:
                issues.append(("ERROR", "房间重叠未标记合并: %s x %s"
                               "(用「打通」标记合并或拖开)" % (a[0], b[0])))

    # outline_override 非空 (D2)
    if G.get("meta", {}).get("outline_override"):
        issues.append(("WARN", "outline_override 非空 (D2 应删除)"))

    # between 两侧同 space
    for op in G.get("openings", []):
        bt = op.get("between")
        if bt and len(bt) == 2 and bt[0] == bt[1]:
            issues.append(("WARN", "opening %s between 两侧同 space" % op["id"]))

    # derive 期间冲突
    res = derive(G)
    for c in res["conflicts"]:
        issues.append(("ERROR", c))
    for w in res["warns"]:
        issues.append(("WARN", w))

    return issues


if __name__ == "__main__":
    import sys
    G = load(sys.argv[1] if len(sys.argv) > 1 else "geometry-D户型.json")
    res = derive(G)
    print("walls:", len(res["walls"]), "doors:", len(res["doors"]),
          "windows:", len(res["windows"]))
    print("dims:", res["dims"])
    print("conflicts:", res["conflicts"])
    print("warns:", res["warns"])
