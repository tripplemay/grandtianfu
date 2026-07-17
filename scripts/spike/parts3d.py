# -*- coding: utf-8 -*-
"""L1 简模引导渲染 (calib-cure-b1 F011): 部件级 3D 盒 + 平光着色 + painter 排序。

家具不再是单个半透明彩盒 (L0), 而是按 catalog.plan2d_spec 的俯视部件 (靠背/扶手/隔板/
桌腿...) 拼成的一组不透明 3D 盒 —— 沙发有靠背扶手、书柜有隔板、餐桌有腿, 给编辑模型
"形状级"引导 (docs/3D模型引导-出图质变评估-20260717.md §2 的 L1 形态)。

坐标/投影约定完全沿用产品 (apps/api/aigc/perspective.py, importlib 路径加载不改产品):
  - footprint 为 px (×mm_per_px 得 mm), 世界系 X=东 Y=南 Z=上, **真实毫米世界层高 2700**
    (perspective._REAL_CEILING_MM; 严禁借 axon 压扁世界的 1450);
  - 相机系裁剪 (near 平面) 与投影复用产品 _clip_face_near / NEAR_MM / Camera;
  - 类型跳过集 / 调色序 / legend 结构 / box_usability 与产品 annotate_boxes 逐字对齐
    (两臂公平性, spec §D5)。

部件高度表**硬编码在本脚本** (spec §D5: 不进产品数据/目录), 数值与产品
perspective._DEFAULT_HEIGHT_MM 的整盒顶同源对齐 (L1 外包络 = L0 盒, 只多内部结构)。
"""

from __future__ import annotations

import io
import math

import numpy as np

# ---------------------------------------------------------------------------
# 部件高度表 (mm) —— spike 专用硬编码 (spec §D5)。整盒顶与产品默认一致:
# sofa 800 / dining_table 760 / desk 750 / coffee_table 420 / chair 900 /
# media 550 / wine_cabinet 1400 / bookshelf 2000 / plant 900 / curtain 2700。
# ---------------------------------------------------------------------------
SOFA_SEAT_MM = 420.0
SOFA_BACK_MM = 800.0
SOFA_ARM_MM = 620.0
CHAIR_SEAT_MM = 450.0
CHAIR_BACK_MM = 900.0
CHAIR_BACK_DEPTH_FRAC = 0.18  # chair 的 plan2d_spec 无 edge 部件 -> 靠背条带占比取此值
TABLE_TOP_THICK_MM = 40.0
SHELF_STEP_MM = 350.0  # bookshelf 每层隔板间距
SHELF_THICK_MM = 30.0
PLANT_POT_MM = 250.0  # plant 锥台近似: 盆 0..250, 冠层收分至 900
PLANT_MID_MM = 620.0

# 桌腿/侧板尺寸 (px 单位, 1px = mm_per_px mm; D 户型 10)。
_LEG_SIDE_PX = (3.0, 12.0)  # 腿截面边长 = 0.12*min(w,h) 夹取到 [3,12] px
_LEG_INSET_FRAC = 0.05
_PANEL_PX = (2.0, 6.0)  # 书柜端板厚 = 0.08*min(w,h) 夹取

# 平光着色: 固定光向 (相机系; x右 y下 z前), 面法线·光向 -> 明暗分面。
_LIGHT_CAM = np.array([-0.35, -0.8, -0.47])
_LIGHT_CAM = _LIGHT_CAM / np.linalg.norm(_LIGHT_CAM)
_AMBIENT = 0.38
_DIFFUSE = 0.62
# 简模基色 = 产品 ANNO_PALETTE 同序色相压向灰 (prompt 语义 "gray 3D primitive mockups",
# 同类家具同色系仍可区分)。
_TINT_KEEP = 0.42
_TINT_GRAY = 150.0
BLANK_BG = (172, 172, 172)


def _footprint_rect(item: dict, room_origin) -> tuple:
    """家具落地脚印 (绝对 px, 未乘 mm) -> (x, y, w, h)。圆形件用外接方。

    与产品 perspective._footprint_corners_px (L232-244) 同一套数学, 但返回 x/y/w/h
    以便部件细分 (产品返回四角点列)。
    """
    ox, oy = room_origin
    if "dcx" in item or "dcy" in item:
        r = float(item.get("r", 20) or 20)
        cx = ox + float(item.get("dcx", 0) or 0)
        cy = oy + float(item.get("dcy", 0) or 0)
        return cx - r, cy - r, 2 * r, 2 * r
    return (
        ox + float(item.get("dx", 0) or 0),
        oy + float(item.get("dy", 0) or 0),
        float(item.get("w", 0) or 0),
        float(item.get("h", 0) or 0),
    )


