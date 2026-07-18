# -*- coding: utf-8 -*-
"""透视标定 + 家具几何投影 (路线A P2, 纯 numpy)。

带透视的实拍空房照 -> 相机 (K,R,t) -> 家具 3D 盒子投影 -> footprint mask。
标定输入 (用户在 UI 提供): 两组正交地面墙线 (各 >=2 条平行, 求 2 个消失点) + >=2 个地面锚点
(world mm z=0 <-> 像素)。消失点给相机朝向/焦距 (透视越强越准, 与"带透视更好看"
同向); 锚点给绝对定位并消解姿态符号歧义。自动消失点检测 (cv2) 属可选增强, 不是本模块的必需依赖。

世界系约定: X=毫米东(+), Y=毫米南(+), Z=上(+); 地面 z=0。

注意 (East, South, Up) 是**左手系** (East x South = Down, 不是 Up), 而相机系 (右,下,前)
是右手系 => 物理正确的 world->camera R 必然 **det(R) = -1**, 这不是缺陷。故 calibrate()
的姿态 z 列取 `-cross(x_col, y_col)`; 若"修正"成 `+cross` 会强制 det=+1, 使 z 列在 x/y
拟合正确时系统性取反 (calib-z-b1 根因: 相机被解到地板下方, 挂画被画在地板上)。det=-1 仍是
精确正交阵, 下游只用 `R @ w + t` 投影, 不依赖手性。
"""

from __future__ import annotations

import io
import os
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


# 实拍世界的层高 (mm)。⚠ 与 axon/scene 的 WALL_H=1450 **无关** —— 见下方两世界警告。
# 生产实测支持 (calib-z-b1): 地面点投 v=1161, z=+2700 投 v=571 = 天花板方向。
_REAL_CEILING_MM = 2700

# 家具默认盒**顶面绝对高度** (mm), item.z 优先 (为何不是"高度": 见 item_top_z_mm docstring)。
#
# ⚠⚠ 本仓有**两个 z 世界, 数字不得互借** (decor-envelope-b1 根因):
#   * 本模块 (perspective / 实拍照片) = **真实毫米**世界, 层高 _REAL_CEILING_MM = 2700。
#     铁证: 下表的 wardrobe/bookshelf = 2000mm —— 在压扁世界里根本立不住。
#   * floorplan_core 的 axon / scene (轴测 dollhouse) = 为看清室内**刻意压扁**的世界:
#     WALL_H = 1450, 家具被 scene 钳到 1400, D 户型 geometry.meta.wall_height_mm 也是 1450。
#   本模块**不 import floorplan_core**, 两边各写各的硬编码 —— 所谓"对齐"从来只是注释里的
#   愿望, 无任何机制保证; 而且**本就不应该对齐**, 两个世界的层高本来就不同。
#
# 本处原写: "decor-b2: wall_art/curtain 顶高对齐 axon SPECS 渲染画框 z (挂画顶 1400,
# 窗帘顶 1450)" —— 那句话正是 bug 本身。axon SPECS 的窗帘 = 帘头 z:(1400,1450) + 长幔
# z:(150,1400), 在 1450 的压扁墙里是"占 90% 墙高的落地帘"(dollhouse 里正确); 被逐字照抄
# 进真实毫米世界后, 在层高 2700 的照片上变成"从脚踝到胸口的下半墙", 比模型实际画的落地帘
# 矮约 1.25m -> 帘子上半截全落在 allowed 外 -> 每次出图都报"盒区外出现新结构"(误报)。
# 而 catalog 的 prompt 词条正是 "floor-length curtains", 南墙窗又被 axon 强制判落地窗 ——
# 模型照做画了天花垂到地面的帘子, 是**盒子**错了, 不是模型错了。
#
# curtain: 落地帘 = 帘杆在天花 -> 顶 = 层高; 底 = 0 (见 _ITEM_Z0_MM)。
# wall_art: 1400 保留, 但**已知欠建模** (模型实测画约 750mm 高的画, 盒只建模 400mm) ——
#   改盒 = 改引导图 = 改模型输出, 须 [L2] 真实出图验证 -> BL-wall-art-box-undermodeled。
_DEFAULT_HEIGHT_MM = {
    "sofa": 800, "bed": 500, "media": 550, "tv": 1200, "coffee_table": 420,
    "dining_table": 760, "cabinet": 850, "wardrobe": 2000, "desk": 750,
    "chair": 900, "nightstand": 500, "bookshelf": 2000, "rug": 8, "plant": 900,
    "wall_art": 1400, "curtain": _REAL_CEILING_MM,
}

