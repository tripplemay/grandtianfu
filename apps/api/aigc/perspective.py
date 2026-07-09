# -*- coding: utf-8 -*-
"""透视标定 + 家具几何投影 (路线A P2, 纯 numpy)。

带透视的实拍空房照 -> 相机 (K,R,t) -> 家具 3D 盒子投影 -> footprint mask。
标定输入 (用户在 UI 提供): 两组正交地面墙线 (各 >=2 条平行, 求 2 个消失点) + >=2 个地面锚点
(world mm z=0 <-> 像素)。消失点给相机朝向/焦距 (透视越强越准, 与"带透视更好看"
同向); 锚点给绝对定位并消解姿态符号歧义。自动消失点检测 (cv2) 属可选增强, 不是本模块的必需依赖。

世界系约定: X=毫米东(+), Y=毫米南(+), Z=上(+); 地面 z=0。
"""

from __future__ import annotations

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


def footprint_mask(
    cam: Camera,
    furniture: list[dict],
    rooms_by_id: dict,
    img_wh: tuple[int, int],
    *,
    mm_per_px: float = 10.0,
    include: set | None = None,
):
    """家具落地脚印投影合并 -> PIL 'L' mask (白=家具区/待生成, 黑=保留空房)。

    rooms_by_id: {room_id: rect[x,y,w,h] (px)}; furniture: 平面家具表 (dx/dy 相对房 px)。
    include: 只画这些 t 类型 (None=全部)。返回 (mask, drawn_count)。
    """
    from PIL import Image, ImageDraw

    W, H = img_wh
    mask = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(mask)
    drawn = 0
    for it in furniture:
        t = it.get("t")
        if not t or it.get("t") == "partition":
            continue
        if include is not None and t not in include:
            continue
        rect = rooms_by_id.get(it.get("room_id"))
        if not rect:
            continue
        corners = _footprint_corners_px(it, (rect[0], rect[1]))
        poly = [cam.project(px * mm_per_px, py * mm_per_px, 0.0) for px, py in corners]
        draw.polygon(poly, fill=255)
        drawn += 1
    return mask, drawn
