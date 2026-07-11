# -*- coding: utf-8 -*-
"""透视标定 + 家具几何投影 (路线A P2, 纯 numpy)。

带透视的实拍空房照 -> 相机 (K,R,t) -> 家具 3D 盒子投影 -> footprint mask。
标定输入 (用户在 UI 提供): 两组正交地面墙线 (各 >=2 条平行, 求 2 个消失点) + >=2 个地面锚点
(world mm z=0 <-> 像素)。消失点给相机朝向/焦距 (透视越强越准, 与"带透视更好看"
同向); 锚点给绝对定位并消解姿态符号歧义。自动消失点检测 (cv2) 属可选增强, 不是本模块的必需依赖。

世界系约定: X=毫米东(+), Y=毫米南(+), Z=上(+); 地面 z=0。
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np

Point = tuple[float, float]
Line = tuple[Point, Point]


@dataclass(frozen=True)
class Camera:
    """针孔相机: 像素 = K (R·world_mm + t) 归一化。R 列 = 世界轴在相机系的方向。"""

    K: np.ndarray  # 3x3 内参
    R: np.ndarray  # 3x3 世界->相机
    t: np.ndarray  # (3,) 平移

    def project(self, x: float, y: float, z: float = 0.0) -> Point:
        uv = self.K @ (self.R @ np.array([x, y, z], float) + self.t)
        return float(uv[0] / uv[2]), float(uv[1] / uv[2])

    @property
    def focal(self) -> float:
        return float(self.K[0, 0])

    def to_dict(self) -> dict:
        """序列化存盘 (photo.calibration.camera)。"""
        return {
            "K": self.K.tolist(),
            "R": self.R.tolist(),
            "t": self.t.tolist(),
            "focal": self.focal,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Camera":
        return cls(
            K=np.array(d["K"], float), R=np.array(d["R"], float), t=np.array(d["t"], float)
        )


# 家具默认高度 (mm), 用于把 footprint 抬成 3D 盒子覆盖 (item.z 优先)。
_DEFAULT_HEIGHT_MM = {
    "sofa": 800, "bed": 500, "media": 550, "tv": 1200, "coffee_table": 420,
    "dining_table": 760, "cabinet": 850, "wardrobe": 2000, "desk": 750,
    "chair": 900, "nightstand": 500, "bookshelf": 2000, "rug": 8, "plant": 900,
}


def _item_height_mm(item: dict) -> float:
    z = item.get("z")
    if isinstance(z, (int, float)) and not isinstance(z, bool) and z > 0:
        return float(z)
    return float(_DEFAULT_HEIGHT_MM.get(item.get("t"), 600))


def _homog_line(p1: Point, p2: Point) -> np.ndarray:
    return np.cross([p1[0], p1[1], 1.0], [p2[0], p2[1], 1.0])


def vanishing_point(lines: list[Line]) -> np.ndarray:
    """一组平行线 (每条 = 两端点) 的消失点 (SVD 最小二乘交点)。>=2 条。"""
    if len(lines) < 2:
        raise ValueError("消失点需 >=2 条平行线")
    L = np.array([_homog_line(a, b) for a, b in lines], float)
    norm = np.linalg.norm(L[:, :2], axis=1, keepdims=True)
    L = L / np.where(norm == 0, 1.0, norm)
    _, _, Vt = np.linalg.svd(L)
    v = Vt[-1]
    if abs(v[2]) < 1e-12:
        raise ValueError("消失点在无穷远 (线接近平行, 需更强透视或更准端点)")
    return v[:2] / v[2]


def calibrate(
    x_lines: list[Line],
    y_lines: list[Line],
    anchors: list[tuple[tuple[float, float, float], Point]],
    *,
    img_wh: tuple[int, int],
) -> Camera:
    """两组正交地面墙线 (求 2 消失点) + >=2 个已知地面锚点 -> Camera。

    x_lines: 沿世界 X 方向的平行线 (如南墙水平边); y_lines: 沿世界 Y (东墙水平边)。
    anchors: [((Xmm,Ymm,Zmm),(u,v)), ...] 至少 2 个 —— 产品里 = 用户点 2 个墙角。
    消失点定相机朝向/焦距; 锚点用最小二乘定尺度/平移, 并消解姿态符号歧义 (单锚点会
    被 t 拟合到 0 无法区分 sign, 故要求 >=2)。
    """
    if len(anchors) < 2:
        raise ValueError("calibrate 需 >=2 个锚点定尺度并消解符号歧义")
    W, H = img_wh
    cx, cy = W / 2.0, H / 2.0
    c = np.array([cx, cy])
    vpx = vanishing_point(x_lines)
    vpy = vanishing_point(y_lines)
    f2 = -float(np.dot(vpx - c, vpy - c))
    if f2 <= 0:
        raise ValueError("消失点正交约束失败 (两 VP 同侧); 检查墙线方向分组")
    f = f2**0.5
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
    Kinv = np.linalg.inv(K)
    ex = Kinv @ np.array([vpx[0], vpx[1], 1.0])
    ex /= np.linalg.norm(ex)
    ey = Kinv @ np.array([vpy[0], vpy[1], 1.0])
    ey /= np.linalg.norm(ey)
    aw = [np.array(w, float) for w, _ in anchors]
    ap = [np.array([p[0], p[1], 1.0]) for _, p in anchors]
    n = len(anchors)

    def solve_t(R):
        # λ_i·m_i - t = R·P_i ; 未知 [λ_1..λ_n, t(3)]; 最小二乘。
        A = np.zeros((3 * n, n + 3))
        b = np.zeros(3 * n)
        for i in range(n):
            A[3 * i : 3 * i + 3, i] = Kinv @ ap[i]
            A[3 * i : 3 * i + 3, n : n + 3] = -np.eye(3)
            b[3 * i : 3 * i + 3] = R @ aw[i]
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
        return sol[n:], sol[:n]

    best = None
    for sx in (1, -1):
        for sy in (1, -1):
            R = np.column_stack([sx * ex, sy * ey, np.cross(sx * ex, sy * ey)])
            t, lams = solve_t(R)
            if np.any(lams <= 0):  # 锚点须在相机前方
                continue
            err = 0.0
            for i in range(n):
                uv = K @ (R @ aw[i] + t)
                uv = uv[:2] / uv[2]
                err += float(np.hypot(*(uv - ap[i][:2])))
            if best is None or err < best[0]:
                best = (err, R, t)
    if best is None:
        raise ValueError("无有效相机姿态解 (检查锚点/墙线分组)")
    return Camera(K=K, R=best[1], t=best[2])


def _footprint_corners_px(item: dict, room_origin: Point) -> list[Point]:
    """家具落地脚印四角 (绝对像素单位, 未乘 mm)。圆形件用外接方。"""
    ox, oy = room_origin
    if "dcx" in item or "dcy" in item:
        r = float(item.get("r", 20) or 20)
        cx = ox + float(item.get("dcx", 0) or 0)
        cy = oy + float(item.get("dcy", 0) or 0)
        return [(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r)]
    x = ox + float(item.get("dx", 0) or 0)
    y = oy + float(item.get("dy", 0) or 0)
    w = float(item.get("w", 0) or 0)
    h = float(item.get("h", 0) or 0)
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def box_usability(
    cam: Camera, item: dict, room_origin: Point, img_wh: tuple[int, int], *, mm_per_px: float = 10.0
) -> dict:
    """单件盒子的画面可用性 (P0-5 盒子投影检查): 投影 8 顶点判出画比例/近场/相机背后。

    生产实证: 电视柜贴镜头半出画时, 编辑模型会把它塞进背景而非按盒落位。据此给 prompt 降级话术
    ("仅部分可见, 按可见部分落位, 勿补全/勿缩进背景")。
    - usable=False: 盒有顶点在相机背后 (深度<=0), 投影退化不可信。
    - in_frame_frac: 盒投影包围盒落在画面内的面积比 (<1 = 部分出画)。
    - near: 盒底 (地面接触) 触/越画面底边 = 贴镜头近场。仅用底边位置判 (不用高度占比,
      否则远处 2m 高衣柜也会被误判近场)。
    """
    W, H = img_wh
    corners = _footprint_corners_px(item, room_origin)
    hz = _item_height_mm(item)
    pts: list[Point] = []
    behind = False
    for px, py in corners:
        for z in (0.0, hz):
            w = np.array([px * mm_per_px, py * mm_per_px, z], float)
            uv = cam.K @ (cam.R @ w + cam.t)
            d = float(uv[2])
            if d <= 1e-6:
                behind = True
                continue
            pts.append((float(uv[0] / d), float(uv[1] / d)))
    if behind or not pts:
        return {"usable": False, "in_frame_frac": 0.0, "near": True}
    us = [p[0] for p in pts]
    vs = [p[1] for p in pts]
    u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
    area = max(1e-6, (u1 - u0) * (v1 - v0))
    ix = max(0.0, min(u1, W) - max(u0, 0.0))
    iy = max(0.0, min(v1, H) - max(v0, 0.0))
    in_frac = (ix * iy) / area
    # near = 盒底 (最大 v = 最近的地面接触点) 触/越画面底边; 不用高度占比, 否则远处高柜误判。
    near = v1 >= H * 0.98
    return {"usable": True, "in_frame_frac": round(in_frac, 3), "near": bool(near)}


def _box_polys(
    cam: Camera, item: dict, room_origin: Point, mm_per_px: float
) -> list[tuple[float, list[Point]]]:
    """家具 3D 盒子 (footprint + 高度) -> [(相机深度均值, 像素四边形)] 底/顶/4侧面共 6 面。

    深度供画家算法排序 (远 -> 近); footprint_mask 只用多边形, annotate_boxes 两者都用。
    """
    corners = _footprint_corners_px(item, room_origin)
    hz = _item_height_mm(item)

    def pd(px: float, py: float, z: float) -> tuple[Point, float]:
        w = np.array([px * mm_per_px, py * mm_per_px, z], float)
        uv = cam.K @ (cam.R @ w + cam.t)
        return (float(uv[0] / uv[2]), float(uv[1] / uv[2])), float(uv[2])

    base = [pd(px, py, 0.0) for px, py in corners]
    top = [pd(px, py, hz) for px, py in corners]
    faces = [base, top] + [
        [base[i], base[(i + 1) % 4], top[(i + 1) % 4], top[i]] for i in range(4)
    ]
    return [
        (float(np.mean([depth for _, depth in face])), [pt for pt, _ in face])
        for face in faces
    ]


def footprint_mask(
    cam: Camera,
    furniture: list[dict],
    rooms_by_id: dict,
    img_wh: tuple[int, int],
    *,
    mm_per_px: float = 10.0,
    include: set | None = None,
    dilate: int = 0,
):
    """家具 3D 盒子投影合并 -> PIL 'L' mask (白=家具区/待生成, 黑=保留空房)。

    每件家具按 footprint(z=0) + 高度(item.z 或类型默认) 抬成盒子, 投影底/顶/4侧面并集,
    覆盖家具在照片里的立体占据 (不只地面脚印 —— 沙发靠背/壁挂电视都在墙面上)。
    rooms_by_id: {room_id: rect[x,y,w,h] (px)}; include: 只画这些 t 类型 (None=全部);
    dilate: MaxFilter 半径 (>0 时略微外扩, 吃掉家具边缘/接触阴影)。返回 (mask, drawn_count)。
    """
    from PIL import Image, ImageDraw, ImageFilter

    W, H = img_wh
    mask = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(mask)
    drawn = 0
    for it in furniture:
        t = it.get("t")
        if not t or t == "partition":
            continue
        if include is not None and t not in include:
            continue
        rect = rooms_by_id.get(it.get("room_id"))
        if not rect:
            continue
        for _depth, pts in _box_polys(cam, it, (rect[0], rect[1]), mm_per_px):
            draw.polygon(pts, fill=255)
        drawn += 1
    if dilate > 0 and drawn:
        mask = mask.filter(ImageFilter.MaxFilter(dilate * 2 + 1))
    return mask, drawn


# 标注盒调色板: 颜色名进 prompt (编辑模型按 "purple box = dining table" 映射), 顺序稳定。
ANNO_PALETTE: tuple = (
    ("purple", (170, 70, 255)),
    ("blue", (60, 130, 255)),
    ("orange", (255, 150, 30)),
    ("green", (40, 190, 90)),
    ("cyan", (0, 200, 220)),
    ("red", (235, 60, 60)),
    ("yellow", (240, 200, 40)),
    ("magenta", (230, 70, 200)),
)
ANNO_PALETTE_RGB: dict = dict(ANNO_PALETTE)  # 色名 -> RGB (acceptance 残留检测用)


def annotate_boxes(
    cam: Camera,
    furniture: list[dict],
    rooms_by_id: dict,
    photo_png: bytes,
    img_wh: tuple[int, int],
    *,
    mm_per_px: float = 10.0,
    include: set | None = None,
    box_alpha: int = 95,
) -> tuple[bytes, list[dict], int]:
    """空房照上画彩色半透明家具 3D 盒子 (无文字) -> (png_bytes, legend, drawn)。

    家具形体提质核心: 体量/朝向以画面像素进图 (而非平 mask 形状), 指令编辑模型
    (nano-banana) 才画得出立体沙发/餐桌。同类家具共用一色 (L形沙发两段读作一体);
    legend=[{"color","t","count"}] 按首次出现顺序, 供 prompt 生成颜色->家具映射
    (count>1 时 prompt 可写"N pieces", 避免两段沙发被并成一张)。
    跳过 partition (非家具) 与 rug (平盒污染标注, 地毯走 prompt 文字)。
    """
    from PIL import Image, ImageDraw

    W, H = img_wh
    photo = Image.open(io.BytesIO(photo_png)).convert("RGBA")
    if photo.size != (W, H):
        photo = photo.resize((W, H))
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    color_by_type: dict = {}
    legend: list[dict] = []
    faces: list[tuple[float, list[Point], tuple]] = []
    drawn = 0
    for it in furniture:
        t = it.get("t")
        if not t or t in ("partition", "rug"):
            continue
        if include is not None and t not in include:
            continue
        rect = rooms_by_id.get(it.get("room_id"))
        if not rect:
            continue
        if t not in color_by_type:
            name, rgb = ANNO_PALETTE[len(color_by_type) % len(ANNO_PALETTE)]
            color_by_type[t] = (name, rgb)
            legend.append({"color": name, "t": t, "count": 0})
        entry = next(e for e in legend if e["t"] == t)
        entry["count"] += 1
        # P0-5 盒子可用性: 逐件判出画/近场, 聚合到该类型 legend 条目 (任一件命中即标记),
        # 供 _geometry_lock_prompt 给该盒降级话术。
        u = box_usability(cam, it, (rect[0], rect[1]), img_wh, mm_per_px=mm_per_px)
        if not u["usable"] or u["in_frame_frac"] < 0.85:
            entry["partial"] = True
        if u["near"]:
            entry["near"] = True
        rgb = color_by_type[t][1]
        for depth, pts in _box_polys(cam, it, (rect[0], rect[1]), mm_per_px):
            faces.append((depth, pts, rgb))
        drawn += 1
    for _depth, pts, rgb in sorted(faces, key=lambda f: -f[0]):  # 画家算法: 远 -> 近
        draw.polygon(pts, fill=rgb + (box_alpha,), outline=rgb + (255,))
    out = Image.alpha_composite(photo, overlay).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue(), legend, drawn