# 悬空/贴墙件盒底面高度 (mm)。挂画从墙面带 1000 起 (非地面 0)。
# 其余件不在表内 -> z0 = 0 (地面), 与既有投影逐字节一致 (byte-safe)。
# curtain 曾是 150 (照抄 axon 长幔的 z0) —— 已移除: 落地帘触地, z0 = 0 才是实拍世界的实情,
# 也正是 catalog 那句 "floor-length curtains" 的意思。
_ITEM_Z0_MM = {"wall_art": 1000}


def item_top_z_mm(item: dict) -> float:
    """盒**顶面的绝对高度** (mm), item.z 优先。

    ⚠ 不是"高度差": _box_polys 的底面在 _item_z0_mm(item), 顶面在本函数的返回值。
    对地面件 (z0=0) 两者数值相同, 故旧名 `_item_height_mm` 长期不显误导; 对墙面带件
    (挂画/窗帘, z0>0) 才暴露。acceptance 的 allowed 上沿由本函数派生 (单一真源)。
    """
    z = item.get("z")
    if isinstance(z, (int, float)) and not isinstance(z, bool) and z > 0:
        return float(z)
    return float(_DEFAULT_HEIGHT_MM.get(item.get("t"), 600))


def _item_z0_mm(item: dict) -> float:
    """盒底面高度 (mm): 悬空/贴墙件从墙面带起, 其余从地面 0 (审查 #1 逐件派生)。"""
    return float(_ITEM_Z0_MM.get(item.get("t"), 0.0))


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


def _solve_poses(
    x_lines: list[Line],
    y_lines: list[Line],
    anchors: list[tuple[tuple[float, float, float], Point]],
    *,
    img_wh: tuple[int, int],
) -> tuple[np.ndarray, list[tuple[float, np.ndarray, np.ndarray]]]:
    """枚举 4 个符号候选并作物理筛选 -> (K, [(err, R, t), ...])。

    calib-z-b1 F001 从 calibrate() 提取, 使"物理门后候选唯一"可被单测直接断言 ——
    这是本 bug 的根因锁: 2 锚点时若门后仍剩 2 个候选, 胜负就回落到浮点噪声上 (见下)。
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

    out: list[tuple[float, np.ndarray, np.ndarray]] = []
    for sx in (1, -1):
        for sy in (1, -1):
            # z 列 = -cross(x,y): 世界系 (X=东, Y=南, Z=上) 是**左手系** (East x South =
            # Down), 而相机系 (右,下,前) 是右手系 => 物理正确的 R 必然 det = -1。写成
            # +cross(x,y) 会强制 det=+1, 于是 x/y 拟合正确时 z 列被系统性取反 —— 相机
            # 解到地板下方, 家具盒朝地下拉伸, 挂画画在地板上 (calib-z-b1 根因)。
            R = np.column_stack([sx * ex, sy * ey, -np.cross(sx * ex, sy * ey)])
            t, lams = solve_t(R)
            if np.any(lams <= 0):  # 约束①: 锚点须在相机前方
                continue
            # 约束②: 相机必须在地板上方 (C = -R^T t 的 z 分量 > 0)。这是地面锚点**给不了**
            # 而物理**必然成立**的约束 —— 两条打分约束全部只用地面锚点 (z=0), 对地面点
            # R@w 中 z 列恒被乘 0 => 对打分零贡献。缺了它, 2 锚点时两个候选的重投影 err
            # 精确平局 (生产实测相对差仅 1e-13~1e-16), z 朝上朝下由浮点噪声抛硬币定
            # (铁证: 同一份存量输入换台机器重算即得相反的 z)。
            if float((-R.T @ t)[2]) <= 0:
                continue
            err = 0.0
            for i in range(n):
                uv = K @ (R @ aw[i] + t)
                uv = uv[:2] / uv[2]
                err += float(np.hypot(*(uv - ap[i][:2])))
            out.append((err, R, t))
    return K, out


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
    被 t 拟合到 0 无法区分 sign, 故要求 >=2)。姿态候选的枚举与物理筛选见 _solve_poses。
    """
    K, cands = _solve_poses(x_lines, y_lines, anchors, img_wh=img_wh)
    if not cands:
        # 诚实报错优于产出一台在地板下方的相机 (错图很隐蔽: auto_check 也检不出)。
        raise ValueError(
            "无物理有效的相机姿态解 (无候选满足『锚点在相机前方』且『相机在地板上方』); "
            "检查锚点世界坐标/像素对应与墙线分组"
        )
    best = min(cands, key=lambda c: c[0])
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
    hz = item_top_z_mm(item)
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


