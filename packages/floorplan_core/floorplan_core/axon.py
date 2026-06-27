# -*- coding: utf-8 -*-
"""
轴测引擎(户型无关·可复用)。
几何(墙/房间/窗)从精准平面SVG解析；家具从外部"家具方案表"传入，按类型查模型库渲染。
无任何硬编码手工层：类型显式、朝向来自数据。
用法见 户型-D户型.py。

家具方案表 FURNITURE：list[dict]，每件：
  {"t": 类型, "x":, "y":, "w":, "h":, "orient": "N|S|E|W"(可选), ...其它模型参数}
  坐标系同平面图：1px=10mm，原点 = 平面SVG 的 translate(150,250) 组内坐标。
支持类型见 MODELS。改/换家具 = 改这张表；新户型 = 换 SVG + 换这张表。
"""
import os, re, math

# ---------------- 投影 / 基础工具 ----------------
C, S = math.cos(math.radians(30)), math.sin(math.radians(30))
ZK = 0.1
WALL_H, T_EXT, T_INT, T_THIN, TILE = 1450.0, 24.0, 14.0, 6.0, 60.0
LOWZ_TOP = 110.0          # thin/public 墙在轴测只挤到此低高度 (D9, ≤120)
DOOR_WOOD = "#7a5a3c"     # 轴测门板木色
DOOR_T = 40.0            # 门板厚 (mm/px)
DOOR_OPEN = 0.55         # 半开比例 (×90°)

def proj(x, y, z=0.0): return ((x - y) * C, (x + y) * S - z * ZK)
def shade(h, f):
    if not h.startswith("#") or len(h) != 7: return h
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    q = lambda v: max(0, min(255, int(v * f)))
    return f"#{q(r):02x}{q(g):02x}{q(b):02x}"
def P(x, y, z): return "%.1f,%.1f" % proj(x, y, z)

# ---------------- 几何解析(只取 墙/房间/窗，不取家具) ----------------
def parse_geometry(svg_path):
    svg = open(svg_path, encoding="utf-8-sig").read()
    geo = svg.split('transform="translate(150, 250)"')[1].split('<g id="room_labels">')[0]
    rooms = [(m.group(1), *map(float, m.groups()[1:]))
             for m in re.finditer(r'<rect class="room-([a-z]+)" x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', geo)]
    walls = [(*map(float, m.groups()), False)
             for m in re.finditer(r'<line class="wall-thick" x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)"', geo)]
    walls += [(*map(float, m.groups()), False)
              for m in re.finditer(r'<line x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)" stroke="#1a1a1a"', geo)]
    pm = re.search(r'<path class="wall-thick" d="\s*([^"]+)"', geo)
    if pm:
        toks = pm.group(1).replace('\n', ' ').split(); i = 0; cur = None; pts = []
        while i < len(toks):
            c = toks[i]
            if c in ('M', 'L'): x, y = map(float, toks[i+1].split(',')); cur = (x, y); pts.append(cur); i += 2
            elif c == 'V': cur = (cur[0], float(toks[i+1])); pts.append(cur); i += 2
            elif c == 'H': cur = (float(toks[i+1]), cur[1]); pts.append(cur); i += 2
            elif c == 'Z': pts.append(pts[0]); i += 1
            else: i += 1
        walls += [(a[0], a[1], b[0], b[1], True) for a, b in zip(pts, pts[1:])]
    windows = []
    for m in re.finditer(r'<rect class="window"[^>]*?/>', geo):
        s = m.group(0)
        gx = re.search(r' x="(-?[\d.]+)"', s); gy = re.search(r' y="(-?[\d.]+)"', s)
        gw = re.search(r'width="([\d.]+)"', s); gh = re.search(r'height="([\d.]+)"', s)
        wt = re.search(r'data-wtype="(\w+)"', s)
        if gx and gy and gw and gh:
            windows.append((float(gx.group(1)), float(gy.group(1)), float(gw.group(1)), float(gh.group(1)),
                            wt.group(1) if wt else "normal"))
    return rooms, walls, windows

# ---------------- 数据驱动几何 (方案B: geometry.py 单一真源) ----------------
def walls_for_engine(walls):
    """把任意墙元组归一化为统一 7 元组 (ax,ay,bx,by,ext,style,lowz).

    legacy parse_geometry 产出 5 元组 (ax,ay,bx,by,ext) -> 补 style/lowz;
    geometry.derive 已是 7 元组, 原样返回 (finding24 防解包崩溃)."""
    out = []
    for w in walls:
        if len(w) >= 7:
            ax, ay, bx, by, ext, style, lowz = w[:7]
        elif len(w) == 5:
            ax, ay, bx, by, ext = w
            style, lowz = ("solid", False)
        else:
            raise ValueError("bad wall tuple len=%d: %r" % (len(w), w))
        out.append((ax, ay, bx, by, bool(ext), style or "solid", bool(lowz)))
    return out

def _rooms_from_G(G):
    """G.rooms -> 引擎房间元组 (type, x, y, w, h)."""
    return [(r["type"], *r["rect"]) for r in G["rooms"]]

def from_geometry(json_path):
    """读 geometry.json -> (rooms, walls, doors, windows, dims, annotations, G).

    经 geometry.load + derive 单一真源. walls 已是归一化 7 元组."""
    from . import geometry as gm
    G = gm.load(json_path)
    geo = gm.derive(G)
    return geom_bundle(G, geo)

def geom_bundle(G, geo):
    """由已 load 的 G + 已 derive 的 geo 组装渲染包 (供 build.py 复用 derive)."""
    rooms = _rooms_from_G(G)
    walls = walls_for_engine(geo["walls"])
    return rooms, walls, geo["doors"], geo["windows"], geo.get("dims", {}), G.get("annotations", [])

