# -*- coding: utf-8 -*-
"""上传归一化 (审计 P0-2): 验真身 / EXIF 方向物化 / 剥 EXIF(GPS) / 压边 / 元数据。"""
import io

import pytest
from PIL import Image

from aigc.errors import AIError
from aigc.imaging import MAX_EDGE, normalize_photo, read_size


def _png(size=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_read_size_returns_actual_dimensions():
    """P1: read_size 读回图片真实宽高 (provider 返回图尺寸校验用)。"""
    assert read_size(_png((1677, 938))) == (1677, 938)
    assert read_size(_png((1024, 1536))) == (1024, 1536)


def test_read_size_rejects_non_image():
    with pytest.raises(AIError):
        read_size(b"not-an-image")


def test_normalize_reencodes_to_jpeg_with_meta():
    blob, meta = normalize_photo(_png((64, 48)))
    assert blob[:3] == b"\xff\xd8\xff"
    assert (meta["width"], meta["height"]) == (64, 48)
    assert meta["mime"] == "image/jpeg"
    assert len(meta["sha256"]) == 64


def test_normalize_materializes_exif_orientation_and_strips_exif():
    # Orientation=6 (顺时针 90°): 物化后宽高互换, 且输出不再携带任何 EXIF。
    buf = io.BytesIO()
    img = Image.new("RGB", (80, 40), (100, 100, 100))
    exif = img.getexif()
    exif[274] = 6  # Orientation
    img.save(buf, format="JPEG", exif=exif.tobytes())

    blob, meta = normalize_photo(buf.getvalue())

    assert (meta["width"], meta["height"]) == (40, 80)
    assert dict(Image.open(io.BytesIO(blob)).getexif()) == {}


def test_normalize_caps_longest_edge():
    blob, meta = normalize_photo(_png((MAX_EDGE * 2, 100)))
    assert max(meta["width"], meta["height"]) <= MAX_EDGE


def test_normalize_rejects_non_image_bytes():
    with pytest.raises(AIError):
        normalize_photo(b"\x89PNG\r\n\x1a\n" + b"0" * 64)  # 假头真垃圾
    with pytest.raises(AIError):
        normalize_photo(b"definitely not an image")


def test_normalize_rejects_decompression_bomb(monkeypatch):
    """像素炸弹 (小文件解出巨图) 必须 415, 不允许进入全量解码。"""
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(AIError):
        normalize_photo(_png((64, 48)))  # 3072 px > 2x1000 -> DecompressionBombError