# render-fix-b1 F001 近平面 (mm): 相机前方此距离内的盒顶点投影不可信 —— 除以 ~0/负深度会让
# 多边形穿过相机翻转、炸开到 ~1e5 px 糊死整幅引导图 (生产实证: 贴窗 curtain 盒 minDepth=-55mm
# → 投影 u:-8903..6580 v:-47843..111194, 覆盖全画幅把餐桌等所有盒埋掉)。室内照相机前 1cm 内
# 无有意义几何, 故按此平面在相机系裁剪后再投影: 部分可见的盒只画可见部分 (勿整件丢弃 —— 贴镜头
# 的窗帘/电视柜仍需盒引导), 整面在背后的丢弃。
NEAR_MM = 10.0


def _clip_face_near(face_cam: list, near: float) -> list:
    """单平面 Sutherland-Hodgman (相机系): 保留 z >= near 的部分, 跨平面的边线性插值取交点。

    面完全在近平面之前 -> 原样返回 (顶点对象与顺序逐字不变), 使投影结果 byte-safe。
    """
    out: list = []
    n = len(face_cam)
    for i in range(n):
        a = face_cam[i]
        b = face_cam[(i + 1) % n]
        za, zb = float(a[2]), float(b[2])
        a_in, b_in = za >= near, zb >= near
        if a_in:
            out.append(a)
        if a_in != b_in:  # 跨近平面 -> 插入交点
            t = (near - za) / (zb - za)
            out.append(a + t * (b - a))
    return out


def _box_polys(
    cam: Camera, item: dict, room_origin: Point, mm_per_px: float
) -> list[tuple[float, list[Point]]]:
    """家具 3D 盒子 (footprint + 高度) -> [(相机深度均值, 像素多边形)] 底/顶/4侧面共 6 面。

    深度供画家算法排序 (远 -> 近); footprint_mask 只用多边形, annotate_boxes 两者都用。
    F001: 顶点先求相机系坐标, 按 NEAR_MM 裁剪, 存活顶点再乘 K 投影 (裁剪必须在投影前 ——
    投影后的坐标已丢失深度符号信息, 无法补救)。盒全在近平面之前时裁剪为 no-op, 逐字节等价。
    """
    corners = _footprint_corners_px(item, room_origin)
    z0 = _item_z0_mm(item)  # decor-b2: 逐件底面 (挂画/窗帘墙面带; 其余 0 保既有字节)
    hz = item_top_z_mm(item)

    def cpt(px: float, py: float, z: float):
        """世界 px -> 相机系 (不乘 K: 裁剪在投影前做)。"""
        w = np.array([px * mm_per_px, py * mm_per_px, z], float)
        return cam.R @ w + cam.t

    base = [cpt(px, py, z0) for px, py in corners]
    top = [cpt(px, py, hz) for px, py in corners]
    faces = [base, top] + [
        [base[i], base[(i + 1) % 4], top[(i + 1) % 4], top[i]] for i in range(4)
    ]
    out: list[tuple[float, list[Point]]] = []
    for face in faces:
        clipped = _clip_face_near(face, NEAR_MM)
        if len(clipped) < 3:
            continue  # 整面在近平面之后 (相机背后) -> 不画, 投影不可信
        pts: list[Point] = []
        depths: list[float] = []
        for c in clipped:
            uv = cam.K @ c
            pts.append((float(uv[0] / uv[2]), float(uv[1] / uv[2])))
            depths.append(float(uv[2]))
        out.append((float(np.mean(depths)), pts))
    return out


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
# render-fix-b1 F002: 由 8 色扩到 14 色。原 8 色不够单房现实类型数 —— 生产实证 r_live 跳过 rug
# 后有 9 类 (dining_table/sofa/coffee_table/media/entry_door/wine_cabinet/wall_art/curtain/plant),
# 旧代码 `% len(ANNO_PALETTE)` 静默回绕 -> 第9类 plant 撞第1类 dining_table 同为 purple,
# prompt 并存 "purple box = 餐桌" 与 "purple boxes = 绿植(3个)" -> 画面 4 个紫盒语义不可区分,
# 模型只能自行猜 -> 餐桌落位错。前 8 色顺序与取值保持不变 (既有 legend/测试字节安全)。
ANNO_PALETTE: tuple = (
    ("purple", (170, 70, 255)),
    ("blue", (60, 130, 255)),
    ("orange", (255, 150, 30)),
    ("green", (40, 190, 90)),
    ("cyan", (0, 200, 220)),
    ("red", (235, 60, 60)),
    ("yellow", (240, 200, 40)),
    ("magenta", (230, 70, 200)),
    ("lime", (160, 230, 50)),
    ("brown", (140, 85, 45)),
    ("teal", (0, 135, 130)),
    ("navy", (35, 55, 150)),
    ("pink", (255, 150, 180)),
    ("maroon", (135, 30, 65)),
)
ANNO_PALETTE_RGB: dict = dict(ANNO_PALETTE)  # 色名 -> RGB (acceptance 残留检测用)

