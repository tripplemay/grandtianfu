# -*- coding: utf-8 -*-
"""P4 自动验收 acceptance.py: 合成场景下逐检查项的判定 + retry_hint。"""

import io

import numpy as np
from aigc.acceptance import evaluate_geometry_lock, retry_hint, wall_band_allowed_top_mm
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


def test_geometry_lock_decor_wall_art_paint_in_allowed_no_structure_fail():
    # decor-b2 F004 (F007 头号验收): 挂画进彩盒(墙面带)+进 allowed(墙面带+上沿余量);
    # 模型在挂画墙面带画内容不触发 structure 误判, 且挂画不进逐盒 furnished。
    from aigc.perspective import footprint_mask
    photo = _photo_arr()
    photo_png = _png(photo)
    wall_art = {"t": "wall_art", "room_id": "r", "dx": 300, "dy": 300, "w": 80, "h": 8}
    furn = _FURN + [wall_art]
    guide_png, _legend, drawn = annotate_boxes(_CAM, furn, _ROOMS, photo_png, (W, H), mm_per_px=10)
    assert drawn == 2  # 挂画用墙面带 z0 进彩盒 (sofa + wall_art)
    out = photo.copy()
    rng = np.random.default_rng(7)
    box = _box_region()
    out[box] = rng.uniform(0, 255, size=(int(box.sum()), 3))  # sofa 盒家具化
    # 在挂画墙面带 allowed 区画内容 (模拟模型画挂画)。allowed 抬顶从 acceptance 的单一真源
    # 取, 不再在测试里抄第三份 1500 (decor-envelope-b1 F001)。
    wa_top = wall_band_allowed_top_mm(wall_art)
    wa_mask, _n = footprint_mask(_CAM, [{**wall_art, "z": wa_top}], _ROOMS, (W, H), mm_per_px=10)
    wa_region = np.asarray(wa_mask) > 127
    out[wa_region] = rng.uniform(0, 255, size=(int(wa_region.sum()), 3))
    v = evaluate_geometry_lock(
        photo_png, _png(out), guide_png=guide_png, cam=_CAM, furniture=furn,
        rooms_by_id=_ROOMS, img_wh=(W, H), mm_per_px=10,
    )
    assert v["ok"], v["fail_reasons"]  # 挂画画在 allowed 内 -> 不误判 structure
    # 挂画不进逐盒 furnished 检查 (只有 sofa 被逐盒判)
    furnished_types = {c.get("t") for c in v["checks"]["furnished"]}
    assert "wall_art" not in furnished_types


def test_allowed_top_derives_from_render_top_not_a_second_table(monkeypatch):
    """decor-envelope-b1 F001 承重: allowed 上沿必须由渲染顶**派生**, 不得是第二张表。

    阳性对照 (这条测试的分量所在): 把渲染顶抬高 -> allowed 顶必须自动跟着高。原来的
    `_WALL_BAND_ALLOWED_Z = {"wall_art": 1500, ...}` 双写表在这条下**必红** —— 它写死
    1500, 不认渲染顶。那正是本测试要防的回归: 表与渲染顶漂移时 allowed 会**比渲染盒还矮**,
    盒顶整片落在 allowed 外, 每次出图必报"盒区外出现新结构"(= 100% 误报)。
    """
    from aigc import perspective

    # 1. 行为等价: 今天的值仍是 1400+100 / 1450+100 (= 旧表的 1500 / 1550)
    assert wall_band_allowed_top_mm({"t": "wall_art"}) == 1500
    assert wall_band_allowed_top_mm({"t": "curtain"}) == 1550

    # 2. 派生不变量: 渲染顶变 -> allowed 顶自动跟随 (旧双写表在此必红)
    monkeypatch.setitem(perspective._DEFAULT_HEIGHT_MM, "wall_art", 2400)
    assert wall_band_allowed_top_mm({"t": "wall_art"}) == 2500

    # 3. allowed 顶恒严格高于渲染顶 —— 这是"余量"二字的定义, 双写表给不了这个保证
    assert wall_band_allowed_top_mm({"t": "wall_art"}) > perspective.item_top_z_mm(
        {"t": "wall_art"}
    )


def test_allowed_top_follows_per_item_z_override():
    """decor-envelope-b1 F001 顺带修掉的潜伏 bug: 带显式 z 的件。

    item.z 优先于类型默认值 (perspective.item_top_z_mm 的既有语义)。旧双写表对这类件
    返回**固定** 1500 —— 若某件 z=1600, 则 allowed(1500) < 渲染盒(1600), allowed 比盒还矮。
    生产今天恰好没有带 z 的墙面带件 (全生产方案实测 0 件), 故该 bug 尚未发作; 派生后
    结构上不可能发生。
    """
    assert wall_band_allowed_top_mm({"t": "wall_art", "z": 1600}) == 1700
    assert wall_band_allowed_top_mm({"t": "curtain", "z": 2700}) == 2800


def test_non_wall_band_items_get_no_vertical_margin():
    """byte-safe: 非墙面带件不进 _WALL_BAND_ALLOWED_TYPES -> allowed 盒不加垂直余量。

    F001 是纯机制化重构, 不得顺手改地面件的 allowed 几何。
    """
    from aigc import acceptance as A

    assert A._WALL_BAND_ALLOWED_TYPES == {"wall_art", "curtain"}
    assert A._WALL_BAND_ALLOWED_MARGIN_MM == 100
    for t in ("sofa", "rug", "dining_table", "media"):
        assert t not in A._WALL_BAND_ALLOWED_TYPES


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
