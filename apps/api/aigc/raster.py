# -*- coding: utf-8 -*-
"""SVG -> PNG 光栅 (rsvg-convert; 容器已装 librsvg2-bin + Noto CJK, 中文房名不豆腐)。

第5步: 轴测 photo 模式 SVG 需先栅格成 PNG 才能作 img2img 底图送 provider。
resvg 会静默丢辉光/滤镜 (架构红线), 故固定用 rsvg-convert。
"""
from __future__ import annotations

import re
import shutil
import subprocess

from .errors import AIError, DependencyUnavailable


def svg_to_png(svg: str | bytes, *, width: int = 1536, timeout_s: float = 60.0) -> bytes:
    exe = shutil.which("rsvg-convert")
    if not exe:
        raise DependencyUnavailable(
            "rsvg-convert 不可用 (需 librsvg2-bin)。安装: "
            "Debian/Ubuntu `apt-get install librsvg2-bin`, macOS `brew install librsvg`。"
            "生产容器已内置; 本机 dev 缺失仅影响渲染/出图链, 核心几何与编辑不受影响。"
        )
    svg_bytes = svg.encode("utf-8") if isinstance(svg, str) else svg
    try:
        proc = subprocess.run(
            [exe, "-w", str(int(width)), "-f", "png"],
            input=svg_bytes,
            capture_output=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise AIError("rsvg-convert 超时") from exc
    if proc.returncode != 0:
        raise AIError(f"rsvg-convert 失败: {proc.stderr.decode('utf-8', 'replace')[:500]}")
    return proc.stdout


# gpt-image edits 支持的输出尺寸档 (spike/官档): 方形 / 横幅 / 竖幅。
EDIT_SIZES: tuple[tuple[int, int], ...] = ((1024, 1024), (1536, 1024), (1024, 1536))


def pick_edit_size(width: float | None, height: float | None) -> tuple[int, int]:
    """按输入图宽高比在 EDIT_SIZES 里选最接近档 (审计 P0-4/P0-5)。

    输入/输出比例不符会让模型重取景, 违反「保持相机与几何不变」; 无有效宽高回退横幅。"""
    try:
        w = float(width or 0)
        h = float(height or 0)
    except (TypeError, ValueError):
        w = h = 0.0
    if w <= 0 or h <= 0:
        return (1536, 1024)
    ratio = h / w
    return min(EDIT_SIZES, key=lambda s: abs((s[1] / s[0]) - ratio))


_VIEWBOX_RE = re.compile(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+) ([\d.]+)"')


def pick_edit_size_for_svg(svg: str | bytes) -> tuple[int, int]:
    """从 SVG viewBox 读纵横比选输出档 (轴测底图纵横比随户型 bbox 变化)。"""
    text = svg.decode("utf-8", "replace") if isinstance(svg, bytes) else svg
    m = _VIEWBOX_RE.search(text)
    if not m:
        return (1536, 1024)
    return pick_edit_size(float(m.group(1)), float(m.group(2)))


def svg_to_png_canvas(
    svg: str | bytes, size: tuple[int, int], *, timeout_s: float = 60.0
) -> bytes:
    """栅格 SVG 并 letterbox 到精确画布 (审计 P0-4): 底图尺寸与 edits size 单一来源。

    先按目标宽栅格 (rsvg 保持纵横比), 超高则等比缩入, 居中贴到白底画布 —— 不拉伸不裁切。"""
    import io

    from PIL import Image

    target_w, target_h = int(size[0]), int(size[1])
    raw = svg_to_png(svg, width=target_w, timeout_s=timeout_s)
    img = Image.open(io.BytesIO(raw))
    img.load()
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        flattened = Image.new("RGB", rgba.size, (255, 255, 255))
        flattened.paste(rgba, mask=rgba.split()[-1])
        img = flattened
    elif img.mode != "RGB":
        img = img.convert("RGB")
    if img.width > target_w or img.height > target_h:
        img.thumbnail((target_w, target_h), Image.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), (255, 255, 255))
    canvas.paste(img, ((target_w - img.width) // 2, (target_h - img.height) // 2))
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()