# 不画标注盒的类型: partition/entry_door 是结构件 (不入家具目录 -> 无 en, 无法向编辑模型描述);
# rug 是平盒会污染标注 (decor-b2 D4, 走 prompt 文字)。
ANNO_SKIP_TYPES: frozenset = frozenset({"partition", "rug", "entry_door"})


# render-fix-b1 F003: 单个标注盒在画幅内的覆盖占比超过此值 = 引导图退化。正常构图下没有任何
# 单件家具会罩死整幅画面 (贴镜头的 3m 餐桌/L 形沙发也远不到)。
GUIDE_SINGLE_BOX_MAX_FRAME_FRAC = 0.9
_GUIDE_PROBE_WH = (256, 192)  # 覆盖率只需量级判断, 低分辨率探针即可 (整幅栅格太贵)

# calib-cure-b1 F006: 聚合出画检查 —— 单件盒可用性低于此 in_frame_frac 记"基本不在画面内";
# 此类件数占比 > 1/3 = 相机标定与场景整体不符 (f4d 生产病灶: 12 件 5 件全出画, 模型只能自由
# 发挥, auto_check 背景保真照样 0.967 通过)。件数 < _MIN_ITEMS 不判 (单件房间半出画是合法构图)。
GUIDE_OFFFRAME_IN_FRAME_FRAC = 0.15
GUIDE_OFFFRAME_MIN_ITEMS = 3


