# -*- coding: utf-8 -*-
"""
路线A POC：从 平面布置图.svg 解析几何，做等轴测(isometric)挤出。
风格：半墙 dollhouse —— 所有墙降到 ~1300mm，从30°俯视看进每个房间，规避遮挡裁剪。
家具按调色板映射高度。比例 1px=10mm。
"""
import re, math

SRC = "/Users/yixingzhou/project/grandtianfu/平面布置图.svg"
OUT = "/private/tmp/claude-501/-Users-yixingzhou-project-grandtianfu/f111c7d5-4519-442d-a10e-a5a5857da1e7/scratchpad/axon_poc.svg"
svg = open(SRC, encoding="utf-8-sig").read()

# 只取布局组(translate(150,250))之后、room_labels 之前的几何主体
body = svg.split('transform="translate(150, 250)"')[1]
geo = body.split('<g id="room_labels">')[0]
labels_block = body.split('<g id="room_labels">')[1].split('</g>')[0]

# ---------- 解析 ----------
rooms = []  # (type, x, y, w, h)
for m in re.finditer(r'<rect class="room-([a-z]+)" x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', geo):
    t, x, y, w, h = m.group(1), *map(float, m.groups()[1:])
    rooms.append((t, x, y, w, h))

walls = []  # axis-aligned wall segments (ax,ay,bx,by)
# wall-thick 线
for m in re.finditer(r'<line class="wall-thick" x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)"', geo):
    walls.append(tuple(map(float, m.groups())))
# furniture-layer 里 stroke=#1a1a1a 的补充墙线
for m in re.finditer(r'<line x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)" stroke="#1a1a1a"', geo):
    walls.append(tuple(map(float, m.groups())))

# 外轮廓 path
pm = re.search(r'<path class="wall-thick" d="\s*([^"]+)"', geo)
pts = []
if pm:
    toks = pm.group(1).replace('\n', ' ').split()
    i, cur = 0, None
    while i < len(toks):
        c = toks[i]
        if c in ('M', 'L'):
            x, y = map(float, toks[i+1].split(',')); cur = (x, y); pts.append(cur); i += 2
        elif c == 'V':
            cur = (cur[0], float(toks[i+1])); pts.append(cur); i += 2
        elif c == 'H':
            cur = (float(toks[i+1]), cur[1]); pts.append(cur); i += 2
        elif c == 'Z':
            pts.append(pts[0]); i += 1
        else:
            i += 1
    for a, b in zip(pts, pts[1:]):
        walls.append((a[0], a[1], b[0], b[1]))

