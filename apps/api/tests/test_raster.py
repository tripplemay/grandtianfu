# -*- coding: utf-8 -*-
"""SVG -> PNG 光栅 (依赖 rsvg-convert; 缺失则跳过, CI/容器内必装)。"""
import shutil

import pytest

from aigc.raster import svg_to_png

_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect width="20" height="20" fill="#abc"/></svg>'


@pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="rsvg-convert 不可用")
def test_svg_to_png_returns_png_bytes():
    out = svg_to_png(_SVG, width=40)
    assert out[:8] == b"\x89PNG\r\n\x1a\n"  # PNG 魔数
    assert len(out) > 50


@pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="rsvg-convert 不可用")
def test_svg_to_png_accepts_bytes():
    out = svg_to_png(_SVG.encode("utf-8"))
    assert out[:8] == b"\x89PNG\r\n\x1a\n"