def guide_sanity_issues(
    cam: Camera,
    furniture: list[dict],
    rooms_by_id: dict,
    img_wh: tuple[int, int],
    *,
    mm_per_px: float = 10.0,
    include: set | None = None,
) -> list[str]:
    """送 AI 前的引导图健全性检查 (确定性输入侧, 不调 AI 不花钱)。返回问题列表 (空=健全)。

    盒穿过相机平面的炸开已由 _box_polys 近平面裁剪根治; 本函数是防御纵深 —— 相机陷在家具体内 /
    标定与家具位置严重不符时, 单盒仍可能罩死画面, 使引导图失去位置信息 (生产实证: 这类失败
    auto_check 检不出, 会静默出错图烧预算)。判据用画幅内实际覆盖率, 不用原始包围盒 ——
    近平面裁剪后的合法盒 (如相机贴脸的窗帘) 坐标本就很大但画幅内几乎不覆盖, 不得误拦。
    """
    from PIL import Image, ImageDraw

    W, H = img_wh
    pw, ph = _GUIDE_PROBE_WH
    sx, sy = pw / float(W), ph / float(H)
    issues: list[str] = []
    offframe = 0  # F006: "基本不在画面内"的件数 (含相机背后的不可用盒)
    total = 0
    for it in furniture:
        t = it.get("t")
        if not t or t in ANNO_SKIP_TYPES:
            continue
        if include is not None and t not in include:
            continue
        rect = rooms_by_id.get(it.get("room_id"))
        if not rect:
            continue
        u = box_usability(cam, it, (rect[0], rect[1]), img_wh, mm_per_px=mm_per_px)
        total += 1
        if (not u["usable"]) or u["in_frame_frac"] < GUIDE_OFFFRAME_IN_FRAME_FRAC:
            offframe += 1
        polys = _box_polys(cam, it, (rect[0], rect[1]), mm_per_px)
        if not polys:
            continue
        probe = Image.new("L", (pw, ph), 0)
        pd = ImageDraw.Draw(probe)
        for _depth, pts in polys:
            pd.polygon([(x * sx, y * sy) for x, y in pts], fill=255)
        frac = sum(1 for v in probe.getdata() if v) / float(pw * ph)
        if frac > GUIDE_SINGLE_BOX_MAX_FRAME_FRAC:
            issues.append(
                f"家具 {t} 的标注盒覆盖了 {frac * 100:.0f}% 画面 —— 相机标定与该家具位置"
                "严重不符 (相机可能陷在家具体内), 引导图无有效位置信息"
            )
    # F006 聚合出画检查: 多数家具投到画外 = 位姿整体错误 (逐件检查看不出, f4d 病灶)。
    if total >= GUIDE_OFFFRAME_MIN_ITEMS and offframe * 3 > total:
        issues.append(
            f"{offframe}/{total} 件家具的标注盒基本不在画面内 —— 相机标定与场景严重不符, "
            "引导图无有效位置信息"
        )
    return issues


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
    跳过 partition (非家具) 与 rug (平盒污染标注, 走 prompt 文字)。decor-b2: 挂画/窗帘不再全跳
    (b1-F008 曾隔离兜底) —— 用墙面带 z0 画盒进 legend, 完整接入第7步; 附着件藏宿主 decor 不进盒。
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
        # decor-b2 D4: skip 字面 {partition, rug} (不复用 SOFT_DECOR_TYPES) ——
        # wall_art/curtain 用墙面带 z0 画盒进 legend; 附着件不作顶层 item 故不涉及。
        # render-fix-b1 F002: 增 entry_door —— 结构件不入目录 (无 en), 画了盒 prompt 只能写
        # "cyan box = entry_door" 把原始标识符漏进英文指令 (生产实证), 且它本非可落位家具。
        if not t or t in ANNO_SKIP_TYPES:
            continue
        if include is not None and t not in include:
            continue
        rect = rooms_by_id.get(it.get("room_id"))
        if not rect:
            continue
        if t not in color_by_type:
            # F002: 去掉静默回绕 (`% len(ANNO_PALETTE)`) —— 耗尽即报错阻断。错图比不出图更贵:
            # 烧 AI 预算 + 误导用户, 且颜色歧义导致的落位错很隐蔽 (auto_check 也检不出)。
            if len(color_by_type) >= len(ANNO_PALETTE):
                raise ValueError(
                    f"标注盒调色板耗尽: 该房间家具类型数 > {len(ANNO_PALETTE)} 色，"
                    "无法给每类分配唯一颜色；颜色歧义会导致落位错乱，故拒绝出图。"
                    "请减少该房间家具类型或扩充 ANNO_PALETTE。"
                )
            name, rgb = ANNO_PALETTE[len(color_by_type)]
            color_by_type[t] = (name, rgb)
            legend.append({"color": name, "t": t, "count": 0})
        entry = next(e for e in legend if e["t"] == t)
        entry["count"] += 1
        # P0-5 盒子可用性: 逐件判出画/近场, 聚合到该类型 legend 条目 (任一件命中即标记),
        # 供 _geometry_lock_prompt 给该盒降级话术。
        u = box_usability(cam, it, (rect[0], rect[1]), img_wh, mm_per_px=mm_per_px)
        if not u["usable"] or u["in_frame_frac"] < 0.85:
            entry["partial"] = True
            # F006: 记录该类型各件的最小画内占比 (仅在有件出画时写键 —— 全可见 legend 字节不变)。
            # prompt 层据此禁止 near×几乎不可见 的矛盾话术 (f4d: 0% 可见的餐桌被令"前景全尺寸")。
            frac = u["in_frame_frac"] if u["usable"] else 0.0
            entry["min_in_frame"] = min(entry.get("min_in_frame", 1.0), frac)
        if u["near"]:
            entry["near"] = True
        rgb = color_by_type[t][1]
        for depth, pts in _box_polys(cam, it, (rect[0], rect[1]), mm_per_px):
            faces.append((depth, pts, rgb))
        drawn += 1
    # F002 防御纵深: 颜色 -> 家具映射必须单射。撞色会让 prompt 并存两条同色映射 (生产实证:
    # "purple box = 餐桌" 与 "purple boxes = 绿植(3个)" 同存), 模型无从区分 -> 落位错。
    _colors = [e["color"] for e in legend]
    if len(_colors) != len(set(_colors)):
        raise ValueError(f"标注盒 legend 出现重复颜色 {_colors}: 颜色->家具映射歧义，拒绝出图。")
    for _depth, pts, rgb in sorted(faces, key=lambda f: -f[0]):  # 画家算法: 远 -> 近
        draw.polygon(pts, fill=rgb + (box_alpha,), outline=rgb + (255,))
    out = Image.alpha_composite(photo, overlay).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue(), legend, drawn