# 家具 rect：按 (fill) 映射高度
FILL_H = {
    "#e3c9a6": (450, "bed"),      # 床
    "#d8c19c": (720, "sofa"),     # 沙发
    "#cfe0d4": (450, "chair"),    # 软座/椅
    "#ece0c8": (820, "cab"),      # 柜(低)
    "#cdb18f": (1800, "tall"),    # 木柜(高/衣柜)
    "#e7d9bb": (430, "table"),    # 矮桌/中岛/床头柜
    "#dde7ec": (600, "wet"),      # 洁具
}
furn = []  # (x,y,w,h, z, fill)
for m in re.finditer(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"[^>]*?fill="(#[0-9a-fA-F]{6})"', geo):
    x, y, w, h = map(float, m.groups()[:4]); fill = m.group(5)
    if fill in FILL_H:
        z, _ = FILL_H[fill]
        furn.append((x, y, w, h, z, fill))

circles = []  # (cx,cy,r,z,fill)
CIRC_H = {"#cfe0cf": (650, "plant"), "#cfe0d4": (450, "chair"), "#e7d9bb": (430, "table")}
for m in re.finditer(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"[^>]*?fill="(#[0-9a-fA-F]{6})"', geo):
    cx, cy, r = map(float, m.groups()[:3]); fill = m.group(4)
    if fill in CIRC_H:
        circles.append((cx, cy, r, CIRC_H[fill][0], fill))

# 房名标签
labels = []
for m in re.finditer(r'<text class="zh-label" x="([\d.]+)" y="([\d.]+)">([^<]+)</text>', labels_block):
    labels.append((float(m.group(1)), float(m.group(2)), m.group(3)))

# ---------- 等轴测投影 ----------
C, S = math.cos(math.radians(30)), math.sin(math.radians(30))
ZK = 0.1  # 高度缩放: 坐标系 1px=10mm，故 mm 高度需 ×0.1 转为 px
def proj(x, y, z=0.0):
    return ((x - y) * C, (x + y) * S - z * ZK)

WALL_H = 1400.0
FLOOR = {"living": "#ece0c6", "bedroom": "#e7d6ba", "wet": "#d7e2e9",
         "outdoor": "#dfe7d8", "corridor": "#e6e0d4", "public": "#dedede"}

def shade(hex_, f):
    r, g, b = int(hex_[1:3], 16), int(hex_[3:5], 16), int(hex_[5:7], 16)
    return f"#{max(0,min(255,int(r*f))):02x}{max(0,min(255,int(g*f))):02x}{max(0,min(255,int(b*f))):02x}"

draws = []  # (depth_key, svg_string)

# 地面（最先画，z=0 顶面）
for t, x, y, w, h in rooms:
    col = FLOOR.get(t, "#e8e8e8")
    p = [proj(x, y), proj(x+w, y), proj(x+w, y+h), proj(x, y+h)]
    pstr = " ".join(f"{px:.1f},{py:.1f}" for px, py in p)
    draws.append((-1e9, f'<polygon points="{pstr}" fill="{col}" stroke="#c9bca2" stroke-width="0.6"/>'))

def box(x0, y0, x1, y1, h, base, key_bias=0):
    """轴对齐立方体：可见 top + 东(x1)面 + 南(y1)面，带明暗。"""
    cx, cy = (x0+x1)/2, (y0+y1)/2
    key = cx + cy + key_bias
    def P(x, y, z):
        px, py = proj(x, y, z); return f"{px:.1f},{py:.1f}"
    top = f'<polygon points="{P(x0,y0,h)} {P(x1,y0,h)} {P(x1,y1,h)} {P(x0,y1,h)}" fill="{shade(base,1.0)}" stroke="#00000022" stroke-width="0.5"/>'
    east = f'<polygon points="{P(x1,y0,0)} {P(x1,y1,0)} {P(x1,y1,h)} {P(x1,y0,h)}" fill="{shade(base,0.74)}" stroke="#00000022" stroke-width="0.5"/>'
    south = f'<polygon points="{P(x0,y1,0)} {P(x1,y1,0)} {P(x1,y1,h)} {P(x0,y1,h)}" fill="{shade(base,0.60)}" stroke="#00000022" stroke-width="0.5"/>'
    draws.append((key, east + south + top))

# 墙体（半高）
T = 90.0
for ax, ay, bx, by in walls:
    if abs(ay - by) < abs(ax - bx):  # 水平
        x0, x1 = min(ax, bx), max(ax, bx); y0, y1 = ay - T/2, ay + T/2
    else:  # 垂直
        y0, y1 = min(ay, by), max(ay, by); x0, x1 = ax - T/2, ax + T/2
    box(x0, y0, x1, y1, WALL_H, "#cfc6b8", key_bias=0)

# 家具方块
for x, y, w, h, z, fill in furn:
    box(x, y, x+w, y+h, z, fill, key_bias=5)

# 圆柱（植物/圆桌/圆椅）→ 椭圆顶 + 体块近似
for cx, cy, r, z, fill in circles:
    botx, boty = proj(cx, cy, 0); topx, topy = proj(cx, cy, z)
    rx, ry = r * (2*C), r * (2*S) * 0.6
    key = cx + cy + 6
    body = f'<rect x="{botx-rx:.1f}" y="{topy:.1f}" width="{2*rx:.1f}" height="{boty-topy:.1f}" fill="{shade(fill,0.7)}"/>'
    bot = f'<ellipse cx="{botx:.1f}" cy="{boty:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{shade(fill,0.7)}"/>'
    top = f'<ellipse cx="{topx:.1f}" cy="{topy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{shade(fill,1.0)}" stroke="#00000022" stroke-width="0.5"/>'
    draws.append((key, bot + body + top))

# 画家算法：远(小 x+y)先画
draws.sort(key=lambda d: d[0])

# 房名标签（浮在房间上方）
label_svg = []
for x, y, name in labels:
    px, py = proj(x, y, WALL_H + 350)
    label_svg.append(f'<text x="{px:.1f}" y="{py:.1f}" font-family="PingFang SC,Microsoft YaHei,sans-serif" '
                     f'font-size="34" font-weight="bold" fill="#2b2b2b" text-anchor="middle">{name}</text>')

# ---------- 计算画布 ----------
allx = []; ally = []
for t, x, y, w, h in rooms:
    for cx, cy in [(x, y), (x+w, y), (x, y+h), (x+w, y+h)]:
        for z in (0, WALL_H):
            px, py = proj(cx, cy, z); allx.append(px); ally.append(py)
minx, maxx, miny, maxy = min(allx)-200, max(allx)+200, min(ally)-300, max(ally)+200
W, H = maxx - minx, maxy - miny

out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx:.0f} {miny:.0f} {W:.0f} {H:.0f}" width="1600">']
out.append(f'<rect x="{minx:.0f}" y="{miny:.0f}" width="{W:.0f}" height="{H:.0f}" fill="#fbfaf7"/>')
out += [d[1] for d in draws]
out += label_svg
out.append('</svg>')
open(OUT, "w", encoding="utf-8").write("\n".join(out))
print("wrote", OUT, "| rooms", len(rooms), "walls", len(walls), "furn", len(furn), "circ", len(circles))
