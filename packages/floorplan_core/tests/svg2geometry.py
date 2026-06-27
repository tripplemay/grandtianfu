#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""svg2geometry.py — 迁移工具 兼 金测解析器.

迁移: 解析 平面布置图-无家具.svg -> geometry-D户型.json.
金测: parse_golden / arc_center_hinge / parse_path_segments 等被 verify_golden 复用,
      作为 SVG 侧的 ground-truth 解析器与 derive 结果逐段比对.
SRC_DEFAULT / OUT_DEFAULT 默认指向 tests/fixtures/ 冻结副本 (不依赖活数据),
可用 GOLDEN_SRC / GOLDEN_OUT 环境变量覆盖.

实现规格 §⑦ P0 迁移:
  * 房间矩形读自现 SVG (含 D1 净矩形去重叠修正: lobby/study).
  * 空间分配按 D10: 原图共享边有墙=异 space, 无墙=并 space
    (corr_pl 并入 suite_g; foyer 并入 living, 与 r_live 同 space 允许重叠).
  * passage 反推 (D10): 对每条派生异-space 边, 用 "candidate - 原墙 - 门跨" 的差集补 passage.
  * 门定位 (D11): 解析 door-arc/door-leaf 反解 hinge/jamb/open_tip; at 按重叠优先
    吸附到派生墙中线 (D6); 漂移门 (无法干净落墙) 标 review:true.
  * 窗 (D6): rect -> (axis,at,span,wtype), at 吸附墙中线.

