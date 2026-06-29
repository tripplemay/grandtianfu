# -*- coding: utf-8 -*-
"""SVG -> PNG 光栅 (rsvg-convert; 容器已装 librsvg2-bin + Noto CJK, 中文房名不豆腐)。

第5步: 轴测 photo 模式 SVG 需先栅格成 PNG 才能作 img2img 底图送 provider。
resvg 会静默丢辉光/滤镜 (架构红线), 故固定用 rsvg-convert。
"""
from __future__ import annotations

import shutil
import subprocess

from .errors import AIError


def svg_to_png(svg: str | bytes, *, width: int = 1536, timeout_s: float = 60.0) -> bytes:
    exe = shutil.which("rsvg-convert")
    if not exe:
        raise AIError("rsvg-convert 不可用 (需 librsvg2-bin)")
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
