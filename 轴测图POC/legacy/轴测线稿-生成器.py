# -*- coding: utf-8 -*-
"""轴测线稿净版：复用精细版几何/家具模型，渲染为 白底+黑线、隐藏线消除(白填充按远近遮挡)。
去掉色彩/阴影/木纹/玻璃染色/文字标签。专供 ControlNet (lineart/canny/mlsd) 当 control 底图。"""
import re, math
SRC = "/Users/yixingzhou/project/grandtianfu/平面布置图.svg"
OUT = "/private/tmp/claude-501/-Users-yixingzhou-project-grandtianfu/f111c7d5-4519-442d-a10e-a5a5857da1e7/scratchpad/axon_lineart.svg"
svg = open(SRC, encoding="utf-8-sig").read()
body = svg.split('transform="translate(150, 250)"')[1]
geo = body.split('<g id="room_labels">')[0]

rooms = [(m.group(1), *map(float, m.groups()[1:]))
         for m in re.finditer(r'<rect class="room-([a-z]+)" x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', geo)]
walls = [(*map(float, m.groups()), False) for m in re.finditer(r'<line class="wall-thick" x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)"', geo)]
walls += [(*map(float, m.groups()), False) for m in re.finditer(r'<line x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)" stroke="#1a1a1a"', geo)]
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
           for m in re.finditer(r'<text x="([\d.]+)" y="([\d.]+)"[^>]*>([^<]+)</text>', geo.split('id="furniture-layer"')[1])]
windows = []
for m in re.finditer(r'<rect class="window"[^>]*?/>', geo):
    s = m.group(0)
    gx = re.search(r' x="(-?[\d.]+)"', s); gy = re.search(r' y="(-?[\d.]+)"', s)
    gw = re.search(r'width="([\d.]+)"', s); gh = re.search(r'height="([\d.]+)"', s)
    wt = re.search(r'data-wtype="(\w+)"', s)
    if gx and gy and gw and gh:
        windows.append((float(gx.group(1)), float(gy.group(1)), float(gw.group(1)), float(gh.group(1)),
                        wt.group(1) if wt else "normal"))

C, S = math.cos(math.radians(30)), math.sin(math.radians(30))
ZK = 0.1
def proj(x, y, z=0.0): return ((x - y) * C, (x + y) * S - z * ZK)
def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx-ax, by-ay; L = dx*dx+dy*dy
    t = 0 if L == 0 else max(0, min(1, ((px-ax)*dx+(py-ay)*dy)/L))
    return math.hypot(px-(ax+t*dx), py-(ay+t*dy))
def nearest_side(cx, cy):
    bd, bseg = 1e9, walls[0]
    for w in walls:
        d = seg_dist(cx, cy, *w[:4])
        if d < bd: bd, bseg = d, w
    ax, ay, bx, by = bseg[:4]
    if abs(ay-by) < abs(ax-bx): return 'N' if (ay+by)/2 < cy else 'S'
    return 'W' if (ax+bx)/2 < cx else 'E'

LINE, SW = "#111111", 1.4
draws = []
def emit(k, s): draws.append((k, s))
def faces(x0, y0, x1, y1, z0, z1, base, **kw):
    P = lambda x, y, z: "%.1f,%.1f" % proj(x, y, z)
    f = f'fill="#ffffff" stroke="{LINE}" stroke-width="{SW}" stroke-linejoin="round"'
    top = f'<polygon points="{P(x0,y0,z1)} {P(x1,y0,z1)} {P(x1,y1,z1)} {P(x0,y1,z1)}" {f}/>'
    east = f'<polygon points="{P(x1,y0,z0)} {P(x1,y1,z0)} {P(x1,y1,z1)} {P(x1,y0,z1)}" {f}/>'
    south = f'<polygon points="{P(x0,y1,z0)} {P(x1,y1,z0)} {P(x1,y1,z1)} {P(x0,y1,z1)}" {f}/>'
    return east + south + top
def piece(boxes, cx, cy, extra=""):
    bs = sorted(boxes, key=lambda b: (b[0]+b[2])/2 + (b[1]+b[3])/2 + b[5]*0.02)
    emit(cx+cy+5, "".join(faces(*b) for b in bs) + extra)
