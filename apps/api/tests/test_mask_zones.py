# -*- coding: utf-8 -*-
"""render-mask-b1 F001 mask_zones 健全门 + F003 background_diff_check 确定性验收。"""

import io

from aigc import acceptance, mask_zones
from PIL import Image


def _png(wh=(200, 100), color=(180, 170, 150)):
    buf = io.BytesIO()
    Image.new("RGB", wh, color).save(buf, format="PNG")
    return buf.getvalue()


def _mask_png(wh=(200, 100), fill=0):
    buf = io.BytesIO()
    Image.new("L", wh, fill).save(buf, format="PNG")
    return buf.getvalue()


def _chat(payload):
    def chat_json(messages):
        return payload

    return chat_json


_FLOOR = [[0.0, 0.6], [0.4, 0.55], [1.0, 0.62], [1.0, 1.0], [0.0, 1.0]]
_WW = [[0.4, 0.2], [1.0, 0.15], [1.0, 0.6], [0.4, 0.55]]


# ---- F001: estimate_zones 健全门 ----


def test_zones_happy_floor_and_window_wall():
    r = mask_zones.estimate_zones(
        _png(), {"floor", "window_wall"}, _chat({"floor": _FLOOR, "window_wall": _WW})
    )
    assert r["degraded"] is False
    assert set(r["zones"]) == {"floor", "window_wall"}
    assert r["dropped"] == []


def test_zones_floor_missing_degrades():
    r = mask_zones.estimate_zones(_png(), {"floor"}, _chat({"window_wall": _WW}))
    assert r["degraded"] is True


def test_zones_floor_too_few_points_degrades():
    r = mask_zones.estimate_zones(_png(), {"floor"}, _chat({"floor": [[0, 0], [1, 1]]}))
    assert r["degraded"] is True
    assert "顶点不足" in r["reason"]


def test_zones_floor_area_out_of_bounds_degrades():
    tiny = [[0.4, 0.4], [0.41, 0.4], [0.41, 0.41], [0.4, 0.41]]
    r = mask_zones.estimate_zones(_png(), {"floor"}, _chat({"floor": tiny}))
    assert r["degraded"] is True
    assert "面积占比" in r["reason"]


def test_zones_self_intersecting_floor_degrades():
    bowtie = [[0.0, 0.0], [1.0, 1.0], [1.0, 0.0], [0.0, 1.0]]
    r = mask_zones.estimate_zones(_png(), {"floor"}, _chat({"floor": bowtie}))
    assert r["degraded"] is True
    assert "自交" in r["reason"]


def test_zones_bad_optional_zone_dropped_not_degraded():
    r = mask_zones.estimate_zones(
        _png(),
        {"floor", "window_wall"},
        _chat({"floor": _FLOOR, "window_wall": [[0, 0], [1, 1]]}),
    )
    assert r["degraded"] is False
    assert r["dropped"] == ["window_wall"]
    assert set(r["zones"]) == {"floor"}


def test_zones_vlm_exception_degrades():
    def boom(messages):
        raise RuntimeError("vlm down")

    r = mask_zones.estimate_zones(_png(), {"floor"}, boom)
    assert r["degraded"] is True
    assert "异常" in r["reason"]


def test_zones_to_mask_exterior_stays_zero_after_feather():
    """羽化只向内: 二值 mask 外的 alpha 恒 0 (合成后 mask 外字节即原图的前提)。"""
    m = mask_zones.zones_to_mask({"floor": _FLOOR}, (200, 100), feather=8)
    import numpy as np

    a = np.asarray(m)
    # 区域上缘之外 (y < 50, floor 上界 ~55%*100=55 最低 55) 必须恒 0
    assert a[:50].max() == 0
    # 区域内部深处必须为 255
    assert a[90, 100] == 255
    # 内缘存在渐变 (羽化生效)
    assert 0 < a[58:64].max() < 255 or a[58:64].max() == 255


# ---- F003: background_diff_check ----

_ORIG = _png((200, 100), (120, 130, 140))


def _final_with_rect(x0, y0, x1, y1, color=(255, 0, 0)):
    im = Image.open(io.BytesIO(_ORIG)).convert("RGB")
    from PIL import ImageDraw

    d = ImageDraw.Draw(im)
    d.rectangle([x0, y0, x1, y1], fill=color)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _mask_with_rect(x0, y0, x1, y1):
    im = Image.new("L", (200, 100), 0)
    from PIL import ImageDraw

    d = ImageDraw.Draw(im)
    d.rectangle([x0, y0, x1, y1], fill=255)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def test_diff_identical_is_ok():
    r = acceptance.background_diff_check(_ORIG, _ORIG, _mask_with_rect(50, 50, 150, 99))
    assert r["ok"] is True
    assert r["changed_frac"] == 0.0


def test_diff_outside_mask_fails():
    # mask 在中下 (50,50)-(150,99); 改动在左上 mask 外
    final = _final_with_rect(0, 0, 30, 30)
    r = acceptance.background_diff_check(_ORIG, final, _mask_with_rect(50, 50, 150, 99))
    assert r["ok"] is False
    assert r["changed_frac"] > 0


def test_diff_inside_mask_passes():
    # 改动完全落在 mask 内 -> 外部零改动
    final = _final_with_rect(60, 60, 140, 90)
    r = acceptance.background_diff_check(_ORIG, final, _mask_with_rect(50, 50, 150, 99))
    assert r["ok"] is True


def test_diff_near_mask_edge_exempted_by_erosion():
    # 改动贴着 mask 外缘 (腐蚀豁免带 x∈[38,50) 内) -> 不算外部改动
    final = _final_with_rect(40, 55, 49, 95)
    r = acceptance.background_diff_check(_ORIG, final, _mask_with_rect(50, 50, 150, 99))
    assert r["ok"] is True


def test_diff_size_mismatch_fails():
    r = acceptance.background_diff_check(_ORIG, _png((100, 50)), _mask_with_rect(50, 50, 150, 99))
    assert r["ok"] is False
    assert "尺寸不一致" in r["error"]
