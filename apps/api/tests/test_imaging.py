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


def _img_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def _solid(size, color) -> bytes:
    return _img_bytes(Image.new("RGB", size, color))


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


# ---- B5 照片质量评分 ----

def _noise_photo(size=(1000, 800)) -> bytes:
    """强纹理噪声图: 清晰 (高拉普拉斯响应)、亮度居中、比例正常 -> 无质量告警。"""
    return _img_bytes(Image.effect_noise(size, 96).convert("RGB"))


def test_quality_present_in_meta():
    _, meta = normalize_photo(_noise_photo())
    q = meta["quality"]
    assert set(q) == {"score", "warnings", "brightness", "sharpness", "megapixels"}


def test_quality_clean_photo_no_warnings_full_score():
    _, meta = normalize_photo(_noise_photo())
    q = meta["quality"]
    assert q["warnings"] == []
    assert q["score"] == 100


def test_quality_flags_low_res():
    _, meta = normalize_photo(_solid((100, 80), (120, 120, 120)))
    assert "low_res" in meta["quality"]["warnings"]


def test_quality_flags_extreme_aspect():
    _, meta = normalize_photo(_solid((2000, 200), (120, 120, 120)))
    assert "extreme_aspect" in meta["quality"]["warnings"]


def test_quality_flags_too_dark_and_too_bright():
    _, dark = normalize_photo(_solid((1000, 800), (4, 4, 4)))
    assert "too_dark" in dark["quality"]["warnings"]
    _, bright = normalize_photo(_solid((1000, 800), (252, 252, 252)))
    assert "too_bright" in bright["quality"]["warnings"]


def test_quality_flags_blurry_but_not_textured():
    # 纯中灰无细节图: 亮度居中、无高频细节 -> blurry, 且不触发 too_dark/too_bright。
    _, g = normalize_photo(_solid((1000, 800), (128, 128, 128)))
    warns = g["quality"]["warnings"]
    assert "blurry" in warns
    assert "too_dark" not in warns and "too_bright" not in warns
    # 强纹理噪声图不应判 blurry。
    _, n = normalize_photo(_noise_photo())
    assert "blurry" not in n["quality"]["warnings"]