def edge(x0, y0, x1, y1, side, th, z0, z1, base):
    if side == 'N': return (x0, y0, x1, y0+th, z0, z1, base)
    if side == 'S': return (x0, y1-th, x1, y1, z0, z1, base)
    if side == 'W': return (x0, y0, x0+th, y1, z0, z1, base)
    return (x1-th, y0, x1, y1, z0, z1, base)

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
    for k, ty in [("床头","nightstand"),("床","bed"),("沙发","sofa"),("贵妃","sofa"),("餐桌","dtable"),
                  ("茶几","ctable"),("中岛","island"),("衣柜","wardrobe"),("书柜","wardrobe"),("影视","media"),
                  ("电视","media"),("马桶","toilet"),("厕","toilet"),("浴缸","tub"),("台盆","vanity"),
                  ("淋浴","shower"),("洁具","shower"),("书桌","desk"),("梳妆","desk"),("鞋柜","cab"),
                  ("餐边","cab"),("高柜","wardrobe"),("橱柜","counter"),("洗烘","wardrobe"),("端景","cab"),("收纳","wardrobe")]:
        if k in name: return ty
    return {"#e3c9a6":"bed","#d8c19c":"sofa","#cdb18f":"wardrobe","#e7d9bb":"ctable","#dde7ec":"vanity"}.get(fill, "cab")

def m_bed(x0,y0,x1,y1,side):
    bx=[(x0,y0,x1,y1,0,300,0),(x0+30,y0+30,x1-30,y1-30,300,480,0),edge(x0,y0,x1,y1,side,70,0,980,0)]
    w,h=x1-x0,y1-y0
    if side in('N','S'):
        yy=y0+90 if side=='N' else y1-160
        bx+=[(x0+w*0.12,yy,x0+w*0.46,yy+90,470,600,0),(x0+w*0.54,yy,x0+w*0.88,yy+90,470,600,0)]
    else:
        xx=x0+90 if side=='W' else x1-160
        bx+=[(xx,y0+h*0.12,xx+90,y0+h*0.46,470,600,0),(xx,y0+h*0.54,xx+90,y0+h*0.88,470,600,0)]
    return bx
def m_sofa(x0,y0,x1,y1,side):
    bx=[(x0,y0,x1,y1,0,340,0),edge(x0,y0,x1,y1,side,90,0,760,0)]
    if side in('N','S'): bx+=[(x0,y0,x0+70,y1,0,560,0),(x1-70,y0,x1,y1,0,560,0)]
    else: bx+=[(x0,y0,x1,y0+70,0,560,0),(x0,y1-70,x1,y1,0,560,0)]
    return bx
def m_legs_top(x0,y0,x1,y1,th,ttop):
    lg=60
    return [(x0,y0,x0+lg,y0+lg,0,ttop-th,0),(x1-lg,y0,x1,y0+lg,0,ttop-th,0),
            (x0,y1-lg,x0+lg,y1,0,ttop-th,0),(x1-lg,y1-lg,x1,y1,0,ttop-th,0),(x0,y0,x1,y1,ttop-th,ttop,0)]
def m_chair(x0,y0,x1,y1,side,backh=760):
    return m_legs_top(x0,y0,x1,y1,55,450)+[(x0+25,y0+25,x1-25,y1-25,450,510,0),edge(x0,y0,x1,y1,side,42,450,backh,0)]
def m_cab(x0,y0,x1,y1,h=820): return [(x0,y0,x1,y1,0,h,0)]
def m_toilet(x0,y0,x1,y1):
    cx,cy=(x0+x1)/2,(y0+y1)/2
    return [(x0+10,y0+10,x1-10,cy+15,0,400,0),(x0+20,cy-5,x1-20,y1-10,0,600,0)]
def m_tub(x0,y0,x1,y1): return [(x0,y0,x1,y1,0,560,0),(x0+25,y0+25,x1-25,y1-25,300,540,0)]