# ---- 标定质量评估 (calib-cure-b1 F003, spec §D1) ----------------------------------
# 硬门阈值: 越线即 ok=False。保存 400 / 渲染 409 / dry-run 预览三处共用本函数 —— 单一真源,
# 不得在调用点另写阈值。reproj 依据: 诚实点击噪声 σ=8px 下 2 锚点自报误差 P90≈23px
# (标定功能缺陷核查 20260717 实验一), 取 2 倍余量; 生产病例 112/2353/123.9px 全部越线。
CALIB_MAX_REPROJ_PX = 50.0  # env CALIB_MAX_REPROJ_PX 覆盖 (escape hatch, 应急放宽用)
CALIB_GOOD_REPROJ_PX = 25.0  # UI 评级 good/suspect 分界 (不参与 ok 判定)
CAMERA_Z_RANGE_MM = (800.0, 2200.0)  # 人手持高度; 生产病例 f4d 解出 399mm(膝下) 即此翻车
HFOV_RANGE_DEG = (35.0, 110.0)  # 手机镜头合理水平视场; f 越界 = 消失点(墙线)画错了
# 软信号 (不 fail, 只进 reasons + level 降 suspect): 相机离绑定房 merge 并集过远 -> 可能
# 绑错房间。站门口/相邻房拍大景是合法姿势 (既有合成 fixture 离并集 ~1950mm), 且该检查的
# 动机案例 798 离房仅 474mm 本就拦不住 —— 故只提示不拦 (2026-07-17 pre-impl 裁决, spec §D1)。
CAMERA_ROOM_SOFT_DIST_MM = 1500.0


def _max_reproj_px() -> float:
    """硬门阈值 (调用时读 env, 便于测试与应急覆盖; 非法值回落默认)。"""
    raw = os.environ.get("CALIB_MAX_REPROJ_PX", "")
    try:
        return float(raw) if raw else CALIB_MAX_REPROJ_PX
    except ValueError:
        return CALIB_MAX_REPROJ_PX


def _point_rect_dist_mm(px: float, py: float, rect: tuple) -> float:
    """水平点到轴对齐矩形 (x0,y0,x1,y1)mm 的距离 (在内=0)。"""
    x0, y0, x1, y1 = rect
    dx = max(x0 - px, 0.0, px - x1)
    dy = max(y0 - py, 0.0, py - y1)
    return float(np.hypot(dx, dy))