# ---------------- 绘制基元 ----------------
def faces(x0, y0, x1, y1, z0, z1, base, tf=1.04, ef=0.78, sf=0.62, oc="#00000014"):
    top = f'<polygon points="{P(x0,y0,z1)} {P(x1,y0,z1)} {P(x1,y1,z1)} {P(x0,y1,z1)}" fill="{shade(base,tf)}" stroke="{oc}" stroke-width="0.4"/>'
    east = f'<polygon points="{P(x1,y0,z0)} {P(x1,y1,z0)} {P(x1,y1,z1)} {P(x1,y0,z1)}" fill="{shade(base,ef)}" stroke="{oc}" stroke-width="0.4"/>'
    south = f'<polygon points="{P(x0,y1,z0)} {P(x1,y1,z0)} {P(x1,y1,z1)} {P(x0,y1,z1)}" fill="{shade(base,sf)}" stroke="{oc}" stroke-width="0.4"/>'
    return east + south + top
def edge(x0, y0, x1, y1, side, th, z0, z1, base):
    if side == 'N': return (x0, y0, x1, y0+th, z0, z1, base)
    if side == 'S': return (x0, y1-th, x1, y1, z0, z1, base)
    if side == 'W': return (x0, y0, x0+th, y1, z0, z1, base)
    return (x1-th, y0, x1, y1, z0, z1, base)
def top_poly(x0, y0, x1, y1, z, color, opacity=1.0):
    return f'<polygon points="{P(x0,y0,z)} {P(x1,y0,z)} {P(x1,y1,z)} {P(x0,y1,z)}" fill="{color}" opacity="{opacity}" stroke="#00000022" stroke-width="0.35"/>'

# ==================================================================
#  门 (§③):  2D 门弧/门扇  +  轴测半开门板。passage 不在 doors 列表内,天然不出门。
# ==================================================================
def _sweep_flag(hinge, jamb, open_tip):
    """叉积定 SVG arc sweep-flag (确定性). v1=jamb-hinge, v2=open_tip-hinge."""
    v1 = (jamb[0] - hinge[0], jamb[1] - hinge[1])
    v2 = (open_tip[0] - hinge[0], open_tip[1] - hinge[1])
    return 1 if (v1[0] * v2[1] - v1[1] * v2[0]) > 0 else 0

def door_svg_2d(d):
    """一扇门的 2D 平面 SVG: 平开=弧+扇; 推拉=错位板; passage 不到此 (无 leaf)."""
    if d.get("door_type") == "sliding":
        axis, at, span = d["axis"], d["at"], list(d["span"])
        n = max(1, d.get("panels", 2))
        seg = (span[1] - span[0]) / n
        bw = seg + 5
        out = []
        for i in range(n):
            off = at - 3 + i * 6
            x0 = span[0] + i * seg
            if axis == "h":
                out.append('<rect class="door-sliding" x="%.0f" y="%.0f" width="%.0f" height="5"/>'
                           % (x0, off, bw))
            else:
                out.append('<rect class="door-sliding" x="%.0f" y="%.0f" width="5" height="%.0f"/>'
                           % (off, x0, bw))
        return "".join(out)
    # swing
    hinge = d["hinge_pt"]; jamb = d["jamb_pt"]; tip = d["open_tip"]; w = d["width"]
    sw = _sweep_flag(hinge, jamb, tip)
    arc = ('<path class="door-arc" d="M %.0f %.0f A %.0f %.0f 0 0 %d %.0f %.0f"/>'
           % (jamb[0], jamb[1], w, w, sw, tip[0], tip[1]))
    leaf = ('<line class="door-leaf" x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f"/>'
            % (hinge[0], hinge[1], tip[0], tip[1]))
    return arc + " " + leaf

def _prism(corners, z0, z1, base, oc="#00000022"):
    """4 角平面四边形竖向挤出 (任意朝向): 4 侧面 + 顶面."""
    s = ""
    for i in range(4):
        a = corners[i]; b = corners[(i + 1) % 4]
        s += ('<polygon points="%s %s %s %s" fill="%s" stroke="%s" stroke-width="0.4"/>'
              % (P(a[0], a[1], z0), P(b[0], b[1], z0), P(b[0], b[1], z1), P(a[0], a[1], z1),
                 shade(base, 0.8), oc))
    s += ('<polygon points="%s %s %s %s" fill="%s" stroke="%s" stroke-width="0.4"/>'
          % (P(corners[0][0], corners[0][1], z1), P(corners[1][0], corners[1][1], z1),
             P(corners[2][0], corners[2][1], z1), P(corners[3][0], corners[3][1], z1),
             shade(base, 1.08), oc))
    return s

def _slab_corners(x0, y0, x1, y1, t):
    """沿 (x0,y0)->(x1,y1) 方向的厚度 t 薄板的 4 个平面角点."""
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1.0
    px, py = -dy / L * t / 2.0, dx / L * t / 2.0
    return [(x0 + px, y0 + py), (x1 + px, y1 + py), (x1 - px, y1 - py), (x0 - px, y0 - py)]

def door_axon(d):
    """一扇门的轴测竖板 + 深度键. 返回 (key, svg). passage 不在 doors 内.

    平开: 半开 (DOOR_OPEN×90°) 竖板 + 把手; 推拉: panels 块错位薄板."""
    DH = min(2050.0, WALL_H)
    if d.get("door_type") == "sliding":
        axis, at, span = d["axis"], d["at"], list(d["span"])
        n = max(1, d.get("panels", 2))
        seg = (span[1] - span[0]) / n
        svg = ""
        for i in range(n):
            off = at - 3 + i * 8
            s0 = span[0] + i * seg
            if axis == "h":
                c = _slab_corners(s0, off, s0 + seg + 5, off, DOOR_T * 0.6)
            else:
                c = _slab_corners(off, s0, off, s0 + seg + 5, DOOR_T * 0.6)
            svg += _prism(c, 0, DH, shade(DOOR_WOOD, 1.05))
        cx = (span[0] + span[1]) / 2.0
        key = (cx + at) if axis == "h" else (at + cx)
        return key, svg
    # swing: 半开竖板
    hx, hy = d["hinge_pt"]; jx, jy = d["jamb_pt"]; ox, oy = d["open_tip"]; w = d["width"]
    ucx, ucy = (jx - hx) / w, (jy - hy) / w
    uox, uoy = (ox - hx) / w, (oy - hy) / w
    th = DOOR_OPEN * (math.pi / 2.0)
    ct, st = math.cos(th), math.sin(th)
    tipx = hx + w * (ct * ucx + st * uox)
    tipy = hy + w * (ct * ucy + st * uoy)
    corners = _slab_corners(hx, hy, tipx, tipy, DOOR_T)
    svg = _prism(corners, 0, DH, DOOR_WOOD)
    knob = proj((hx + tipx) / 2.0 + (tipx - hx) * 0.3, (hy + tipy) / 2.0 + (tipy - hy) * 0.3, 760)
    svg += '<circle cx="%.1f" cy="%.1f" r="3.5" fill="#c2a36b"/>' % (knob[0], knob[1])
    cx, cy = (hx + tipx) / 2.0, (hy + tipy) / 2.0
    return cx + cy, svg