def dispatch(ty,x0,y0,x1,y1):
    cx,cy=(x0+x1)/2,(y0+y1)/2; side=nearest_side(cx,cy)
    if ty=="bed": return m_bed(x0,y0,x1,y1,side)
    if ty=="sofa": return m_sofa(x0,y0,x1,y1,side)
    if ty=="chair":
        if min(x1-x0,y1-y0)<=30: return m_chair(x0,y0,x1,y1,side,720)
        return m_chair(x0,y0,x1,y1,side,820)
    if ty=="dtable": return m_legs_top(x0,y0,x1,y1,50,750)
    if ty=="ctable": return m_legs_top(x0,y0,x1,y1,45,420)
    if ty=="desk": return m_legs_top(x0,y0,x1,y1,45,750)
    if ty=="island": return [(x0,y0,x1,y1,0,880,0),(x0-15,y0-15,x1+15,y1+15,880,920,0)]
    if ty=="wardrobe": return [(x0,y0,x1,y1,0,2000,0)]
    if ty=="media": return m_cab(x0,y0,x1,y1,520)
    if ty=="nightstand": return m_cab(x0,y0,x1,y1,470)
    if ty=="toilet": return m_toilet(x0,y0,x1,y1)
    if ty=="tub": return m_tub(x0,y0,x1,y1)
    if ty=="vanity": return m_cab(x0,y0,x1,y1,820)
    if ty=="shower": return [(x0,y0,x1,y1,0,120,0)]
    if ty=="counter": return m_cab(x0,y0,x1,y1,850)
    return m_cab(x0,y0,x1,y1)

# 地面：白填充+浅灰线（给 control 一个房间分隔参考，但不抢主线）
for t,x,y,w,h in rooms:
    P=lambda X,Y:"%.1f,%.1f"%proj(X,Y,0)
    emit(-1e9, f'<polygon points="{P(x,y)} {P(x+w,y)} {P(x+w,y+h)} {P(x,y+h)}" fill="#ffffff" stroke="#bbbbbb" stroke-width="1.0"/>')
# 墙（白填充切块做遮挡 + 整段轮廓线，无接缝）
WALL_H,T_EXT,T_INT=1450.0,24.0,14.0
TILE=60.0
def wall_fill(x0,y0,x1,y1,h):
    P=lambda x,y,z:"%.1f,%.1f"%proj(x,y,z)
    top=f'<polygon points="{P(x0,y0,h)} {P(x1,y0,h)} {P(x1,y1,h)} {P(x0,y1,h)}" fill="#ffffff" stroke="none"/>'
    east=f'<polygon points="{P(x1,y0,0)} {P(x1,y1,0)} {P(x1,y1,h)} {P(x1,y0,h)}" fill="#ffffff" stroke="none"/>'
    south=f'<polygon points="{P(x0,y1,0)} {P(x1,y1,0)} {P(x1,y1,h)} {P(x0,y1,h)}" fill="#ffffff" stroke="none"/>'
    return east+south+top
def _L(p,q): return f'<line x1="{p[0]:.1f}" y1="{p[1]:.1f}" x2="{q[0]:.1f}" y2="{q[1]:.1f}" stroke="{LINE}" stroke-width="{SW}"/>'
def wall_edges(x0,y0,x1,y1,h):
    p=lambda x,y,z:proj(x,y,z)
    return "".join([_L(p(x0,y0,h),p(x1,y0,h)),_L(p(x1,y0,h),p(x1,y1,h)),_L(p(x1,y1,h),p(x0,y1,h)),_L(p(x0,y1,h),p(x0,y0,h)),
                    _L(p(x1,y0,0),p(x1,y0,h)),_L(p(x1,y1,0),p(x1,y1,h)),_L(p(x0,y1,0),p(x0,y1,h)),
                    _L(p(x1,y0,0),p(x1,y1,0)),_L(p(x0,y1,0),p(x1,y1,0))])
