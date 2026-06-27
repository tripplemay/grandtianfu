# -*- coding: utf-8 -*-
"""路线A 精细版：从 平面布置图.svg 解析几何 → 等轴测 dollhouse，带真实家具造型/材质/柔和阴影/玻璃窗。
坐标系 1px=10mm；高度以 mm 给出，投影时 ×0.1。纯程序化，几何与平面图严格一致。"""
import re, math

SRC = "/Users/yixingzhou/project/grandtianfu/平面布置图.svg"
OUT = "/private/tmp/claude-501/-Users-yixingzhou-project-grandtianfu/f111c7d5-4519-442d-a10e-a5a5857da1e7/scratchpad/axon_v2.svg"
svg = open(SRC, encoding="utf-8-sig").read()
body = svg.split('transform="translate(150, 250)"')[1]
geo = body.split('<g id="room_labels">')[0]
rlbl = body.split('<g id="room_labels">')[1].split('</g>')[0]

# ---------------- 解析 ----------------
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

furn = [(float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)), m.group(5))
        for m in re.finditer(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"[^>]*?fill="(#[0-9a-fA-F]{6})"', geo)]
circ = [(float(m.group(1)), float(m.group(2)), float(m.group(3)), m.group(4))
        for m in re.finditer(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"[^>]*?fill="(#[0-9a-fA-F]{6})"', geo)]
flabels = [(float(m.group(1)), float(m.group(2)), m.group(3))
           for m in re.finditer(r'<text x="([\d.]+)" y="([\d.]+)"[^>]*>([^<]+)</text>',
                                geo.split('id="furniture-layer"')[1])]
windows = []
for m in re.finditer(r'<rect class="window"[^>]*?/>', geo):
    s = m.group(0)
    gx = re.search(r' x="(-?[\d.]+)"', s); gy = re.search(r' y="(-?[\d.]+)"', s)
    gw = re.search(r'width="([\d.]+)"', s); gh = re.search(r'height="([\d.]+)"', s)
    wt = re.search(r'data-wtype="(\w+)"', s)
    if gx and gy and gw and gh:
        windows.append((float(gx.group(1)), float(gy.group(1)), float(gw.group(1)), float(gh.group(1)),
                        wt.group(1) if wt else "normal"))
rlabels = [(float(m.group(1)), float(m.group(2)), m.group(3))
           for m in re.finditer(r'<text class="zh-label" x="([\d.]+)" y="([\d.]+)">([^<]+)</text>', rlbl)]

# ---------------- 投影 / 工具 ----------------
C, S = math.cos(math.radians(30)), math.sin(math.radians(30))
ZK = 0.1
def proj(x, y, z=0.0): return ((x - y) * C, (x + y) * S - z * ZK)
def shade(h, f):
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    g_ = lambda v: max(0, min(255, int(v * f)))
    return f"#{g_(r):02x}{g_(g):02x}{g_(b):02x}"
def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay; L = dx*dx + dy*dy
    t = 0 if L == 0 else max(0, min(1, ((px-ax)*dx + (py-ay)*dy) / L))
    return math.hypot(px - (ax+t*dx), py - (ay+t*dy))
def nearest_side(cx, cy):
    bd, bseg = 1e9, walls[0]
    for w in walls:
        d = seg_dist(cx, cy, *w[:4])
        if d < bd: bd, bseg = d, w
    ax, ay, bx, by = bseg[:4]
    if abs(ay-by) < abs(ax-bx): return 'N' if (ay+by)/2 < cy else 'S'
    return 'W' if (ax+bx)/2 < cx else 'E'

draws = []  # (depthkey, svg)
def emit(k, s): draws.append((k, s))
def faces(x0, y0, x1, y1, z0, z1, base, tf=1.0, ef=0.78, sf=0.6, oc="#0000001a"):
    P = lambda x, y, z: "%.1f,%.1f" % proj(x, y, z)
    top = f'<polygon points="{P(x0,y0,z1)} {P(x1,y0,z1)} {P(x1,y1,z1)} {P(x0,y1,z1)}" fill="{shade(base,tf)}" stroke="{oc}" stroke-width="0.4"/>'
    east = f'<polygon points="{P(x1,y0,z0)} {P(x1,y1,z0)} {P(x1,y1,z1)} {P(x1,y0,z1)}" fill="{shade(base,ef)}" stroke="{oc}" stroke-width="0.4"/>'
    south = f'<polygon points="{P(x0,y1,z0)} {P(x1,y1,z0)} {P(x1,y1,z1)} {P(x0,y1,z1)}" fill="{shade(base,sf)}" stroke="{oc}" stroke-width="0.4"/>'
    return east + south + top
def piece(boxes, cx, cy, extra=""):
    bs = sorted(boxes, key=lambda b: (b[0]+b[2])/2 + (b[1]+b[3])/2 + b[5]*0.02)
    emit(cx + cy + 5, "".join(faces(*b) for b in bs) + extra)
def shadow(x0, y0, x1, y1, cx, cy):
    o = 35; P = lambda x, y: "%.1f,%.1f" % proj(x, y, 0)
    emit(cx + cy + 4, f'<polygon points="{P(x0+o,y0+o)} {P(x1+o,y0+o)} {P(x1+o,y1+o)} {P(x0+o,y1+o)}" '
                      f'fill="#00000022" filter="url(#sh)"/>')
def edge(x0, y0, x1, y1, side, th, z0, z1, base):
    if side == 'N': return (x0, y0, x1, y0+th, z0, z1, base)
    if side == 'S': return (x0, y1-th, x1, y1, z0, z1, base)
    if side == 'W': return (x0, y0, x0+th, y1, z0, z1, base)
    return (x1-th, y0, x1, y1, z0, z1, base)

# ---------------- 分类 ----------------
def classify(cx, cy, fill, is_circle):
    if is_circle:
        if fill == "#cfe0cf": return "plant"
        if fill == "#cfe0d4": return "rchair"
        return "rtable"
    if fill == "#cfe0d4": return "chair"
    bd, name = 200, ""
    for lx, ly, t in flabels:
        d = math.hypot(cx-lx, cy-ly)
        if d < bd: bd, name = d, t
    kw = [("床头", "nightstand"), ("床", "bed"), ("沙发", "sofa"), ("贵妃", "sofa"),
          ("餐桌", "dtable"), ("茶几", "ctable"), ("中岛", "island"),
          ("衣柜", "wardrobe"), ("书柜", "wardrobe"), ("影视", "media"), ("电视", "media"),
          ("马桶", "toilet"), ("厕", "toilet"), ("浴缸", "tub"), ("台盆", "vanity"),
          ("淋浴", "shower"), ("洁具", "shower"), ("书桌", "desk"), ("梳妆", "desk"),
          ("鞋柜", "cab"), ("餐边", "cab"), ("高柜", "wardrobe"), ("橱柜", "counter"),
          ("洗烘", "wardrobe"), ("端景", "cab"), ("收纳", "wardrobe")]
    for k, ty in kw:
        if k in name: return ty
    # 颜色兜底
    if fill == "#e3c9a6": return "bed"
    if fill == "#d8c19c": return "sofa"
    if fill == "#cdb18f": return "wardrobe"
    if fill == "#e7d9bb": return "ctable"
    if fill == "#dde7ec": return "vanity"
    return "cab"

# ---------------- 家具模型 ----------------
WOOD_D, WOOD = "#9c7850", "#b9926a"
def m_bed(x0, y0, x1, y1, side, base):
    bx = []
    bx.append((x0, y0, x1, y1, 0, 300, WOOD_D))            # 床架
    ins = 30
    bx.append((x0+ins, y0+ins, x1-ins, y1-ins, 300, 430, "#f3ece0"))  # 床垫
    bx.append((x0+ins, y0+ins, x1-ins, y1-ins, 430, 480, base))       # 被褥
    bx.append(edge(x0, y0, x1, y1, side, 70, 0, 980, WOOD_D))         # 床头板
    # 枕头
    w, h = x1-x0, y1-y0
    if side in ('N', 'S'):
        yy = y0+90 if side == 'N' else y1-160
        bx.append((x0+w*0.12, yy, x0+w*0.46, yy+90, 470, 600, "#fffaf0"))
        bx.append((x0+w*0.54, yy, x0+w*0.88, yy+90, 470, 600, "#fffaf0"))
    else:
        xx = x0+90 if side == 'W' else x1-160
        bx.append((xx, y0+h*0.12, xx+90, y0+h*0.46, 470, 600, "#fffaf0"))
        bx.append((xx, y0+h*0.54, xx+90, y0+h*0.88, 470, 600, "#fffaf0"))
    return bx
def m_sofa(x0, y0, x1, y1, side, base):
    bx = [(x0, y0, x1, y1, 0, 340, shade(base, 0.85))]     # 底座
    ai = 90
    if side in ('N', 'S'):
        bx.append((x0+ai, y0+ai if side != 'S' else y0, x1-ai, y1 if side != 'S' else y1-ai, 340, 470, shade(base, 1.05)))
    else:
        bx.append((x0+ai if side != 'E' else x0, y0+ai, x1 if side != 'E' else x1-ai, y1-ai, 340, 470, shade(base, 1.05)))
    bx.append(edge(x0, y0, x1, y1, side, 90, 0, 760, shade(base, 0.8)))  # 靠背
    # 扶手（两侧）
    if side in ('N', 'S'):
        bx.append((x0, y0, x0+70, y1, 0, 560, shade(base, 0.75)))
        bx.append((x1-70, y0, x1, y1, 0, 560, shade(base, 0.75)))
    else:
        bx.append((x0, y0, x1, y0+70, 0, 560, shade(base, 0.75)))
        bx.append((x0, y1-70, x1, y1, 0, 560, shade(base, 0.75)))
    return bx
def m_legs_top(x0, y0, x1, y1, th, ttop, base, leg=None):
    leg = leg or shade(base, 0.7); lg = 60
    return [(x0, y0, x0+lg, y0+lg, 0, ttop-th, leg), (x1-lg, y0, x1, y0+lg, 0, ttop-th, leg),
            (x0, y1-lg, x0+lg, y1, 0, ttop-th, leg), (x1-lg, y1-lg, x1, y1, 0, ttop-th, leg),
            (x0, y0, x1, y1, ttop-th, ttop, base)]
def m_chair(x0, y0, x1, y1, side, base, backh=760):
    bx = m_legs_top(x0, y0, x1, y1, 55, 450, base)
    bx.append((x0+25, y0+25, x1-25, y1-25, 450, 510, shade(base, 1.08)))      # 坐垫
    bx.append(edge(x0, y0, x1, y1, side, 42, 450, backh, shade(base, 0.82)))  # 靠背
    return bx
def m_cab(x0, y0, x1, y1, base, h=820):
    return [(x0, y0, x1, y1, 0, h, base)]
def m_wardrobe(x0, y0, x1, y1, base):
    return [(x0, y0, x1, y1, 0, 2000, base)]
def m_toilet(x0, y0, x1, y1):
    cx, cy = (x0+x1)/2, (y0+y1)/2
    return [(x0+10, y0+10, x1-10, cy+15, 0, 400, "#eef2f5"), (x0+20, cy-5, x1-20, y1-10, 0, 600, "#e3eaef")]
def m_tub(x0, y0, x1, y1):
    return [(x0, y0, x1, y1, 0, 560, "#e7edf1"), (x0+25, y0+25, x1-25, y1-25, 300, 540, "#cdd9e2")]
def m_vanity(x0, y0, x1, y1):
    bx = [(x0, y0, x1, y1, 0, 820, "#dde7ec")]
    return bx
def m_plant(cx, cy, r):
    out = []
    px0, py0 = proj(cx, cy, 0)
    out.append((cx-r*0.6, cy-r*0.6, cx+r*0.6, cy+r*0.6, 0, 350, "#9a8466"))  # 盆
    return out

# ---------------- 地面 ----------------
FLOOR = {"living": "#d9c4a0", "bedroom": "#dcc8a4", "wet": "#cdd9e0",
         "outdoor": "#cfdac6", "corridor": "#dcd5c6", "public": "#d4d4d4"}
PLANK = {"living", "bedroom", "corridor"}
for t, x, y, w, h in rooms:
    col = FLOOR.get(t, "#e0e0e0")
    P = lambda X, Y: "%.1f,%.1f" % proj(X, Y, 0)
    emit(-1e9, f'<polygon points="{P(x,y)} {P(x+w,y)} {P(x+w,y+h)} {P(x,y+h)}" fill="{col}" stroke="#bfae8e" stroke-width="0.5"/>')
    if t in PLANK:
        step = 240; lc = shade(col, 0.92)
        xx = x + step
        while xx < x + w:
            a, b = proj(xx, y), proj(xx, y+h)
            emit(-9e8, f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" stroke="{lc}" stroke-width="0.8"/>')
            xx += step

# ---------------- 墙 ----------------
WALL_H, T_EXT, T_INT = 1450.0, 24.0, 14.0
TILE = 60.0   # 墙按长度切块，每块局部深度键 → 遮挡正确；无描边避免接缝
for ax, ay, bx, by, ext in walls:
    T = T_EXT if ext else T_INT
    horiz = abs(ay-by) < abs(ax-bx)
    lo, hi, fx = (min(ax, bx), max(ax, bx), ay) if horiz else (min(ay, by), max(ay, by), ax)
    n = max(1, int(round((hi-lo)/TILE)))
    step = (hi-lo)/n
    for i in range(n):
        s0, s1 = lo+i*step, lo+(i+1)*step
        if horiz: x0, x1, y0, y1 = s0, s1, fx-T/2, fx+T/2
        else: y0, y1, x0, x1 = s0, s1, fx-T/2, fx+T/2
        cx, cy = (x0+x1)/2, (y0+y1)/2
        emit(cx+cy, faces(x0, y0, x1, y1, 0, WALL_H, "#d7cfc0", tf=1.12, ef=0.82, sf=0.66, oc="none"))

# ---------------- 家具 ----------------
def dispatch(ty, x0, y0, x1, y1, fill):
    cx, cy = (x0+x1)/2, (y0+y1)/2; side = nearest_side(cx, cy)
    if ty == "bed": return m_bed(x0, y0, x1, y1, side, fill if fill.startswith('#') else "#e3c9a6")
    if ty == "sofa": return m_sofa(x0, y0, x1, y1, side, "#c2a06f")
    if ty == "chair":
        if min(x1-x0, y1-y0) <= 30: return m_chair(x0, y0, x1, y1, side, "#c9b79a", backh=720)  # 餐椅
        return m_chair(x0, y0, x1, y1, side, "#5f8870", backh=820)                                # 墨绿丝绒旋转椅
    if ty == "dtable": return m_legs_top(x0, y0, x1, y1, 50, 750, WOOD)
    if ty == "ctable": return m_legs_top(x0, y0, x1, y1, 45, 420, WOOD)
    if ty == "desk": return m_legs_top(x0, y0, x1, y1, 45, 750, "#cdb48c")
    if ty == "island": return [(x0, y0, x1, y1, 0, 880, "#cbb893"), (x0-15, y0-15, x1+15, y1+15, 880, 920, "#e6dcc4")]
    if ty == "wardrobe": return m_wardrobe(x0, y0, x1, y1, "#b89a72")
    if ty == "media": return m_cab(x0, y0, x1, y1, "#9c7044", h=520)
    if ty == "nightstand": return m_cab(x0, y0, x1, y1, "#caa97f", h=470)
    if ty == "toilet": return m_toilet(x0, y0, x1, y1)
    if ty == "tub": return m_tub(x0, y0, x1, y1)
    if ty == "vanity": return m_vanity(x0, y0, x1, y1)
    if ty == "shower": return [(x0, y0, x1, y1, 0, 120, "#cdd9e0")]
    if ty == "counter": return m_cab(x0, y0, x1, y1, "#d4c19a", h=850)
    return m_cab(x0, y0, x1, y1, fill if fill.startswith('#') else "#d4c19a")

for x, y, w, h, fill in furn:
    cx, cy = x+w/2, y+h/2
    ty = classify(cx, cy, fill, False)
    if max(w, h) <= 60 and ty == "cab": ty = "nightstand"
    boxes = dispatch(ty, x, y, x+w, y+h, fill)
    if ty != "shower": shadow(x, y, x+w, y+h, cx, cy)
    extra = ""
    if ty == "shower":  # 玻璃淋浴房
        P = lambda X, Y, Z: "%.1f,%.1f" % proj(X, Y, Z)
        extra = (f'<polygon points="{P(x,y,0)} {P(x+w,y,0)} {P(x+w,y,1900)} {P(x,y,1900)}" fill="#bcd6e388" stroke="#9bb8c8" stroke-width="1"/>'
                 f'<polygon points="{P(x+w,y,0)} {P(x+w,y+h,0)} {P(x+w,y+h,1900)} {P(x+w,y,1900)}" fill="#aac7d77a" stroke="#9bb8c8" stroke-width="1"/>')
    piece(boxes, cx, cy, extra)

for cx, cy, r, fill in circ:
    ty = classify(cx, cy, fill, True)
    shadow(cx-r, cy-r, cx+r, cy+r, cx, cy)
    if ty == "plant":
        boxes = [(cx-r*0.55, cy-r*0.55, cx+r*0.55, cy+r*0.55, 0, 360, "#8f7b5c")]
        tx, ty2 = proj(cx, cy, 360)
        extra = (f'<ellipse cx="{tx:.1f}" cy="{ty2-26:.1f}" rx="{r*1.5:.1f}" ry="{r*0.95:.1f}" fill="#6f9466"/>'
                 f'<ellipse cx="{tx-r*0.5:.1f}" cy="{ty2-46:.1f}" rx="{r*0.9:.1f}" ry="{r*0.6:.1f}" fill="#7fa676"/>')
        piece(boxes, cx, cy, extra)
    else:
        h = 430 if ty == "rtable" else 450
        base = "#e1d3b4" if ty == "rtable" else "#5f8870"
        bx0, by0 = proj(cx, cy, 0); tx, tyo = proj(cx, cy, h)
        rx, ry = r*2*C, r*2*S*0.62
        body = f'<rect x="{bx0-rx:.1f}" y="{tyo:.1f}" width="{2*rx:.1f}" height="{by0-tyo:.1f}" fill="{shade(base,0.72)}"/>'
        bot = f'<ellipse cx="{bx0:.1f}" cy="{by0:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{shade(base,0.72)}"/>'
        top = f'<ellipse cx="{tx:.1f}" cy="{tyo:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{base}" stroke="#0000001a" stroke-width="0.5"/>'
        emit(cx+cy+5, bot+body+top)

# ---------------- 窗（按类型出窗高的玻璃；深度用窗的最近角，画在所在墙块之后） ----------------
SILL = {"full": 0, "normal": 750, "high": 1100}   # 落地/普通/高窗 窗台高
for x, y, w, h, wt in windows:
    P = lambda X, Y, Z: "%.1f,%.1f" % proj(X, Y, Z)
    cx, cy = x+w/2, y+h/2
    z0 = SILL.get(wt, 750); z1 = WALL_H + 30
    a, b = ((x, cy), (x+w, cy)) if w >= h else ((cx, y), (cx, y+h))
    glass = f'<polygon points="{P(a[0],a[1],z0)} {P(b[0],b[1],z0)} {P(b[0],b[1],z1)} {P(a[0],a[1],z1)}" fill="#bfe0f0aa" stroke="#7fa6bc" stroke-width="2"/>'
    mull = ""
    for fr in (0.33, 0.66):
        mx, my = a[0]+(b[0]-a[0])*fr, a[1]+(b[1]-a[1])*fr
        p1, p2 = P(mx, my, z0), P(mx, my, z1)
        mull += f'<line x1="{p1.split(",")[0]}" y1="{p1.split(",")[1]}" x2="{p2.split(",")[0]}" y2="{p2.split(",")[1]}" stroke="#7fa6bc" stroke-width="1"/>'
    emit(max(a[0], b[0]) + max(a[1], b[1]) + 1, glass + mull)

# ---------------- 排序 + 标签 ----------------
draws.sort(key=lambda d: d[0])
lab_svg = []
for x, y, name in rlabels:
    px, py = proj(x, y, WALL_H+450)
    lab_svg.append(f'<text x="{px:.1f}" y="{py:.1f}" font-family="PingFang SC,Microsoft YaHei,sans-serif" '
                   f'font-size="30" font-weight="bold" fill="#33312c" text-anchor="middle" '
                   f'paint-order="stroke" stroke="#fbfaf7" stroke-width="4">{name}</text>')

allx, ally = [], []
for t, x, y, w, h in rooms:
    for X, Y in [(x, y), (x+w, y), (x, y+h), (x+w, y+h)]:
        for z in (0, WALL_H):
            p = proj(X, Y, z); allx.append(p[0]); ally.append(p[1])
minx, maxx, miny, maxy = min(allx)-220, max(allx)+220, min(ally)-340, max(ally)+220
W, H = maxx-minx, maxy-miny
out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx:.0f} {miny:.0f} {W:.0f} {H:.0f}" width="2000">',
       '<defs><filter id="sh" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="7"/></filter>',
       f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f6f3ec"/><stop offset="1" stop-color="#eae4d8"/></linearGradient></defs>',
       f'<rect x="{minx:.0f}" y="{miny:.0f}" width="{W:.0f}" height="{H:.0f}" fill="url(#bg)"/>']
out += [d[1] for d in draws]
out += lab_svg
out.append('</svg>')
open(OUT, "w", encoding="utf-8").write("\n".join(out))
print("wrote", OUT, "| rooms", len(rooms), "walls", len(walls), "furn", len(furn), "circ", len(circ), "win", len(windows))