# ==================================================================
#  家具模型库  MODELS：类型 -> 函数(it)->(boxes, extra_svg)
#  it = 家具dict；boxes = [(x0,y0,x1,y1,z0,z1,color),...]；extra_svg 叠加在顶层
# ==================================================================
WOOD_D, WOOD = "#5a4332", "#8a633e"
def _xy(it): return it["x"], it["y"], it["x"]+it["w"], it["y"]+it["h"], it.get("orient", "N")

def m_bed(it):
    x0, y0, x1, y1, side = _xy(it); base = it.get("color", "#d8c9ad")
    bx = [(x0, y0, x1, y1, 0, 300, WOOD_D),
          (x0+30, y0+30, x1-30, y1-30, 300, 430, "#f3ece0"),
          (x0+30, y0+30, x1-30, y1-30, 430, 480, base),
          edge(x0, y0, x1, y1, side, 70, 0, 980, WOOD_D)]
    w, h = x1-x0, y1-y0
    if side in ('N', 'S'):
        yy = y0+90 if side == 'N' else y1-160
        bx += [(x0+w*0.12, yy, x0+w*0.46, yy+90, 470, 600, "#fffaf0"),
               (x0+w*0.54, yy, x0+w*0.88, yy+90, 470, 600, "#fffaf0")]
    else:
        xx = x0+90 if side == 'W' else x1-160
        bx += [(xx, y0+h*0.12, xx+90, y0+h*0.46, 470, 600, "#fffaf0"),
               (xx, y0+h*0.54, xx+90, y0+h*0.88, 470, 600, "#fffaf0")]
    return bx, ""
def m_sofa(it):
    x0, y0, x1, y1, side = _xy(it); base = it.get("color", "#b07a4e")
    bx = [(x0, y0, x1, y1, 0, 340, shade(base, 0.85))]
    ai = 90
    if side in ('N', 'S'):
        bx.append((x0+ai, y0+ai if side != 'S' else y0, x1-ai, y1 if side != 'S' else y1-ai, 340, 470, shade(base, 1.05)))
        bx += [(x0, y0, x0+70, y1, 0, 560, shade(base, 0.75)), (x1-70, y0, x1, y1, 0, 560, shade(base, 0.75))]
    else:
        bx.append((x0+ai if side != 'E' else x0, y0+ai, x1 if side != 'E' else x1-ai, y1-ai, 340, 470, shade(base, 1.05)))
        bx += [(x0, y0, x1, y0+70, 0, 560, shade(base, 0.75)), (x0, y1-70, x1, y1, 0, 560, shade(base, 0.75))]
    bx.append(edge(x0, y0, x1, y1, side, 90, 0, 760, shade(base, 0.8)))
    return bx, ""
def m_chaise(it):
    x0, y0, x1, y1, side = _xy(it); base = it.get("color", "#3d5440")
    bx = [(x0, y0, x1, y1, 0, 400, base)]
    bx.append(edge(x0, y0, x1, y1, {'E':'W','W':'E','N':'S','S':'N'}[side], 33, 400, 780, shade(base, 0.82)))  # 靠背在朝向的反侧
    return bx, top_poly(x0+10, y0+10, x1-10, y1-10, 405, shade(base, 1.12), 0.95)
def m_legs_top(it, th, ttop, base, leg=None):
    x0, y0, x1, y1, _ = _xy(it); leg = leg or shade(base, 0.7); lg = 60
    return [(x0, y0, x0+lg, y0+lg, 0, ttop-th, leg), (x1-lg, y0, x1, y0+lg, 0, ttop-th, leg),
            (x0, y1-lg, x0+lg, y1, 0, ttop-th, leg), (x1-lg, y1-lg, x1, y1, 0, ttop-th, leg),
            (x0, y0, x1, y1, ttop-th, ttop, base)], ""