for ax,ay,bx,by,ext in walls:
    T=T_EXT if ext else T_INT
    horiz=abs(ay-by)<abs(ax-bx)
    lo,hi,fx=(min(ax,bx),max(ax,bx),ay) if horiz else (min(ay,by),max(ay,by),ax)
    if horiz: x0,x1,y0,y1=lo,hi,fx-T/2,fx+T/2
    else: y0,y1,x0,x1=lo,hi,fx-T/2,fx+T/2
    n=max(1,int(round((hi-lo)/TILE))); step=(hi-lo)/n
    for i in range(n):
        a0,a1=lo+i*step,lo+(i+1)*step
        if horiz: tx0,tx1,ty0,ty1=a0,a1,y0,y1
        else: ty0,ty1,tx0,tx1=a0,a1,x0,x1
        emit((tx0+tx1)/2+(ty0+ty1)/2, wall_fill(tx0,ty0,tx1,ty1,WALL_H))
    emit(x1+y1+0.5, wall_edges(x0,y0,x1,y1,WALL_H))
# 家具
for x,y,w,h,fill in furn:
    cx,cy=x+w/2,y+h/2; ty=classify(cx,cy,fill,False)
    if max(w,h)<=60 and ty=="cab": ty="nightstand"
    piece(dispatch(ty,x,y,x+w,y+h),cx,cy)
# 圆（植物/圆椅/圆桌）
for cx,cy,r,fill in circ:
    ty=classify(cx,cy,fill,True); h=360 if ty=="plant" else (430 if ty=="rtable" else 450)
    bx0,by0=proj(cx,cy,0); tx,tyo=proj(cx,cy,h); rx,ry=r*2*C,r*2*S*0.62
    body=f'<rect x="{bx0-rx:.1f}" y="{tyo:.1f}" width="{2*rx:.1f}" height="{by0-tyo:.1f}" fill="#ffffff" stroke="{LINE}" stroke-width="{SW}"/>'
    bot=f'<ellipse cx="{bx0:.1f}" cy="{by0:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="#ffffff" stroke="{LINE}" stroke-width="{SW}"/>'
    top=f'<ellipse cx="{tx:.1f}" cy="{tyo:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="#ffffff" stroke="{LINE}" stroke-width="{SW}"/>'
    emit(cx+cy+5, bot+body+top)
# 窗：按类型出窗高的线框 + 竖向中梃（深度用窗最近角，画在墙之后）
SILL={"full":0,"normal":750,"high":1100}
for x,y,w,h,wt in windows:
    P=lambda X,Y,Z:"%.1f,%.1f"%proj(X,Y,Z); cx,cy=x+w/2,y+h/2
    z0=SILL.get(wt,750); z1=WALL_H+30
    a,b=((x,cy),(x+w,cy)) if w>=h else ((cx,y),(cx,y+h))
    s=f'<polygon points="{P(a[0],a[1],z0)} {P(b[0],b[1],z0)} {P(b[0],b[1],z1)} {P(a[0],a[1],z1)}" fill="none" stroke="{LINE}" stroke-width="{SW}"/>'
    for fr in (0.33,0.66):
        mx,my=a[0]+(b[0]-a[0])*fr,a[1]+(b[1]-a[1])*fr
        p1,p2=P(mx,my,z0),P(mx,my,z1)
        s+=f'<line x1="{p1.split(",")[0]}" y1="{p1.split(",")[1]}" x2="{p2.split(",")[0]}" y2="{p2.split(",")[1]}" stroke="{LINE}" stroke-width="0.8"/>'
    emit(max(a[0],b[0])+max(a[1],b[1])+1, s)

draws.sort(key=lambda d: d[0])
allx, ally = [], []
for t,x,y,w,h in rooms:
    for X,Y in [(x,y),(x+w,y),(x,y+h),(x+w,y+h)]:
        for z in (0,WALL_H):
            p=proj(X,Y,z); allx.append(p[0]); ally.append(p[1])
minx,maxx,miny,maxy=min(allx)-120,max(allx)+120,min(ally)-140,max(ally)+120
W,H=maxx-minx,maxy-miny
out=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx:.0f} {miny:.0f} {W:.0f} {H:.0f}" width="2400">',
     f'<rect x="{minx:.0f}" y="{miny:.0f}" width="{W:.0f}" height="{H:.0f}" fill="#ffffff"/>']
out+=[d[1] for d in draws]; out.append('</svg>')
open(OUT,"w",encoding="utf-8").write("\n".join(out))
print("wrote",OUT,"| walls",len(walls),"furn",len(furn),"circ",len(circ),"win",len(windows))
