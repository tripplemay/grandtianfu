# -*- coding: utf-8 -*-
"""mask 区域估计 (render-mask-b1 F001, spec §D1/D3): VLM 把「可改动区域」划成多边形 -> 栅格 mask。

背景: 整图编辑模型 (gpt-image-2) 锁不住背景 (route-eval §4); mask 级编辑 (fal flux inpaint)
需要「哪里可以画」的区域输入。本模块用 VLM 从照片估计区域 (无需标定): 地面 (必有) / 窗墙
(有窗帘时) / 挂画墙 (有挂画时), 栅格化为 'L' mask, 供 inpaint 与合成使用。

诚实边界 (spec §D3, 开工前调查实测): VLM 区域精度「够用但不完美」—— 地面贴墙脚线较好,
窗墙较粗。故健全门 (顶点/图内/面积占比/自交) 是硬要求: floor 不过 -> 整体降级 (degraded,
调用方走 relational 无 mask 路径); 可选区不过 -> 只丢该区 (其余照常, 记录原因)。不抛不阻断。

chat_json 由调用方依赖注入 (同 semantic_accept 模式), 本模块可离线单测。
"""

from __future__ import annotations

import base64
import io
from typing import Callable

# 健全门阈值 (spec §D3): floor 面积占画面比例; 可选区占比上下限; 顶点坐标容差 (越界少许可夹取)。
_FLOOR_MIN_FRAC = 0.05
_FLOOR_MAX_FRAC = 0.80
_OPT_MIN_FRAC = 0.01
_OPT_MAX_FRAC = 0.85
_COORD_TOL = 0.02
# 羽化半径 (px): 合成边缘渐变, 只向 mask 内羽化 (mask 外保持字节即原图, spec §D1)。
FEATHER_PX = 8

_ZONE_DESC = {
    "floor": "可见地面区域（家具将摆放的地板面）—— 沿墙脚线/地脚线围出的多边形，通常 4-8 个顶点",
    "window_wall": "窗户所在的墙面区域（含窗框/玻璃，用于窗帘挂载）—— 没有明显窗户则给 null",
    "art_wall": "需要挂装饰画的墙面区域（在画面中的可见部分）—— 没有需要挂画的墙则给 null",
}


def _b64(png: bytes) -> str:
    return base64.b64encode(png).decode()


def _downscale(png: bytes, max_side: int = 1024) -> bytes:
    from PIL import Image

    im = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = im.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _seg_intersect(a, b, c, d) -> bool:
    """线段 ab 与 cd 是否相交 (含共线重叠的保守判定: 用跨立实验)。"""

    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    d1 = cross(c, d, a)
    d2 = cross(c, d, b)
    d3 = cross(a, b, c)
    d4 = cross(a, b, d)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _self_intersecting(poly: list) -> bool:
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        for j in range(i + 1, n):
            # 跳过相邻边 (共享顶点)
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            c, d = poly[j], poly[(j + 1) % n]
            if _seg_intersect(a, b, c, d):
                return True
    return False


def _poly_area_frac(poly: list) -> float:
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _check_poly(poly, *, min_frac: float, max_frac: float) -> str | None:
    """单个多边形健全检查 -> 错误原因 or None。坐标越界少许可夹取 (调用方先夹)。"""
    if not isinstance(poly, list) or len(poly) < 3:
        return "顶点不足 (需 >=3)"
    pts = []
    for p in poly:
        if not (isinstance(p, (list, tuple)) and len(p) == 2):
            return "顶点格式非法"
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError):
            return "顶点坐标非数值"
        pts.append((x, y))
    if any(
        x < -_COORD_TOL or x > 1 + _COORD_TOL or y < -_COORD_TOL or y > 1 + _COORD_TOL
        for x, y in pts
    ):
        return "顶点越出画面"
    if _self_intersecting(pts):
        return "多边形自交"
    frac = _poly_area_frac(pts)
    if not (min_frac <= frac <= max_frac):
        return f"面积占比 {frac:.1%} 超出合理范围 [{min_frac:.0%}, {max_frac:.0%}]"
    return None