def _rect_part(x: float, y: float, w: float, h: float, z0: float, z1: float) -> dict:
    return {"x": x, "y": y, "w": w, "h": h, "z0": float(z0), "z1": float(z1)}


def _center_scaled(x, y, w, h, scale):
    return x + w * (1 - scale) / 2, y + h * (1 - scale) / 2, w * scale, h * scale


def _spec_part(spec, kind: str) -> dict:
    for part in spec or []:
        if isinstance(part, dict) and part.get("k") == kind:
            return part
    return {}


def _sofa_like(item, x, y, w, h, top, p2s, spec):
    """sofa/chaise/armchair: 座 420 + 靠背 800 + 扶手 620 (贴 orient 边, 占比取自
    catalog.plan2d_spec —— 与产品 2D 外形同一真源; 高度取自本脚本硬编码表)。"""
    o = item.get("orient")
    parts = [_rect_part(x, y, w, h, 0, min(SOFA_SEAT_MM, top))]
    edge = p2s._edge_rect(
        x,
        y,
        w,
        h,
        o if o in p2s._ORIENTS else "N",
        float(_spec_part(spec, "edge").get("depth", 0.22)),
    )
    parts.append(_rect_part(edge["x"], edge["y"], edge["w"], edge["h"], 0, min(SOFA_BACK_MM, top)))
    arms_spec = _spec_part(spec, "arms")
    for arm in p2s._arm_rects(
        x,
        y,
        w,
        h,
        o if o in p2s._ORIENTS else "N",
        float(arms_spec.get("depth", 0.85)),
        float(arms_spec.get("width", 0.11)),
    ):
        parts.append(_rect_part(arm["x"], arm["y"], arm["w"], arm["h"], 0, min(SOFA_ARM_MM, top)))
    return parts


def _chair_like(item, x, y, w, h, top, p2s, spec):
    """chair/desk_chair: 座 450 + 靠背 900 (靠背条带贴 orient 边, 占比硬编码)。"""
    o = item.get("orient")
    parts = [_rect_part(x, y, w, h, 0, min(CHAIR_SEAT_MM, top))]
    edge = p2s._edge_rect(x, y, w, h, o if o in p2s._ORIENTS else "N", CHAIR_BACK_DEPTH_FRAC)
    parts.append(_rect_part(edge["x"], edge["y"], edge["w"], edge["h"], 0, min(CHAIR_BACK_MM, top)))
    return parts


def _table_like(item, x, y, w, h, top, p2s, spec):
    """dining_table 760 / desk 750 / coffee_table 420: 面板厚 40 + 四角腿。
    desk 另按 plan2d_spec 的 edge (0.1) 加背板条 (挡板)。"""
    thick = min(TABLE_TOP_THICK_MM, top / 2)
    leg_h = top - thick
    parts = [_rect_part(x, y, w, h, leg_h, top)]
    side = max(_LEG_SIDE_PX[0], min(_LEG_SIDE_PX[1], 0.12 * min(w, h)))
    ix, iy = w * _LEG_INSET_FRAC, h * _LEG_INSET_FRAC
    for lx, ly in (
        (x + ix, y + iy),
        (x + w - ix - side, y + iy),
        (x + ix, y + h - iy - side),
        (x + w - ix - side, y + h - iy - side),
    ):
        parts.append(_rect_part(lx, ly, side, side, 0, leg_h))
    edge_spec = _spec_part(spec, "edge")
    if item.get("t") == "desk" and edge_spec:
        o = item.get("orient")
        edge = p2s._edge_rect(
            x, y, w, h, o if o in p2s._ORIENTS else "N", float(edge_spec.get("depth", 0.1))
        )
        parts.append(_rect_part(edge["x"], edge["y"], edge["w"], edge["h"], 250.0, leg_h))
    return parts