用法:  python3 svg2geometry.py [src.svg] [out.json]
"""
from __future__ import annotations

import json
import math
import re
import sys
import os

from floorplan_core import geometry as geo

HERE = os.path.dirname(os.path.abspath(__file__))
# 金测 fixture (冻结副本, 不依赖活数据); 可用 env 覆盖.
FIXTURES = os.path.join(HERE, "fixtures")
SRC_DEFAULT = os.environ.get("GOLDEN_SRC", os.path.join(FIXTURES, "平面布置图-无家具.svg"))
OUT_DEFAULT = os.environ.get("GOLDEN_OUT", os.path.join(FIXTURES, "geometry-D户型.json"))

# --------------------------------------------------------------------------- #
#  空间元数据 (id -> category/label/style)
# --------------------------------------------------------------------------- #
SPACES = {
    "garden":  {"category": "outdoor",  "label": "入户花园", "style": "solid"},
    "balcony": {"category": "outdoor",  "label": "生活阳台", "style": "solid"},
    "entry":   {"category": "interior", "label": "玄关/前室", "style": "solid"},
    "living":  {"category": "interior", "label": "客厅·餐厅·厨房", "style": "solid"},
    "kitchen": {"category": "interior", "label": "厨房",     "style": "solid"},
    "study":   {"category": "interior", "label": "书房",     "style": "solid"},
    "guest2":  {"category": "interior", "label": "次卧(二)", "style": "solid"},
    "lobby":   {"category": "interior", "label": "内部过渡", "style": "solid"},
    "wc_pub":  {"category": "interior", "label": "公卫",     "style": "solid"},
    "cloak":   {"category": "interior", "label": "主卧衣帽间", "style": "solid"},
    "mbath":   {"category": "interior", "label": "主卫",     "style": "solid"},
    "master":  {"category": "interior", "label": "主卧睡眠区", "style": "solid"},
    "suite_g": {"category": "interior", "label": "次卧套房", "style": "solid"},
    "bath_g":  {"category": "interior", "label": "次卫",     "style": "solid"},
    "public":  {"category": "shared",   "label": "公共区",   "style": "dashed"},
}

# 房间 (id, space, type, rect[x,y,w,h]) — 读自 SVG, 含 D1 去重叠修正
ROOMS = [
    ("r_pub1",    "public",  "public",   [0, 250, 180, 390]),
    ("r_pub2",    "public",  "public",   [0, 640, 495, 280]),
    ("r_garden",  "garden",  "outdoor",  [365, 0, 310, 250]),
    ("r_vest",    "entry",   "living",   [180, 250, 315, 390]),
    ("r_foyer",   "living",  "living",   [495, 250, 180, 390]),   # D10: 并入 living
    ("r_live",    "living",  "living",   [495, 490, 720, 765]),
    ("r_kit",     "kitchen", "wet",      [675, 265, 330, 225]),
    ("r_balc",    "balcony", "outdoor",  [1005, 265, 210, 225]),
    ("r_liveext", "living",  "living",   [495, 1255, 720, 155]),
    ("r_corr_g",  "suite_g", "corridor", [180, 920, 315, 100]),
    ("r_bed_g",   "suite_g", "bedroom",  [180, 1020, 315, 390]),
    ("r_bath_g",  "bath_g",  "wet",      [0, 1020, 180, 390]),
    ("r_corr_pl", "suite_g", "corridor", [0, 920, 180, 100]),     # D10: 并入 suite_g
    ("r_study",   "study",   "bedroom",  [1215, 170, 300, 320]),
    ("r_guest2",  "guest2",  "bedroom",  [1515, 170, 300, 400]),
    ("r_lobby",   "lobby",   "corridor", [1215, 490, 300, 190]),  # D1: 缩至 y[490,680]
    ("r_wcpub",   "wc_pub",  "wet",      [1515, 570, 300, 190]),
    ("r_cloak",   "cloak",   "bedroom",  [1215, 680, 300, 340]),
    ("r_mbath",   "mbath",   "wet",      [1515, 760, 300, 260]),
    ("r_master",  "master",  "bedroom",  [1215, 1020, 600, 390]),
]

# 自由墙 (房间边推不出者; D8) — 公共虚线 L + 电梯厅 4 细线 + 衣帽间残段
FREE_WALLS = [
    {"id": "fw_pub_h", "axis": "h", "at": 640, "span": [0, 180], "role": "public", "style": "dashed"},
    {"id": "fw_pub_v", "axis": "v", "at": 180, "span": [640, 920], "role": "public", "style": "dashed"},
    {"id": "fw_elev1", "axis": "h", "at": 480, "span": [0, 180], "role": "thin", "style": "thin"},
    {"id": "fw_elev2", "axis": "h", "at": 520, "span": [0, 180], "role": "thin", "style": "thin"},
    {"id": "fw_elev3", "axis": "h", "at": 560, "span": [0, 180], "role": "thin", "style": "thin"},
    {"id": "fw_elev4", "axis": "h", "at": 600, "span": [0, 180], "role": "thin", "style": "thin"},
    {"id": "fw_clk",   "axis": "v", "at": 1435, "span": [680, 760], "role": "interior"},
]

LABELS = {
    "r_garden": {"zh": "入户花园", "en": "COURTYARD", "at": [542, 110]},
    "r_vest": {"zh": "玄关", "en": "VESTIBULE", "at": [337, 420]},
    "r_kit": {"zh": "厨房", "en": "KITCHEN", "at": [860, 435]},
    "r_balc": {"zh": "生活阳台", "en": "UTILITY BALCONY", "at": [1110, 435]},
    "r_study": {"zh": "书房", "en": "STUDY", "at": [1365, 330]},
    "r_guest2": {"zh": "次卧(二)", "en": "GUESTROOM 2", "at": [1665, 390]},
    "r_lobby": {"zh": "内部过渡", "en": "PRIVATE LOBBY", "at": [1340, 625]},
    "r_wcpub": {"zh": "公卫", "en": "PUBLIC RESTROOM", "at": [1665, 665]},
    "r_cloak": {"zh": "主卧衣帽间", "en": "CLOAKROOM", "at": [1365, 880]},
    "r_mbath": {"zh": "主卫", "en": "MASTER BATH", "at": [1665, 880]},
    "r_master": {"zh": "主卧睡眠区", "en": "MASTER BEDROOM", "at": [1515, 1200]},
    "r_live": {"zh": "餐厅区", "en": "DINING AREA", "at": [855, 750]},
    "r_liveext": {"zh": "客厅·景观区", "en": "LIVING (EXT)", "at": [855, 1372]},
    "r_corr_g": {"zh": "套内过道", "en": "CORRIDOR", "at": [337, 965]},
    "r_bed_g": {"zh": "次卧套房", "en": "GUEST SUITE", "at": [337, 1210]},
    "r_bath_g": {"zh": "次卫", "en": "BATH", "at": [90, 1210]},
    "r_pub1": {"zh": "公共电梯厅", "at": [90, 350], "style": "public"},
    "r_pub2": {"zh": "公共楼梯间", "at": [250, 780], "style": "public"},
}

EPS = 1.0
# 门重建参数 (D11):
MAXSNAP = 90        # at 吸附搜索半径 px (容纳漂移门 d11 move=80)
MAX_DOOR_GAP = 130  # 门级缺口最大宽度 px (>此值视作敞口/通道, 不整段当门)
MOVE_TOL = 10       # at 漂移容差; 超过即标 review (D11 坐标漂移>容差)
MIN_DOOR_W = 40     # 门洞最小宽度 px; 低于此为无效门


# --------------------------------------------------------------------------- #
#  SVG 解析
# --------------------------------------------------------------------------- #
def _seg_axis(x1, y1, x2, y2):
    if abs(x1 - x2) < 1e-6:
        return ("v", x1, min(y1, y2), max(y1, y2))
    if abs(y1 - y2) < 1e-6:
        return ("h", y1, min(x1, x2), max(x1, x2))
    return None


def parse_path_segments(d: str):
    """解析绝对命令 M/L/H/V/Z 路径 -> [(axis,at,lo,hi), ...]."""
    toks = re.findall(r"[MLHVZ]|-?\d+\.?\d*", d)
    segs = []
    i = 0
    cur = None
    start = None
    cmd = None
    while i < len(toks):
        t = toks[i]
        if t in "MLHVZ":
            cmd = t
            i += 1
            if cmd == "Z":
                if cur and start and cur != start:
                    s = _seg_axis(cur[0], cur[1], start[0], start[1])
                    if s:
                        segs.append(s)
                cur = start
            continue
        # 数值: 按当前 cmd 取参数
        if cmd in ("M", "L"):
            x = float(toks[i]); y = float(toks[i + 1]); i += 2
            pt = (x, y)
            if cmd == "M":
                cur = pt; start = pt
            else:
                s = _seg_axis(cur[0], cur[1], pt[0], pt[1])
                if s:
                    segs.append(s)
                cur = pt
            # 连续坐标视作隐式 L
            cmd = "L"
        elif cmd == "H":
            x = float(toks[i]); i += 1
            pt = (x, cur[1])
            s = _seg_axis(cur[0], cur[1], pt[0], pt[1])
            if s:
                segs.append(s)
            cur = pt
        elif cmd == "V":
            y = float(toks[i]); i += 1
            pt = (cur[0], y)
            s = _seg_axis(cur[0], cur[1], pt[0], pt[1])
            if s:
                segs.append(s)
            cur = pt
        else:
            i += 1
    return segs


def parse_golden(svg: str):
    """返回 (walls_by_at, doors_raw, windows_raw, sliding_raw).

    walls_by_at: {(axis,at): [[lo,hi],...]} 合并后 (所有墙类合并, 仅几何)."""
    # 只取 translate 组内
    walls = []

    # path: wall-thick / wall-public
    for m in re.finditer(r'<path class="(wall-thick|wall-public)"[^>]*d="([^"]*)"', svg, re.S):
        for s in parse_path_segments(m.group(2)):
            walls.append(s)

    # line: wall-thick / wall-thin / wall-public + struct(#1a1a1a)
    for m in re.finditer(r'<line\b([^>]*)/?>', svg):
        attrs = m.group(1)
        cls = re.search(r'class="([^"]*)"', attrs)
        stroke = re.search(r'stroke="([^"]*)"', attrs)
        is_wall = False
        if cls and cls.group(1) in ("wall-thick", "wall-thin", "wall-public"):
            is_wall = True
        elif stroke and stroke.group(1) == "#1a1a1a":
            is_wall = True
        if not is_wall:
            continue
        def gv(name):
            mm = re.search(r'%s="(-?\d+\.?\d*)"' % name, attrs)
            return float(mm.group(1)) if mm else None
        x1, y1, x2, y2 = gv("x1"), gv("y1"), gv("x2"), gv("y2")
        if None in (x1, y1, x2, y2):
            continue
        s = _seg_axis(x1, y1, x2, y2)
        if s:
            walls.append(s)

    walls_by_at = {}
    for axis, at, lo, hi in walls:
        walls_by_at.setdefault((axis, at), []).append([lo, hi])
    walls_by_at = {k: geo.merge_intervals(v, EPS) for k, v in walls_by_at.items()}

    # doors: arc + leaf (按文档序成对)
    arcs = []
    for m in re.finditer(
            r'<path class="door-arc" d="M\s*(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+A\s*(-?\d+\.?\d*)\s+'
            r'-?\d+\.?\d*\s+0\s+0\s+(\d)\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)"', svg):
        mx, my, r, sweep, ex, ey = (float(m.group(1)), float(m.group(2)),
                                    float(m.group(3)), int(m.group(4)),
                                    float(m.group(5)), float(m.group(6)))
        arcs.append({"jamb": (mx, my), "r": r, "sweep": sweep, "open_tip": (ex, ey)})
    leaves = []
    for m in re.finditer(
            r'<line class="door-leaf" x1="(-?\d+\.?\d*)" y1="(-?\d+\.?\d*)" '
            r'x2="(-?\d+\.?\d*)" y2="(-?\d+\.?\d*)"', svg):
        leaves.append(((float(m.group(1)), float(m.group(2))),
                       (float(m.group(3)), float(m.group(4)))))
    doors_raw = []
    for i, arc in enumerate(arcs):
        leaf = leaves[i] if i < len(leaves) else None
        doors_raw.append({**arc, "leaf": leaf})

    # sliding rects
    sliding_raw = []
    for m in re.finditer(
            r'<rect class="door-sliding" x="(-?\d+\.?\d*)" y="(-?\d+\.?\d*)" '
            r'width="(-?\d+\.?\d*)" height="(-?\d+\.?\d*)"', svg):
        sliding_raw.append((float(m.group(1)), float(m.group(2)),
                            float(m.group(3)), float(m.group(4))))

    # windows
    windows_raw = []
    for m in re.finditer(r'<rect class="window"([^>]*)/?>', svg):
        attrs = m.group(1)
        def gv(name, d=None):
            mm = re.search(r'%s="([^"]*)"' % name, attrs)
            return mm.group(1) if mm else d
        x = float(gv("x")); y = float(gv("y"))
        w = float(gv("width")); h = float(gv("height"))
        wtype = gv("data-wtype", "normal")
        windows_raw.append((x, y, w, h, wtype))

    return walls_by_at, doors_raw, sliding_raw, windows_raw


# --------------------------------------------------------------------------- #
#  几何辅助
# --------------------------------------------------------------------------- #
def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def overlap_len(a, b):
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def snap_at(axis, raw_at, span, cand):
    """把开洞 at 吸附到候选墙中线: 在 ±60px 内选与 span 重叠最大的 at.

    返回 (at, fully_covered: bool)."""
    best_at, best_ov, best_cov = raw_at, -1.0, False
    for (cax, cat), segs in cand.items():
        if cax != axis or abs(cat - raw_at) > 60:
            continue
        ov = max((overlap_len(span, s) for s in segs), default=0.0)
        if ov > best_ov + 1e-9:
            best_ov = ov
            best_at = cat
            best_cov = any(s[0] - EPS <= span[0] and s[1] + EPS >= span[1] for s in segs)
    if best_ov < 0:
        return raw_at, False
    return best_at, best_cov


def between_of(rooms, axis, at, span):
    m = (span[0] + span[1]) / 2.0
    if axis == "v":
        a = geo._occ(rooms, at - 1, m)
        b = geo._occ(rooms, at + 1, m)
    else:
        a = geo._occ(rooms, m, at - 1)
        b = geo._occ(rooms, m, at + 1)
    return [a[0], b[0]]


# --------------------------------------------------------------------------- #
#  门重建 (D11) — 处理混合 arc 朝向
# --------------------------------------------------------------------------- #
def arc_center_hinge(leaf, arc_m, arc_e, r):
    """hinge = 距两 arc 端点均约 r 的 leaf 端点 (= 弧心), 与 sweep 朝向无关."""
    def err(p):
        return abs(dist(p, arc_m) - r) + abs(dist(p, arc_e) - r)
    return leaf[0] if err(leaf[0]) <= err(leaf[1]) else leaf[1]


def door_axis_options(hinge, arc_m, arc_e):
    """对两个 arc 端点各试一次作 jamb (闭合端), 返回墙向候选.

    每候选 = (axis, at_raw, span_raw, hinge_along, perp).
    jamb=沿墙闭合端; 另一 arc 端点=open_tip(墙法向), 决定 swing.
    自然处理两种 sweep: 哪一端是开侧由几何 (与 hinge 共线者为墙向) 自动确定."""
    opts = []
    for jamb in (arc_m, arc_e):
        open_tip = arc_e if jamb is arc_m else arc_m
        dx = abs(hinge[0] - jamb[0])
        dy = abs(hinge[1] - jamb[1])
        if dx < 1 and dy < 1:
            continue
        if dx < 1:                      # hinge->jamb 竖直 => 竖墙
            axis = "v"
            at = hinge[0]
            span = sorted([hinge[1], jamb[1]])
            hinge_along = hinge[1]
            perp = 1 if open_tip[0] > at else -1
        elif dy < 1:                    # hinge->jamb 水平 => 横墙
            axis = "h"
            at = hinge[1]
            span = sorted([hinge[0], jamb[0]])
            hinge_along = hinge[0]
            perp = 1 if open_tip[1] > at else -1
        else:
            continue                    # 斜向 (异常) 跳过
        opts.append((axis, at, span, hinge_along, perp))
    return opts


def placements_for(axis, at_raw, span_raw, cand, golden):
    """枚举 span_raw 可落的派生墙(axis,cat) 落点 (D11 缺口优先).

    每记录 = {axis,at,span,covered,has_gap,ov,move}.
    span: 若命中门级缺口(<=MAX_DOOR_GAP) 则吸附为该缺口(真实洞口);
          否则把 drawn span 夹入派生墙段."""
    recs = []
    for (cax, cat), segs in cand.items():
        if cax != axis or abs(cat - at_raw) > MAXSNAP:
            continue
        gaps = geo.diff_intervals(segs, golden.get((cax, cat), []))
        gap_hit, gap_ov = None, 0.0
        for g in gaps:
            o = overlap_len(span_raw, g)
            if o > gap_ov:
                gap_ov, gap_hit = o, g
        seg, seg_ov = None, 0.0
        for s in segs:
            o = overlap_len(span_raw, s)
            if o > seg_ov:
                seg_ov, seg = o, s
        if seg is None:
            continue
        if gap_hit is not None and gap_ov > 0:
            if gap_hit[1] - gap_hit[0] <= MAX_DOOR_GAP:
                span = [float(gap_hit[0]), float(gap_hit[1])]
                covered = True
            else:                       # 缺口过大=敞口: 只取 drawn 段
                span = [max(span_raw[0], seg[0]), min(span_raw[1], seg[1])]
                covered = (span_raw[0] >= seg[0] - EPS and span_raw[1] <= seg[1] + EPS)
            recs.append({"axis": axis, "at": cat, "span": span, "covered": covered,
                         "has_gap": True, "ov": gap_ov, "move": abs(cat - at_raw)})
        else:
            span = [max(span_raw[0], seg[0]), min(span_raw[1], seg[1])]
            covered = (span_raw[0] >= seg[0] - EPS and span_raw[1] <= seg[1] + EPS)
            recs.append({"axis": axis, "at": cat, "span": span, "covered": covered,
                         "has_gap": False, "ov": seg_ov, "move": abs(cat - at_raw)})
    return recs


def reconstruct_door(dr, cand, golden, rooms_occ, accepted):
    """由单个 arc+leaf 反解一扇平开门 (返回 op dict + 记录 cut span).

    accepted: {(axis,at):[span,...]} 已接受门跨度, 用于碰撞检测 (重复门标 review)."""
    leaf, arc_m, arc_e, r = dr["leaf"], dr["jamb"], dr["open_tip"], dr["r"]
    if leaf is None:
        return None
    hinge = arc_center_hinge(leaf, arc_m, arc_e, r)

    recs = []
    for axis, at_raw, span_raw, hinge_along, perp in door_axis_options(hinge, arc_m, arc_e):
        for rc in placements_for(axis, at_raw, span_raw, cand, golden):
            a, b = between_of(rooms_occ, rc["axis"], rc["at"], rc["span"])
            rc["between"] = [a, b]
            rc["distinct"] = (a != b and a is not None and b is not None)
            acc = accepted.get((rc["axis"], rc["at"]), [])
            rc["collision"] = any(overlap_len(rc["span"], s) > EPS for s in acc)
            rc["hinge_along"] = hinge_along
            rc["perp"] = perp
            recs.append(rc)
    if not recs:
        return None

    # 选优: 异space > 落墙 > 不碰撞 > 命中缺口 > 漂移小 > 重叠大
    best = max(recs, key=lambda r: (
        1 if r["distinct"] else 0,
        1 if r["covered"] else 0,
        0 if r["collision"] else 1,
        1 if r["has_gap"] else 0,
        -r["move"],
        r["ov"],
    ))

    span = [round(best["span"][0]), round(best["span"][1])]
    width = span[1] - span[0]
    hinge_end = "lo" if abs(best["hinge_along"] - best["span"][0]) <= \
        abs(best["hinge_along"] - best["span"][1]) else "hi"
    swing = "+" if best["perp"] > 0 else "-"
    review = (not best["covered"]) or (not best["distinct"]) or \
        (best["move"] > MOVE_TOL) or best["collision"] or (width < MIN_DOOR_W)
    op = {"kind": "door", "door_type": "swing",
          "wall": {"axis": best["axis"], "at": best["at"], "span": span},
          "hinge": hinge_end, "swing": swing, "cut": True,
          "between": best["between"]}
    if review:
        op["review"] = True
    accepted.setdefault((best["axis"], best["at"]), []).append(best["span"])
    return op


# --------------------------------------------------------------------------- #
#  迁移主流程
# --------------------------------------------------------------------------- #
def build():
    src = sys.argv[1] if len(sys.argv) > 1 else SRC_DEFAULT
    out = sys.argv[2] if len(sys.argv) > 2 else OUT_DEFAULT
    with open(src, "r", encoding="utf-8") as fh:
        svg = fh.read()

    walls_by_at, doors_raw, sliding_raw, windows_raw = parse_golden(svg)

    # 组装 rooms / spaces / free_walls 的临时 G (用于 candidate)
    rooms_json = []
    for rid, sp, typ, rect in ROOMS:
        r = {"id": rid, "space": sp, "type": typ, "rect": rect}
        if rid in LABELS:
            r["label"] = {"zh": LABELS[rid]["zh"]}
            if "en" in LABELS[rid]:
                r["label"]["en"] = LABELS[rid]["en"]
            r["label"]["at"] = LABELS[rid]["at"]
            if "style" in LABELS[rid]:
                r["label"]["style"] = LABELS[rid]["style"]
        rooms_json.append(r)

    meta = {
        "house": "D", "schema_version": 2, "mm_per_px": 10,
        "origin": [150, 250], "canvas_viewbox": [0, 0, 2200, 1800],
        "wall_thickness_mm": geo.DEFAULT_THICKNESS_MM,
        "wall_height_mm": 1450, "grid": 5, "eps": 1,
    }
    G = {"meta": meta, "spaces": SPACES, "rooms": rooms_json,
         "free_walls": FREE_WALLS, "openings": []}

    cand = geo.candidate_walls(G)
    rooms_occ = geo._rooms_xywh(G)

    # ---- 解析门 (D11): arc 心定 hinge, 两端各试 jamb, 缺口优先, 漂移/碰撞标 review ----
    doors = []
    door_spans = {}     # (axis,at) -> [[lo,hi],...]  用于 gap 反推
    accepted = {}       # (axis,at) -> [[lo,hi],...]  门跨度碰撞检测
    for i, dr in enumerate(doors_raw):
        op = reconstruct_door(dr, cand, walls_by_at, rooms_occ, accepted)
        if op is None:
            continue
        op["id"] = "d%02d" % (i + 1)
        doors.append(op)
        sp = op["wall"]["span"]
        door_spans.setdefault((op["wall"]["axis"], op["wall"]["at"]), []).append(
            [float(sp[0]), float(sp[1])])

    # ---- 解析推拉门 (sliding) ----
    sliding_ops = []
    if sliding_raw:
        xs = [r[0] for r in sliding_raw] + [r[0] + r[2] for r in sliding_raw]
        ys = [r[1] + r[3] / 2.0 for r in sliding_raw]
        span = [min(xs), max(xs)]
        raw_at = sum(ys) / len(ys)
        # 判断方向: 宽>高 -> 横
        wsum = sum(r[2] for r in sliding_raw); hsum = sum(r[3] for r in sliding_raw)
        axis = "h" if wsum >= hsum else "v"
        if axis == "v":
            xs2 = [r[0] + r[2] / 2.0 for r in sliding_raw]
            ys2 = [r[1] for r in sliding_raw] + [r[1] + r[3] for r in sliding_raw]
            span = [min(ys2), max(ys2)]; raw_at = sum(xs2) / len(xs2)
        at, _cov = snap_at(axis, raw_at, span, cand)
        try:
            btw = between_of(rooms_occ, axis, at, span)
        except Exception:
            btw = None
        op = {"id": "d_kit", "kind": "door", "door_type": "sliding",
              "wall": {"axis": axis, "at": at, "span": [round(span[0]), round(span[1])]},
              "panels": len(sliding_raw), "cut": True, "between": btw}
        sliding_ops.append(op)
        door_spans.setdefault((axis, at), []).append([span[0], span[1]])

    # ---- 解析窗 (D6) ----
    windows = []
    for j, (x, y, w, h, wtype) in enumerate(windows_raw):
        if w >= h:
            axis = "h"; raw_at = y + h / 2.0; span = [x, x + w]
        else:
            axis = "v"; raw_at = x + w / 2.0; span = [y, y + h]
        at, _cov = snap_at(axis, raw_at, span, cand)
        windows.append({"id": "w%02d" % (j + 1), "kind": "window", "wtype": wtype,
                        "wall": {"axis": axis, "at": at,
                                 "span": [round(span[0]), round(span[1])]},
                        "cut": False})

    # ---- passage 反推 (D10): missing = candidate - 原墙 - 门跨 ----
    passages = []
    pidx = 0
    for (axis, at), cand_segs in sorted(cand.items()):
        golden = walls_by_at.get((axis, at), [])
        missing = geo.diff_intervals(cand_segs, golden)
        if not missing:
            continue
        dsp = door_spans.get((axis, at), [])
        gaps = geo.diff_intervals(missing, dsp)
        for lo, hi in gaps:
            if hi - lo < EPS:
                continue
            try:
                btw = between_of(rooms_occ, axis, at, [lo, hi])
            except Exception:
                btw = None
            pidx += 1
            passages.append({"id": "p%02d" % pidx, "kind": "passage",
                             "wall": {"axis": axis, "at": at,
                                      "span": [round(lo), round(hi)]},
                             "cut": True, "between": btw})

    openings = doors + sliding_ops + passages + windows

    G_final = {
        "meta": meta,
        "spaces": SPACES,
        "rooms": rooms_json,
        "openings": openings,
        "free_walls": FREE_WALLS,
        "annotations": [
            {"x": 255, "y": 335, "zh": "入户门", "en": "ENTRANCE", "style": "room"},
            {"x": 855, "y": 950, "zh": "客厅区", "en": "LIVING ROOM", "style": "room"},
        ],
        "dims": {"auto": True, "sides": ["top", "left"],
                 "offsets_px": {"top": 60, "left": 60, "right": 60, "bottom": 60},
                 "exclude_coords": [], "overrides": []},
    }

    with open(out, "w", encoding="utf-8") as fh:
        json.dump(G_final, fh, ensure_ascii=False, indent=2)

    print("写出:", out)
    print("rooms=%d spaces=%d doors=%d sliding=%d passages=%d windows=%d free_walls=%d"
          % (len(rooms_json), len(SPACES), len(doors), len(sliding_ops),
             len(passages), len(windows), len(FREE_WALLS)))
    rev = [d["id"] for d in doors if d.get("review")]
    print("review 门:", rev)
    print("passages:", [(p["wall"]["axis"], p["wall"]["at"], p["wall"]["span"]) for p in passages])
    return G_final


if __name__ == "__main__":
    build()