def m_coffee(it): return m_legs_top(it, 45, 420, "#d8c9ad", leg="#5a4332")
def m_desk(it): return m_legs_top(it, 45, 750, "#8a633e")
def m_dining(it):
    x0, y0, x1, y1, _ = _xy(it); w, h = x1-x0, y1-y0
    boxes, _ = m_legs_top(it, 50, 750, WOOD)
    per = max(1, it.get("seats", 8)//2)
    for i in range(per):
        if w >= h:   # 长轴沿x：椅分南北两排
            cxc = x0 + w*(i+0.5)/per
            boxes += m_chair({"x": cxc-22, "y": y0-46, "w": 44, "h": 40, "orient": "N", "backh": 720})[0]
            boxes += m_chair({"x": cxc-22, "y": y1+6,  "w": 44, "h": 40, "orient": "S", "backh": 720})[0]
        else:        # 长轴沿y：椅分东西两侧
            cyc = y0 + h*(i+0.5)/per
            boxes += m_chair({"x": x0-46, "y": cyc-22, "w": 40, "h": 44, "orient": "W", "backh": 720})[0]
            boxes += m_chair({"x": x1+6,  "y": cyc-22, "w": 40, "h": 44, "orient": "E", "backh": 720})[0]
    extra = ""
    for lx in (x0+w*0.35, (x0+x1)/2, x0+w*0.65):
        px, py = proj(lx, (y0+y1)/2, 1280)
        extra += f'<circle cx="{px:.1f}" cy="{py:.1f}" r="9" fill="#ffd98a" opacity="0.72" filter="url(#glow)"/>'
    return boxes, extra
def m_chair(it):
    x0, y0, x1, y1, side = _xy(it); base = it.get("color", "#d8c9ad"); backh = it.get("backh", 760)
    boxes, _ = m_legs_top(it, 55, 450, base)
    boxes += [(x0+25, y0+25, x1-25, y1-25, 450, 510, shade(base, 1.08)),
              edge(x0, y0, x1, y1, side, 42, 450, backh, shade(base, 0.82))]
    return boxes, ""
def m_swivel(it):  # 墨绿丝绒旋转椅
    x0, y0, x1, y1, side = _xy(it)
    return m_chair({**it, "color": "#3d5440", "backh": 820, "orient": side})
def m_cab(it):     # 通用柜(矮)
    x0, y0, x1, y1, _ = _xy(it)
    return [(x0, y0, x1, y1, 0, it.get("z", 820), it.get("color", "#8a633e"))], ""
def m_tall(it):    # 高柜/衣柜/书柜/冰箱
    x0, y0, x1, y1, _ = _xy(it)
    return [(x0, y0, x1, y1, 0, it.get("z", 2000), it.get("color", "#846752"))], ""
def m_media(it):
    x0, y0, x1, y1, _ = _xy(it)
    p1, p2 = proj(x0+(x1-x0)*0.15, (y0+y1)/2, 900), proj(x0+(x1-x0)*0.85, (y0+y1)/2, 900)
    glow = f'<line x1="{p1[0]:.1f}" y1="{p1[1]:.1f}" x2="{p2[0]:.1f}" y2="{p2[1]:.1f}" stroke="#ffdda0" stroke-width="5" opacity="0.42" filter="url(#glow)"/>'
    return [(x0, y0, x1, y1, 0, 520, "#5a4332")], glow
def m_island(it):
    x0, y0, x1, y1, _ = _xy(it)
    return [(x0, y0, x1, y1, 0, 880, "#5a4332"), (x0-15, y0-15, x1+15, y1+15, 880, 920, "#d9d0bf")], ""
def m_kitchen(it):  # 厨房台面 + 灶 + 水槽 (L由两件拼)
    x0, y0, x1, y1, _ = _xy(it)
    boxes = [(x0, y0, x1, y1, 0, 860, "#d9d0bf")]
    extra = ""
    if it.get("hob"):   extra += top_poly(x0+(x1-x0)*0.30, y0+8, x0+(x1-x0)*0.55, y1-8, 868, "#1f1f1f", 0.9)
    if it.get("sink"):  extra += top_poly(x0+(x1-x0)*0.62, y0+8, x0+(x1-x0)*0.92, y1-8, 868, "#b8d7e4", 0.85)
    return boxes, extra
def m_washer(it):   # 洗烘一体塔 + 圆舱门
    x0, y0, x1, y1, _ = _xy(it)
    extra = ""
    for zc in (470, 1160):
        p = proj((x0+x1)/2, y1, zc)
        extra += f'<circle cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="12" fill="#9fb6c4" stroke="#6f8a99" stroke-width="2"/>'
    return [(x0, y0, x1, y1, 0, it.get("z", 1820), "#ededee")], extra
def m_vanity(it):
    x0, y0, x1, y1, _ = _xy(it)
    return [(x0, y0, x1, y1, 0, 760, "#6a6d74"), (x0, y0, x1, y1, 760, 830, "#a8875a")], \
           top_poly(x0+12, y0+8, x1-12, y1-8, 838, "#b8d7e4", 0.85)
def m_toilet(it):
    x0, y0, x1, y1, _ = _xy(it); cy = (y0+y1)/2
    return [(x0+10, y0+10, x1-10, cy+15, 0, 400, "#eef2f5"), (x0+20, cy-5, x1-20, y1-10, 0, 600, "#e3eaef")], ""
def m_tub(it):
    x0, y0, x1, y1, _ = _xy(it)
    return [(x0, y0, x1, y1, 0, 560, "#e7edf1"), (x0+25, y0+25, x1-25, y1-25, 300, 540, "#cdd9e2")], ""
def m_shower(it):
    x0, y0, x1, y1, _ = _xy(it)
    extra = (f'<polygon points="{P(x0,y0,0)} {P(x1,y0,0)} {P(x1,y0,1900)} {P(x0,y0,1900)}" fill="#bcd6e388" stroke="#9bb8c8" stroke-width="1"/>'
             f'<polygon points="{P(x1,y0,0)} {P(x1,y1,0)} {P(x1,y1,1900)} {P(x1,y0,1900)}" fill="#aac7d77a" stroke="#9bb8c8" stroke-width="1"/>')
    return [(x0, y0, x1, y1, 0, 120, "#cdd9e0")], extra
def m_entry_door(it):  # 入户门：墙里一扇深色门 + 门把手
    x0, y0, x1, y1, _ = _xy(it)
    knob = proj((x0+x1)/2+3, (y0+y1)/2, 760)
    return [(x0, y0, x1, y1, 0, WALL_H, "#433d37")], f'<circle cx="{knob[0]:.1f}" cy="{knob[1]:.1f}" r="3.5" fill="#c2a36b"/>'
def m_partition(it):   # 补强隔墙(防止AI合并房间)
    x0, y0, x1, y1, _ = _xy(it)
    return [(x0, y0, x1, y1, 0, WALL_H + 40, "#ddd6c8")], ""

MODELS = {
    "bed": m_bed, "sofa": m_sofa, "chaise": m_chaise, "coffee_table": m_coffee, "desk": m_desk,
    "dining_table": m_dining, "chair": m_chair, "swivel_chair": m_swivel, "cabinet": m_cab,
    "nightstand": lambda it: m_cab({**it, "z": it.get("z", 470), "color": it.get("color", "#8a633e")}),
    "tall_cabinet": m_tall, "wardrobe": m_tall, "bookshelf": m_tall, "fridge": m_tall,
    "media": m_media, "island": m_island, "kitchen": m_kitchen, "washer_dryer": m_washer,
    "vanity": m_vanity, "toilet": m_toilet, "tub": m_tub, "shower": m_shower,
    "entry_door": m_entry_door, "partition": m_partition,
    "bench": lambda it: m_cab({**it, "z": it.get("z", 430), "color": it.get("color", "#b07a4e")}),
}

# ---------------- 圆形家具(植物/圆桌/圆椅) ----------------
def draw_round(it, emit, shadow):
    cx, cy, r = it["cx"], it["cy"], it["r"]; t = it["t"]
    shadow(cx-r, cy-r, cx+r, cy+r, cx, cy)
    if t == "plant":
        bx0, by0 = proj(cx, cy, 0)
        emit(cx+cy+5, faces(cx-r*0.55, cy-r*0.55, cx+r*0.55, cy+r*0.55, 0, 360, "#8f7b5c"))
        tx, ty2 = proj(cx, cy, 360)
        emit(cx+cy+6, f'<ellipse cx="{tx:.1f}" cy="{ty2-26:.1f}" rx="{r*1.5:.1f}" ry="{r*0.95:.1f}" fill="#6f9466"/>'
                      f'<ellipse cx="{tx-r*0.5:.1f}" cy="{ty2-46:.1f}" rx="{r*0.9:.1f}" ry="{r*0.6:.1f}" fill="#7fa676"/>')
    else:
        h = 430 if t == "round_table" else 450
        base = "#e1d3b4" if t == "round_table" else "#3d5440"
        bx0, by0 = proj(cx, cy, 0); tx, tyo = proj(cx, cy, h); rx, ry = r*2*C, r*2*S*0.62
        emit(cx+cy+5, f'<ellipse cx="{bx0:.1f}" cy="{by0:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{shade(base,0.72)}"/>'
                      f'<rect x="{bx0-rx:.1f}" y="{tyo:.1f}" width="{2*rx:.1f}" height="{by0-tyo:.1f}" fill="{shade(base,0.72)}"/>'
                      f'<ellipse cx="{tx:.1f}" cy="{tyo:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{base}" stroke="#0000001a" stroke-width="0.5"/>')

# ---------------- 主渲染 ----------------
FLOOR = {"living": ("url(#travertine)", "#d8c7a7", "stone"), "bedroom": ("url(#oak)", "#a47a56", "wood"),
         "wet": ("url(#microcement)", "#aeb2b5", "tile"), "outdoor": ("url(#gardenfloor)", "#c8d2c1", "tile"),
         "corridor": ("url(#travertine)", "#d8c7a7", "stone"), "public": ("url(#publicgrey)", "#d4d4d4", "tile")}
FLAT = {"living": "#ece0c6", "bedroom": "#e7d6ba", "wet": "#d7e2e9", "outdoor": "#dfe7d8",
        "corridor": "#e6e0d4", "public": "#dedede"}

DEFS = '''<defs>
<filter id="sh" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="7"/></filter>
<filter id="glow" x="-120%" y="-120%" width="340%" height="340%"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f7f3ea"/><stop offset="1" stop-color="#e8e1d3"/></linearGradient>
<pattern id="travertine" width="120" height="120" patternUnits="userSpaceOnUse"><rect width="120" height="120" fill="#d8c7a7"/><path d="M6 28 C34 20 55 37 115 23 M12 72 C45 84 82 54 118 74 M0 106 C30 96 73 112 120 98" stroke="#c4ad89" stroke-width="1.3" opacity="0.32" fill="none"/><path d="M32 0 L28 120 M88 0 L94 120" stroke="#eadfc9" stroke-width="1" opacity="0.35"/></pattern>
<pattern id="oak" width="90" height="90" patternUnits="userSpaceOnUse"><rect width="90" height="90" fill="#a47a56"/><path d="M12 0 L18 90 M44 0 L38 90 M75 0 L79 90" stroke="#6f4f38" stroke-width="1.4" opacity="0.35"/><path d="M0 22 C25 14 44 30 90 20 M0 62 C28 70 52 50 90 62" stroke="#c1966c" stroke-width="1" opacity="0.42" fill="none"/></pattern>
<pattern id="microcement" width="110" height="110" patternUnits="userSpaceOnUse"><rect width="110" height="110" fill="#aeb2b5"/><path d="M0 35 C30 20 73 45 110 28 M0 88 C42 76 72 101 110 82" stroke="#8e9499" stroke-width="1.2" opacity="0.25" fill="none"/></pattern>
<pattern id="gardenfloor" width="100" height="100" patternUnits="userSpaceOnUse"><rect width="100" height="100" fill="#c8d2c1"/><path d="M0 50 H100 M50 0 V100" stroke="#aebaa8" stroke-width="1" opacity="0.38"/></pattern>
<pattern id="publicgrey" width="100" height="100" patternUnits="userSpaceOnUse"><rect width="100" height="100" fill="#d4d4d4"/><path d="M0 50 H100 M50 0 V100" stroke="#bcbcbc" stroke-width="1" opacity="0.35"/></pattern>
</defs>'''

# ==================================================================
#  2D 俯视平面渲染(同一张 FURNITURE 表 → 2D 家具层)，实现 平面+轴测 同源
# ==================================================================
CAT2D = {  # 类型 -> (fill, stroke)
    "bed": ("#e3c9a6", "#b78f5e"), "sofa": ("#d8c19c", "#a9895c"), "chaise": ("#cdd9e0", "#7a93a0"),
    "chair": ("#cfe0d4", "#7fa088"), "swivel_chair": ("#cfe0d4", "#7fa088"),
    "coffee_table": ("#e7d9bb", "#b9ad8a"), "island": ("#e7d9bb", "#b9ad8a"),
    "round_table": ("#e7d9bb", "#b9ad8a"), "nightstand": ("#ece0c8", "#b9a274"),
    "cabinet": ("#ece0c8", "#b9a274"), "tall_cabinet": ("#ece0c8", "#b9a274"),
    "wardrobe": ("#cdb18f", "#a9895c"), "bookshelf": ("#ece0c8", "#b9a274"),
    "desk": ("#ece0c8", "#b9a274"), "bench": ("#ece0c8", "#b9a274"), "dining_table": ("#ece0c8", "#b9a274"),
    "kitchen": ("#ece0c8", "#b9a274"), "fridge": ("#cdb18f", "#8a6a44"), "media": ("#cdb18f", "#8a6a44"),
    "washer_dryer": ("#ece0c8", "#b9a274"), "vanity": ("#dde7ec", "#8aa6b4"), "toilet": ("#dde7ec", "#8aa6b4"),
    "tub": ("#dde7ec", "#8aa6b4"), "shower": ("#dde7ec", "#8aa6b4"), "plant": ("#cfe0cf", "#6b8a6b"),
}
NAME2D = {"bed": "双人床", "sofa": "沙发", "chaise": "贵妃榻", "dining_table": "餐桌", "coffee_table": "茶几",
          "desk": "书桌", "island": "中岛", "wardrobe": "衣柜", "bookshelf": "书柜", "fridge": "冰箱",
          "media": "影视柜", "kitchen": "橱柜", "washer_dryer": "洗烘", "vanity": "台盆", "toilet": "马桶",
          "tub": "浴缸", "shower": "淋浴", "swivel_chair": "旋转椅", "island ": "中岛"}
def _t2d(x, y, s):
    return f'<text x="{x:.0f}" y="{y:.0f}" font-family="Microsoft YaHei,PingFang SC,sans-serif" font-size="10" fill="#5a4a33" text-anchor="middle" dominant-baseline="middle">{s}</text>'
STYLE_2D = '''  <defs>
    <style>
      .bg { fill: #ffffff; }
      .wall-thick { stroke: #1a1a1a; stroke-width: 7; stroke-linecap: round; stroke-linejoin: round; fill: none; }
      .wall-thin { stroke: #555555; stroke-width: 3; fill: none; }
      .wall-public { stroke: #b0b0b0; stroke-width: 3; stroke-dasharray: 4,4; fill: none; }
      .room-bedroom { fill: #fbfbfb; stroke: #d0d0d0; stroke-width: 1; }
      .room-living { fill: #fcfdfd; stroke: #d0d0d0; stroke-width: 1; }
      .room-wet { fill: #f5f6f7; stroke: #d0d0d0; stroke-width: 1; }
      .room-outdoor { fill: #f7f5f2; stroke: #d0d0d0; stroke-width: 1; }
      .room-corridor { fill: #fafafa; stroke: #d0d0d0; stroke-width: 1; }
      .room-public { fill: #f0f0f0; stroke: #e0e0e0; stroke-width: 1; }
      .window { stroke: #6ba4c7; stroke-width: 5; fill: #eef7fc; }
      .door-leaf { stroke: #b5845c; stroke-width: 4; stroke-linecap: round; fill: none; }
      .door-arc { stroke: #b5845c; stroke-width: 2; stroke-dasharray: 4,4; fill: none; }
      .door-sliding { fill: #6ba4c7; stroke: #4a7b9d; stroke-width: 1; }
      .zh-label { font-family: "Microsoft YaHei", "SimHei", "PingFang SC", sans-serif; font-size: 24px; font-weight: bold; fill: #000000; text-anchor: middle; dominant-baseline: middle; }
      .zh-label-public { font-family: "Microsoft YaHei", "SimHei", "PingFang SC", sans-serif; font-size: 20px; font-weight: normal; fill: #888888; text-anchor: middle; dominant-baseline: middle; }
      .en-label { font-family: Arial, sans-serif; font-size: 14px; font-weight: normal; fill: #444444; text-anchor: middle; dominant-baseline: middle; }
      .dim-line { stroke: #776e65; stroke-width: 1.5; }
      .dim-tick { stroke: #443f3a; stroke-width: 2.5; }
      .dim-text { font-family: Arial, sans-serif; font-size: 16px; font-weight: bold; fill: #222222; text-anchor: middle; dominant-baseline: middle; }
    </style>
  </defs>'''

def _wall_class_2d(style):
    if style == "thin": return "wall-thin"
    if style in ("dashed", "public"): return "wall-public"
    return "wall-thick"

def _dims_2d(dims, mm):
    """尺寸链 SVG: 顶链 translate(0,-50) 横向; 左链 translate(-60,0) 竖向。保留尺寸线。"""
    out = []
    top = dims.get("top", [])
    left = dims.get("left", [])
    if len(top) >= 2:
        g = ['<g transform="translate(0, -50)">']
        for a, b in zip(top, top[1:]):
            g.append('<line class="dim-line" x1="%g" y1="0" x2="%g" y2="0"/>' % (a, b))
            g.append('<line class="dim-tick" x1="%g" y1="-6" x2="%g" y2="6"/>' % (a, a))
            g.append('<text class="dim-text" x="%g" y="-15">%d</text>' % ((a + b) / 2.0, round((b - a) * mm)))
        g.append('<line class="dim-tick" x1="%g" y1="-6" x2="%g" y2="6"/>' % (top[-1], top[-1]))
        g.append('</g>')
        out.append("\n".join(g))
    if len(left) >= 2:
        g = ['<g transform="translate(-60, 0)">']
        for a, b in zip(left, left[1:]):
            mid = (a + b) / 2.0
            g.append('<line class="dim-line" x1="0" y1="%g" x2="0" y2="%g"/>' % (a, b))
            g.append('<line class="dim-tick" x1="-6" y1="%g" x2="6" y2="%g"/>' % (a, a))
            g.append('<text class="dim-text" x="-25" y="%g" transform="rotate(-90 -25 %g)">%d</text>'
                     % (mid, mid, round((b - a) * mm)))
        g.append('<line class="dim-tick" x1="-6" y1="%g" x2="6" y2="%g"/>' % (left[-1], left[-1]))
        g.append('</g>')
        out.append("\n".join(g))
    return out

def render_plan_2d(G, geo, furniture, out_path):
    """2D 平面全量数据重绘 (不再 string-replace): 房间→墙→窗→门→房名→尺寸链→家具层。
    G=geometry.load 结果; geo=geometry.derive 结果。"""
    mm = G.get("meta", {}).get("mm_per_px", 10)
    vb = G.get("meta", {}).get("canvas_viewbox", [0, 0, 2200, 1800])
    ox, oy = G.get("meta", {}).get("origin", [150, 250])

    # 房间地面色块
    R = []
    for r in G["rooms"]:
        x, y, w, h = r["rect"]
        R.append('<rect class="room-%s" x="%g" y="%g" width="%g" height="%g"/>' % (r["type"], x, y, w, h))
    # 墙 (thick/thin/dashed 按 style; 门洞已在 derive 断开)
    W = []
    for (ax, ay, bx, by, ext, style, lowz) in geo["walls"]:
        W.append('<line class="%s" x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f"/>'
                 % (_wall_class_2d(style), ax, ay, bx, by))
    # 窗 (.window + data-wtype)
    WN = []
    for win in geo["windows"]:
        axis, at, span = win["axis"], win["at"], win["span"]
        ln = span[1] - span[0]
        if axis == "h":
            WN.append('<rect class="window" data-wtype="%s" x="%g" y="%g" width="%g" height="10"/>'
                      % (win["wtype"], span[0], at - 5, ln))
        else:
            WN.append('<rect class="window" data-wtype="%s" x="%g" y="%g" width="10" height="%g"/>'
                      % (win["wtype"], at - 5, span[0], ln))
    # 门弧/扇 (passage 不在 doors 列表内)
    D = [door_svg_2d(d) for d in geo["doors"]]
    # 房名 (rooms.label) + annotations
    L = []
    for r in G["rooms"]:
        lb = r.get("label")
        if not lb:
            continue
        x, y, w, h = r["rect"]
        at = lb.get("at", [x + w / 2.0, y + h / 2.0])
        cls = "zh-label-public" if lb.get("style") == "public" else "zh-label"
        if lb.get("zh"):
            L.append('<text class="%s" x="%g" y="%g">%s</text>' % (cls, at[0], at[1], lb["zh"]))
        if lb.get("en") and cls == "zh-label":
            L.append('<text class="en-label" x="%g" y="%g">%s</text>' % (at[0], at[1] + 28, lb["en"]))
    for a in G.get("annotations", []):
        if a.get("zh"):
            L.append('<text class="zh-label" x="%g" y="%g">%s</text>' % (a["x"], a["y"], a["zh"]))
        if a.get("en"):
            L.append('<text class="en-label" x="%g" y="%g">%s</text>' % (a["x"], a["y"] + 28, a["en"]))
    # 尺寸链
    DIM = _dims_2d(geo.get("dims", {}), mm)

    # 家具层 (沿用 furniture-D户型.json, 家具模型不变)
    F = []
    for it in furniture:
        t = it["t"]
        if t in ("entry_door", "partition"): continue
        if t == "rug":
            F.append(f'<rect x="{it["x"]}" y="{it["y"]}" width="{it["w"]}" height="{it["h"]}" fill="none" stroke="#c9bb96" stroke-width="1" stroke-dasharray="6,4"/>'); continue
        if t in ("plant", "round_table", "round_chair"):
            fill, st = CAT2D.get(t, ("#e7d9bb", "#b9ad8a"))
            F.append(f'<circle cx="{it["cx"]}" cy="{it["cy"]}" r="{it["r"]}" fill="{fill}" stroke="{st}" stroke-width="1.2"/>'); continue
        x, y, w, h = it["x"], it["y"], it["w"], it["h"]; fill, st = CAT2D.get(t, ("#ece0c8", "#b9a274"))
        F.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{fill}" stroke="{st}" stroke-width="1.2"/>')
        if t == "dining_table":   # 餐椅
            per = max(1, it.get("seats", 8)//2)
            for i in range(per):
                if w >= h:
                    cxc = x + w*(i+0.5)/per
                    F.append(f'<rect x="{cxc-22:.0f}" y="{y-26:.0f}" width="44" height="20" rx="2" fill="#cfe0d4" stroke="#7fa088" stroke-width="1.2"/>')
                    F.append(f'<rect x="{cxc-22:.0f}" y="{y+h+6:.0f}" width="44" height="20" rx="2" fill="#cfe0d4" stroke="#7fa088" stroke-width="1.2"/>')
                else:
                    cyc = y + h*(i+0.5)/per
                    F.append(f'<rect x="{x-26:.0f}" y="{cyc-22:.0f}" width="20" height="44" rx="2" fill="#cfe0d4" stroke="#7fa088" stroke-width="1.2"/>')
                    F.append(f'<rect x="{x+w+6:.0f}" y="{cyc-22:.0f}" width="20" height="44" rx="2" fill="#cfe0d4" stroke="#7fa088" stroke-width="1.2"/>')
        label = it["label"] if "label" in it else NAME2D.get(t)   # "label":"" 可显式不显示
        if label and max(w, h) >= 40:
            F.append(_t2d(x+w/2, y+h/2, label))
    out = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="%g %g %g %g" width="100%%" height="100%%">'
        % (vb[0], vb[1], vb[2], vb[3]),
        STYLE_2D,
        '<rect class="bg" x="%g" y="%g" width="%g" height="%g"/>' % (vb[0], vb[1], vb[2], vb[3]),
        '<g transform="translate(%g, %g)">' % (ox, oy),
        '<g id="rooms">\n' + "\n".join(R) + '\n</g>',
        '<g id="walls">\n' + "\n".join(W) + '\n</g>',
        '<g id="windows">\n' + "\n".join(WN) + '\n</g>',
        '<g id="doors">\n' + "\n".join(D) + '\n</g>',
        '<g id="dims">\n' + "\n".join(DIM) + '\n</g>',
        '<g id="furniture-layer">\n' + "\n".join(F) + '\n</g>',
        '<g id="room_labels">\n' + "\n".join(L) + '\n</g>',
        '</g>',
        '</svg>',
    ]
    open(out_path, "w", encoding="utf-8-sig").write("\n".join(out))
    print(f"wrote {out_path} | 2D-plan rooms={len(G['rooms'])} walls={len(W)} doors={len(D)} win={len(WN)} furn={len(furniture)}")

def render(geom, furniture, out_path, mode="photo"):
    """数据驱动轴测渲染. geom = (rooms, walls, doors, windows, dims, annotations)
    来自 from_geometry / geom_bundle (geometry.py 单一真源).
    mode: photo(纹理+家具) / shell(纹理+无家具) / flat(扁平色+家具)"""
    rooms, walls, doors, windows = geom[0], geom[1], geom[2], geom[3]
    walls = walls_for_engine(walls)
    textures = mode in ("photo", "shell"); show_furn = mode in ("photo", "flat")
    draws = []
    def emit(k, s): draws.append((k, s))
    def shadow(x0, y0, x1, y1, cx, cy):
        o = 35
        emit(cx+cy+4, f'<polygon points="{P(x0+o,y0+o,0)} {P(x1+o,y0+o,0)} {P(x1+o,y1+o,0)} {P(x0+o,y1+o,0)}" fill="#00000022" filter="url(#sh)"/>')
    def piece(boxes, cx, cy, extra=""):
        bs = sorted(boxes, key=lambda b: (b[0]+b[2])/2 + (b[1]+b[3])/2 + b[5]*0.02)
        emit(cx+cy+5, "".join(faces(*b) for b in bs) + extra)

    # 地面
    for t, x, y, w, h in rooms:
        if textures: fill, col, kind = FLOOR.get(t, ("#e0e0e0", "#e0e0e0", "tile"))
        else: fill, col, kind = FLAT.get(t, "#e0e0e0"), FLAT.get(t, "#e0e0e0"), "none"
        emit(-1e9, f'<polygon points="{P(x,y,0)} {P(x+w,y,0)} {P(x+w,y+h,0)} {P(x,y+h,0)}" fill="{fill}" stroke="#bfae8e" stroke-width="0.45"/>')
        if kind in ("wood", "stone", "tile"):
            step = 90 if kind == "wood" else (300 if kind == "stone" else 180); lc = shade(col, 0.78)
            xx = x + step
            while xx < x + w:
                a, b = proj(xx, y), proj(xx, y+h)
                emit(-9e8, f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" stroke="{lc}" stroke-width="0.5" opacity="0.4"/>')
                xx += step
            if kind != "wood":
                yy = y + step
                while yy < y + h:
                    a, b = proj(x, yy), proj(x+w, yy)
                    emit(-9e8, f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" stroke="{lc}" stroke-width="0.5" opacity="0.32"/>')
                    yy += step

    # 墙(切块·局部深度键·无描边无接缝)。lowz(thin/public) 不挤整高 (D9)。
    for ax, ay, bx, by, ext, style, lowz in walls:
        T = T_EXT if ext else (T_THIN if style == "thin" else T_INT)
        horiz = abs(ay-by) < abs(ax-bx)
        lo, hi, fx = (min(ax, bx), max(ax, bx), ay) if horiz else (min(ay, by), max(ay, by), ax)
        z_top = LOWZ_TOP if lowz else WALL_H
        wcol = "#cfcabf" if lowz else "#ddd6c8"
        n = max(1, int(round((hi-lo)/TILE))); step = (hi-lo)/n
        for i in range(n):
            s0, s1 = lo+i*step, lo+(i+1)*step
            if horiz: x0, x1, y0, y1 = s0, s1, fx-T/2, fx+T/2
            else: y0, y1, x0, x1 = s0, s1, fx-T/2, fx+T/2
            emit((x0+x1)/2+(y0+y1)/2, faces(x0, y0, x1, y1, 0, z_top, wcol, tf=1.08, ef=0.82, sf=0.68, oc="none"))

    # 门(轴测半开门板;passage 不在 doors 列表内,天然不出板)
    for d in doors:
        k, s = door_axon(d)
        emit(k, s)

    # 家具(来自数据表，按类型查模型)
    if show_furn:
        for it in furniture:
            t = it["t"]
            if t in ("plant", "round_table", "round_chair"):
                draw_round(it, emit, shadow); continue
            if t == "rug":
                x0, y0 = it["x"], it["y"]; emit(-8e8, faces(x0, y0, x0+it["w"], y0+it["h"], 0, 8, it.get("color", "#b8ad9a"), tf=1.05, ef=0.72, sf=0.58, oc="#00000010")); continue
            fn = MODELS.get(t)
            if not fn: continue
            boxes, extra = fn(it)
            cx, cy = it["x"]+it["w"]/2, it["y"]+it["h"]/2
            if t not in ("shower", "entry_door", "partition"): shadow(it["x"], it["y"], it["x"]+it["w"], it["y"]+it["h"], cx, cy)
            piece(boxes, cx, cy, extra)

    # 窗(derive 数据;南墙强制落地；按 wtype 出窗高；深度=最近角)
    SILL = {"full": 0, "normal": 750, "high": 1100}
    for win in windows:
        axis, at, span, wt = win["axis"], win["at"], list(win["span"]), win["wtype"]
        a, b = ((span[0], at), (span[1], at)) if axis == "h" else ((at, span[0]), (at, span[1]))
        if axis == "h" and at >= 1390: wt = "full"      # 南墙满窗
        z0 = SILL.get(wt, 750); z1 = WALL_H + 30
        g = f'<polygon points="{P(a[0],a[1],z0)} {P(b[0],b[1],z0)} {P(b[0],b[1],z1)} {P(a[0],a[1],z1)}" fill="#bfe0f088" stroke="#7fa6bc" stroke-width="1.6"/>'
        for fr in (0.33, 0.66):
            mx, my = a[0]+(b[0]-a[0])*fr, a[1]+(b[1]-a[1])*fr
            p1, p2 = P(mx, my, z0), P(mx, my, z1)
            g += f'<line x1="{p1.split(",")[0]}" y1="{p1.split(",")[1]}" x2="{p2.split(",")[0]}" y2="{p2.split(",")[1]}" stroke="#7fa6bc" stroke-width="1"/>'
        emit(max(a[0], b[0]) + max(a[1], b[1]) + 1, g)

    # 画布 + 输出
    draws.sort(key=lambda d: d[0])
    allx, ally = [], []
    for t, x, y, w, h in rooms:
        for X, Y in [(x, y), (x+w, y), (x, y+h), (x+w, y+h)]:
            for z in (0, WALL_H):
                p = proj(X, Y, z); allx.append(p[0]); ally.append(p[1])
    minx, maxx, miny, maxy = min(allx)-220, max(allx)+220, min(ally)-340, max(ally)+220
    W, Ht = maxx-minx, maxy-miny
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx:.0f} {miny:.0f} {W:.0f} {Ht:.0f}" width="2000">', DEFS,
           f'<rect x="{minx:.0f}" y="{miny:.0f}" width="{W:.0f}" height="{Ht:.0f}" fill="url(#bg)"/>']
    out += [d[1] for d in draws]; out.append('</svg>')
    open(out_path, "w", encoding="utf-8").write("\n".join(out))
    print(f"wrote {out_path} | mode={mode} rooms={len(rooms)} walls={len(walls)} doors={len(doors)} furn={len(furniture)} win={len(windows)}")