def _bookshelf(item, x, y, w, h, top, p2s, spec):
    """bookshelf: 框 (两端板 + 顶板) + 每 350mm 一层通长隔板; 顶随 item.z (产品同款覆盖)。"""
    panel = max(_PANEL_PX[0], min(_PANEL_PX[1], 0.08 * min(w, h)))
    parts = []
    if w >= h:  # 长轴 = x -> 端板在左右
        parts.append(_rect_part(x, y, panel, h, 0, top))
        parts.append(_rect_part(x + w - panel, y, panel, h, 0, top))
    else:  # 长轴 = y -> 端板在上下
        parts.append(_rect_part(x, y, w, panel, 0, top))
        parts.append(_rect_part(x, y + h - panel, w, panel, 0, top))
    z = 0.0
    while z + SHELF_THICK_MM <= top - SHELF_STEP_MM / 2:  # 底板起, 每 350 一层
        parts.append(_rect_part(x, y, w, h, z, z + SHELF_THICK_MM))
        z += SHELF_STEP_MM
    parts.append(_rect_part(x, y, w, h, top - SHELF_THICK_MM, top))  # 顶板
    return parts


def _plant(item, x, y, w, h, top, p2s, spec):
    """plant: 锥台近似 —— 盆 (45%) + 下冠 (95%) + 上冠 (60%) 收分到 900。"""
    pot = min(PLANT_POT_MM, top)
    mid = min(PLANT_MID_MM, top)
    parts = [_rect_part(*_center_scaled(x, y, w, h, 0.45), 0, pot)]
    if mid > pot:
        parts.append(_rect_part(*_center_scaled(x, y, w, h, 0.95), pot, mid))
    if top > mid:
        parts.append(_rect_part(*_center_scaled(x, y, w, h, 0.6), mid, top))
    return parts


def _whole_box(item, x, y, w, h, top, p2s, spec, *, z0: float = 0.0):
    """整盒回退 (无 spec / 平板类): 与产品 L0 盒同外形 (media 550 / wine_cabinet 1400 /
    curtain 全高薄板 0..2700 / wall_art 墙面带 1000..1400 由 z0 参数带入)。"""
    return [_rect_part(x, y, w, h, z0, top)]


_BUILDERS = {
    "sofa": _sofa_like,
    "chaise": _sofa_like,
    "armchair": _sofa_like,
    "chair": _chair_like,
    "desk_chair": _chair_like,
    "dining_table": _table_like,
    "desk": _table_like,
    "coffee_table": _table_like,
    "bookshelf": _bookshelf,
    "plant": _plant,
    # media 550 / wine_cabinet 1400 / curtain 全高薄板: 高度表数值与产品整盒顶一致,
    # 走整盒 (内部结构对引导增益有限, 保持与 L0 同外形)。
    "media": _whole_box,
    "wine_cabinet": _whole_box,
    "curtain": _whole_box,
}


def build_parts(item: dict, room_origin, persp, catalog, p2s) -> list:
    """单件家具 -> 部件 3D 盒列表 [{x,y,w,h,z0,z1} px/mm]。

    顶高包络 = 产品 item_top_z_mm (item.z 优先, 缺省用产品默认表) —— L1 外包络与
    L0 盒一致, 部件高超包络时夹取 (两臂公平: 只多内部结构, 不多占空间)。
    无 builder 的类型回退整盒 (z0 沿产品 _item_z0_mm: 挂画墙面带 1000)。
    """
    x, y, w, h = _footprint_rect(item, room_origin)
    top = persp.item_top_z_mm(item)
    builder = _BUILDERS.get(item.get("t"))
    spec = catalog.plan2d_spec(item.get("t"))
    if builder is None:
        return _whole_box(item, x, y, w, h, top, p2s, spec, z0=persp._item_z0_mm(item))
    return builder(item, x, y, w, h, top, p2s, spec)


def mockup_tint(rgb) -> tuple:
    """ANNO_PALETTE 色相压向灰 -> 简模基色 (灰底上同类同色系可区分)。"""
    return tuple(int(round(_TINT_KEEP * c + (1 - _TINT_KEEP) * _TINT_GRAY)) for c in rgb)


def _part_faces(cam, part: dict, mm_per_px: float, persp) -> list:
    """部件盒 -> [(深度均值, 像素多边形, 相机系法线)] 6 面, near 裁剪在投影前。

    复用产品 _clip_face_near/NEAR_MM (perspective.py L292-350 的 _box_polys 思想:
    顶点先到相机系, 裁剪存活后再乘 K 投影)。
    """
    x, y, w, h = part["x"], part["y"], part["w"], part["h"]
    corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]

    def cpt(px, py, z):
        wpt = np.array([px * mm_per_px, py * mm_per_px, z], float)
        return cam.R @ wpt + cam.t

    base = [cpt(px, py, part["z0"]) for px, py in corners]
    top = [cpt(px, py, part["z1"]) for px, py in corners]
    faces = [base, top] + [[base[i], base[(i + 1) % 4], top[(i + 1) % 4], top[i]] for i in range(4)]
    out = []
    for face in faces:
        n = np.cross(face[1] - face[0], face[2] - face[0])
        norm = float(np.linalg.norm(n))
        n = n / norm if norm > 1e-9 else np.array([0.0, 0.0, 1.0])
        clipped = persp._clip_face_near(face, persp.NEAR_MM)
        if len(clipped) < 3:
            continue
        pts, depths = [], []
        for c in clipped:
            uv = cam.K @ c
            pts.append((float(uv[0] / uv[2]), float(uv[1] / uv[2])))
            depths.append(float(uv[2]))
        out.append((float(np.mean(depths)), pts, n))
    return out