def assess_calibration_quality(
    cam: Camera,
    anchors: list,
    *,
    room_rects_mm: tuple | list = (),
    img_wh: tuple | None = None,
) -> dict:
    """标定质量评估 -> {ok, level, reasons, metrics} (spec §D1, 2026-07-17 裁决版)。

    硬门 (任一越线 ok=False): 锚点重投影误差 RMS (F005, 非取最大) / 相机高度 / 水平视场角。
    软信号 (只记 reasons, level 降 suspect): 相机离绑定房 merge 并集 > 1500mm。
    anchors: [{"world":[x,y,z], "px":[u,v]}, ...] (标定 payload / 存量载荷同形)。
    room_rects_mm: merge 组成员矩形 [(x0,y0,x1,y1)mm]; 空 = 跳过离房软信号 (降级不失效)。
    img_wh: 缺省时跳过 HFOV 检查 (metrics.hfov_deg=None)。
    """
    reasons: list[str] = []
    errs: list[float] = []
    for a in anchors or []:
        try:
            w, p = a["world"], a["px"]
            u, v = cam.project(float(w[0]), float(w[1]), float(w[2]))
            errs.append(float(np.hypot(u - float(p[0]), v - float(p[1]))))
        except Exception:  # noqa: BLE001 - 单个畸形锚点按缺失处理 (整体走"缺锚点"硬失败)
            errs = []
            break
    # F005: 门与评级用**稳健指标 RMS** (非取最大) —— 一个点没点准不整体判死; 真歪相机所有点
    # 全偏 -> RMS≈max 仍被拦 (门仍诚实)。reproj_max 供单点离群另标。
    if errs:
        _arr = np.asarray(errs, float)
        reproj = round(float(np.sqrt(np.mean(_arr**2))), 1)  # RMS
        reproj_max = round(float(_arr.max()), 1)
    else:
        reproj = reproj_max = None
    limit = _max_reproj_px()
    ok = True
    if reproj is None:
        ok = False
        reasons.append("标定载荷缺有效锚点, 无法评估重投影误差 — 请重新标定")
    elif reproj > limit:
        ok = False
        reasons.append(
            f"锚点重投影误差(RMS) {reproj}px 超过阈值 {limit:g}px — 标定输入与解算相机不自洽, "
            "请检查锚点/墙线后重新标定"
        )
    elif reproj_max is not None and reproj_max > 2.0 * limit and reproj_max > 2.5 * reproj:
        # 整体 RMS 达标但某单点明显离群 -> 软信号 (level 降 suspect, 不整体判死): 只需修那个点。
        reasons.append(
            f"有一个特征点明显偏离(单点误差 {reproj_max}px, 整体 RMS {reproj}px) — "
            "多数点自洽, 建议重点复核并重标这个点"
        )
    cz = float((-cam.R.T @ cam.t)[2])
    if not (CAMERA_Z_RANGE_MM[0] <= cz <= CAMERA_Z_RANGE_MM[1]):
        ok = False
        reasons.append(
            f"解算相机高度 {cz:.0f}mm 不在手持拍摄范围 "
            f"[{CAMERA_Z_RANGE_MM[0]:.0f}, {CAMERA_Z_RANGE_MM[1]:.0f}]mm — 姿态不可信, 请重新标定"
        )
    hfov = None
    if img_wh:
        hfov = round(float(2.0 * np.degrees(np.arctan((float(img_wh[0]) / 2.0) / cam.focal))), 1)
        if not (HFOV_RANGE_DEG[0] <= hfov <= HFOV_RANGE_DEG[1]):
            ok = False
            reasons.append(
                f"解算水平视场角 {hfov}° 不在合理范围 [{HFOV_RANGE_DEG[0]:.0f}, "
                f"{HFOV_RANGE_DEG[1]:.0f}]° — 两组墙线方向可能画错"
            )
    dist = None
    if room_rects_mm:
        C = -cam.R.T @ cam.t
        dist = round(
            min(_point_rect_dist_mm(float(C[0]), float(C[1]), r) for r in room_rects_mm), 1
        )
        if dist > CAMERA_ROOM_SOFT_DIST_MM:
            reasons.append(
                f"相机似在离绑定房间 {dist / 1000:.1f}m 处拍摄 — 若非站相邻房间取景, "
                "请确认照片的房间绑定是否正确"
            )
    good = (
        ok
        and not reasons
        and reproj is not None
        and reproj < CALIB_GOOD_REPROJ_PX
    )
    level = "bad" if not ok else ("good" if good else "suspect")
    return {
        "ok": ok,
        "level": level,
        "reasons": reasons,
        "metrics": {
            "reproj_px": reproj,  # F005: RMS (稳健), 门与评级用
            "reproj_max_px": reproj_max,  # 最差单点 (离群透明化)
            "camera_z_mm": round(cz, 1),
            "camera_room_dist_mm": dist,
            "hfov_deg": hfov,
        },
    }