def estimate_zones(
    photo_png: bytes,
    needs: set,
    chat_json: Callable,
    *,
    frame: str | None = None,
    hints: list | None = None,
) -> dict:
    """VLM 区域估计 -> {zones, degraded, reason, dropped}。

    needs: {"floor"} | {"floor","window_wall",...}; frame: placement_brief 的画面四至文案
    (辅助 VLM 定位); hints: 与窗帘/挂画相关的约束原文 (指明窗墙/挂画墙是哪面)。
    floor 缺失/不合法 -> degraded=True (调用方走 relational 无 mask 路径); 可选区不合法
    -> 只丢该区 (dropped 记录), 其余照常。VLM 异常 -> 整体降级 (不抛)。"""
    needs = {n for n in (needs or {"floor"}) if n in _ZONE_DESC} or {"floor"}
    zone_lines = "\n".join(f"  - {k}: {_ZONE_DESC[k]}" for k in sorted(needs))
    hint_txt = ""
    if hints:
        hint_txt = "\n参考信息 (方案里与这些区域相关的约束): " + "；".join(
            str(h) for h in hints[:6]
        )
    frame_txt = f"\n辅助定位: {frame}" if frame else ""
    prompt = (
        "这是一张空房实拍照片。请估计下列区域的边界多边形 "
        "(归一化坐标 [0.000,1.000], 原点左上, x 向右 y 向下):\n"
        f"{zone_lines}\n"
        "要求: 多边形 3-10 个顶点, 沿可见边界 (墙脚线/窗框) 走, 不要自交。"
        f"{frame_txt}{hint_txt}\n"
        '只输出 JSON: {"floor": [[x,y],...], "window_wall": [[x,y],...] | null, ...}'
        " (未列出的区域键给 null)"
    )
    try:
        out = chat_json(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{_b64(_downscale(photo_png))}"
                            },
                        },
                    ],
                }
            ]
        )
    except Exception as exc:  # noqa: BLE001 - VLM 异常整体降级, 不阻断出图
        return {
            "zones": {},
            "degraded": True,
            "reason": f"区域估计 VLM 异常: {exc!s}"[:200],
            "dropped": sorted(needs),
        }
    zones: dict = {}
    dropped: list = []
    for k in sorted(needs):
        poly = out.get(k)
        if poly is None:
            if k == "floor":
                return {
                    "zones": {},
                    "degraded": True,
                    "reason": "VLM 未返回地面区域",
                    "dropped": sorted(needs),
                }
            dropped.append(k)
            continue
        lo, hi = (
            (_FLOOR_MIN_FRAC, _FLOOR_MAX_FRAC) if k == "floor" else (_OPT_MIN_FRAC, _OPT_MAX_FRAC)
        )
        err = _check_poly(poly, min_frac=lo, max_frac=hi)
        if err:
            if k == "floor":
                return {
                    "zones": {},
                    "degraded": True,
                    "reason": f"地面区域不健全: {err}",
                    "dropped": sorted(needs),
                }
            dropped.append(k)
            continue
        # 夹取到 [0,1] (容差内的轻微越界)
        zones[k] = [
            (min(1.0, max(0.0, float(p[0]))), min(1.0, max(0.0, float(p[1])))) for p in poly
        ]
    return {
        "zones": zones,
        "degraded": False,
        "reason": ("丢弃不健全可选区: " + ",".join(dropped)) if dropped else None,
        "dropped": dropped,
    }


def zones_to_mask(zones: dict, img_wh: tuple, feather: int = FEATHER_PX):
    """区域多边形 -> 'L' alpha mask (PIL): 并集栅格化 + **只向内羽化**。

    mask 语义 = 合成 alpha (255=取模型输出, 0=取原图字节)。羽化用高斯模糊后按二值支持
    裁剪 (darker), 保证 alpha 在二值 mask 外恒 0 —— 合成后 mask 外字节即原图字节
    (spec §D1 构造保证的背景保真; 羽化只发生在 mask 内, 供 F003 diff 检查豁免带)。"""
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    W, H = int(img_wh[0]), int(img_wh[1])
    binary = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(binary)
    for poly in (zones or {}).values():
        if len(poly) >= 3:
            draw.polygon([(x * W, y * H) for x, y in poly], fill=255)
    if feather <= 0:
        return binary
    blurred = binary.filter(ImageFilter.GaussianBlur(feather))
    return ImageChops.darker(blurred, binary)  # min 逐像素: mask 外恒 0, 内缘渐变


def composite_masked(orig_png: bytes, model_png: bytes, mask_png: bytes) -> bytes:
    """合成 (render-mask-b1 F002, spec §D1): mask 内取模型输出, mask 外取原图字节。

    背景保真由构造保证 (不信模型的 mask 外承诺 —— 开工前调查实测 fal 输出缩分辨率且
    mask 外约 6% 像素被碰): 模型输出先 LANCZOS 回缩到原图尺寸 (fal 会缩分辨率但全帧对齐),
    再按 alpha 合成; mask PNG 输出 (无 JPEG 重编码, 外部字节即原图解码字节)。"""
    from PIL import Image

    orig = Image.open(io.BytesIO(orig_png)).convert("RGB")
    model = Image.open(io.BytesIO(model_png)).convert("RGB")
    if model.size != orig.size:
        model = model.resize(orig.size, Image.LANCZOS)
    alpha = Image.open(io.BytesIO(mask_png)).convert("L")
    out = Image.composite(model, orig, alpha)
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()
