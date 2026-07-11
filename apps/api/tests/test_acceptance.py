# -*- coding: utf-8 -*-
"""P4 自动验收 acceptance.py: 合成场景下逐检查项的判定 + retry_hint。"""

import io

import numpy as np
from aigc.acceptance import evaluate_geometry_lock, retry_hint
from aigc.perspective import Camera, annotate_boxes, footprint_mask
from PIL import Image

W, H = 2048, 1536


def _synth_camera(f=1600.0):
    cx, cy = W / 2, H / 2
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
    eye = np.array([3000.0, 3000.0, 1450.0])
    fwd = np.array([10000.0, 12000.0, 0.0]) - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    down = np.cross(fwd, right)
    down /= np.linalg.norm(down)
    return Camera(K=K, R=np.vstack([right, down, fwd]), t=-np.vstack([right, down, fwd]) @ eye)


_CAM = _synth_camera()
_ROOMS = {"r": [0, 0, 2000, 2000]}
_FURN = [{"t": "sofa", "room_id": "r", "dx": 800, "dy": 800, "w": 200, "h": 90}]


def _photo_arr() -> np.ndarray:
    """带强边缘的合成空房照: 非周期随机竖条 (供 reframe/structure 检测有边可丢/可添)。

    周期条纹会骗过 lost-edge 匹配 (平移后上升沿落进相邻下降沿的容差), 真实照片
    是非周期的, 测试图案须一致。
    """
    arr = np.full((H, W, 3), 150.0)
    rng = np.random.default_rng(3)
    x = 0
    while x < W - 120:
        x += int(rng.integers(60, 160))
        w = int(rng.integers(24, 72))
        arr[:, x : x + w] += 60
        x += w
    return arr


def _png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(buf, format="PNG")
    return buf.getvalue()


def _box_region() -> np.ndarray:
    mask, _ = footprint_mask(_CAM, _FURN, _ROOMS, (W, H), mm_per_px=10)
    return np.asarray(mask) > 127


def _fixtures():
    photo = _photo_arr()
    photo_png = _png(photo)
    guide_png, _legend, drawn = annotate_boxes(
        _CAM, _FURN, _ROOMS, photo_png, (W, H), mm_per_px=10
    )
    assert drawn == 1
    return photo, photo_png, guide_png


def _eval(photo_png, out_png, guide_png):
    return evaluate_geometry_lock(
        photo_png, out_png, guide_png=guide_png, cam=_CAM, furniture=_FURN,
        rooms_by_id=_ROOMS, img_wh=(W, H), mm_per_px=10,
    )


def test_pass_when_box_furnished_and_rest_untouched():
    photo, photo_png, guide_png = _fixtures()
    out = photo.copy()
    box = _box_region()
    rng = np.random.default_rng(7)
    out[box] = rng.uniform(0, 255, size=(int(box.sum()), 3))  # 盒内画了"家具"
    v = _eval(photo_png, _png(out), guide_png)
    assert v["ok"], v["fail_reasons"]
    assert v["score"] >= 0.9


def test_unfurnished_box_fails():
    photo, photo_png, guide_png = _fixtures()
    v = _eval(photo_png, photo_png, guide_png)  # 原样返回空房照
    assert not v["ok"]
    assert any("未见家具" in r for r in v["fail_reasons"])


def test_residue_guide_kept_fails():
    photo, photo_png, guide_png = _fixtures()
    v = _eval(photo_png, guide_png, guide_png)  # 彩盒原样保留 (输出=标注图)
    assert not v["ok"]
    assert any("未被替换" in r for r in v["fail_reasons"])


def test_new_structure_outside_boxes_fails():
    photo, photo_png, guide_png = _fixtures()
    out = photo.copy()
    box = _box_region()
    out[box] = 30  # 盒内画了家具
    yy, xx = np.mgrid[0:200, 0:1200]
    out[80:280, 400:1600] = np.where(((yy // 24 + xx // 24) % 2)[..., None], 255.0, 0.0)
    v = _eval(photo_png, _png(out), guide_png)  # 顶部 (盒区外) 长出棋盘格 = 新结构
    assert not v["ok"]
    assert any("新结构" in r for r in v["fail_reasons"])


def test_reframe_shift_fails():
    photo, photo_png, guide_png = _fixtures()
    out = np.roll(photo, 40, axis=1)  # 整图平移 = 重取景
    box = _box_region()
    out[box] = 30
    v = _eval(photo_png, _png(out), guide_png)
    assert not v["ok"]
    assert any("重新取景" in r for r in v["fail_reasons"])


def test_retry_hint_maps_reasons():
    hint = retry_hint({"fail_reasons": ["sofa 盒区未见家具 (盒内改动 3)", "盒区外出现新结构 (新边缘坏块 5/100)"]})
    assert "EVERY box" in hint and "room structure" in hint
    assert retry_hint({"fail_reasons": []}) == ""