def _shade(base_rgb, normal) -> tuple:
    """面法线·固定光向 -> 平光明暗 (abs 双面, 免面绕序簿记)。"""
    lam = _AMBIENT + _DIFFUSE * abs(float(np.dot(normal, _LIGHT_CAM)))
    return tuple(min(255, int(round(c * lam))) for c in base_rgb)


def render_l1_guide(
    persp,
    catalog,
    p2s,
    cam,
    furniture: list,
    rooms_by_id: dict,
    photo_png,
    img_wh,
    *,
    mm_per_px: float = 10.0,
    include=None,
) -> tuple:
    """L1 简模引导图 -> (png_bytes, legend, drawn)。

    photo_png=None -> 灰底 (--blank)。迭代顺序 / 类型跳过 / 调色序 / legend 结构 /
    box_usability 降级标记与产品 annotate_boxes (perspective.py L475-555) 逐字对齐,
    仅把"半透明彩盒"换成"部件级不透明简模" (spec §D5 两臂公平性)。
    """
    from PIL import Image, ImageDraw

    W, H = img_wh
    if photo_png is None:
        canvas = Image.new("RGB", (W, H), BLANK_BG)
    else:
        canvas = Image.open(io.BytesIO(photo_png)).convert("RGB")
        if canvas.size != (W, H):
            canvas = canvas.resize((W, H))
    color_by_type: dict = {}
    legend: list = []
    faces: list = []  # (depth, pts, fill_rgb, outline_rgb)
    drawn = 0
    for it in furniture:
        t = it.get("t")
        if not t or t in persp.ANNO_SKIP_TYPES:
            continue
        if include is not None and t not in include:
            continue
        rect = rooms_by_id.get(it.get("room_id"))
        if not rect:
            continue
        if t not in color_by_type:
            if len(color_by_type) >= len(persp.ANNO_PALETTE):
                raise ValueError(
                    f"简模调色板耗尽: 家具类型数 > {len(persp.ANNO_PALETTE)} "
                    "(与产品 annotate_boxes 同规则拒绝出图)"
                )
            name, rgb = persp.ANNO_PALETTE[len(color_by_type)]
            color_by_type[t] = (name, mockup_tint(rgb))
            legend.append({"color": name, "t": t, "count": 0})
        entry = next(e for e in legend if e["t"] == t)
        entry["count"] += 1
        u = persp.box_usability(cam, it, (rect[0], rect[1]), img_wh, mm_per_px=mm_per_px)
        if not u["usable"] or u["in_frame_frac"] < 0.85:
            entry["partial"] = True
        if u["near"]:
            entry["near"] = True
        base_rgb = color_by_type[t][1]
        for part in build_parts(it, (rect[0], rect[1]), persp, catalog, p2s):
            for depth, pts, normal in _part_faces(cam, part, mm_per_px, persp):
                fill = _shade(base_rgb, normal)
                outline = tuple(int(round(v * 0.45)) for v in fill)
                faces.append((depth, pts, fill, outline))
        drawn += 1
    draw = ImageDraw.Draw(canvas)
    for _depth, pts, fill, outline in sorted(faces, key=lambda f: -f[0]):  # painter: 远->近
        draw.polygon(pts, fill=fill, outline=outline, width=2)
    buf = io.BytesIO()
    canvas.save(buf, "PNG")
    return buf.getvalue(), legend, drawn


def blank_photo_png(img_wh) -> bytes:
    """--blank 灰底照片字节 (供 L0 臂 annotate_boxes 与 provider 输入复用)。"""
    from PIL import Image

    im = Image.new("RGB", (int(img_wh[0]), int(img_wh[1])), BLANK_BG)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def hfov_deg(cam, img_w: float) -> float:
    """水平视场角 (调试输出用)。"""
    return math.degrees(2 * math.atan((img_w / 2.0) / cam.focal))
