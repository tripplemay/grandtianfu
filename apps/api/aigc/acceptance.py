# -*- coding: utf-8 -*-
"""几何锁定出图自动验收 (路线A P4, 纯 PIL/numpy, 零模型成本)。

对照标注盒逐项检查生成图:
  1. furnished — 每个盒区相对空房照要有实质改动 (家具画上了), 否则 = 漏画;
  2. residue  — 盒区像素若与标注图 (guide) 几乎一致 = 半透明彩盒没被替换掉
     (按 guide 相似度判, 不按色相 —— 橙/棕标注色会撞木色家具与暖色地板);
  3. reframe  — 空房照的强边缘 (墙线/窗框/灯带) 在成图盒区外大量丢失 = 画面被
     重新取景 (平移或缩放, 相机被动了);
  4. structure — 盒区 (含世界坐标外扩/地毯/倒影余量) 之外出现空房照没有的新强
     边缘 = 结构被改 (幻觉门窗 / 换木地板拼缝 / 墙面加护墙板)。
     注: 不用强度差分 —— 整图重绘模型对窗景/纹理做近似重绘, 像素级漂移几 px 就让
     有梯度处强度差爆表 (好图也全线超阈, 标定实测); 边缘差分 + 膨胀容差才稳。

只判「画没画/画哪了/改没改不该改的」, 不判美观 —— 形体质量由彩盒引导保证, 这里
兜住引导失效的尾部。阈值用 D 客厅真实样本标定 (好图 3 全放行; 幻觉门/法式重绘墙/
彩盒残留/完全漏画全拦截), 见各常量注释。

已知盲区 (标定实测, 生产后端 gpt-image-2/nano-banana 未见此类失败, 如实记录):
  - furnished 只兜「盒区像素未被动过」; 整图重绘模型把空盒区重绘一遍的"隐性漏画"
    强度上与真家具不可分 (kontext 空边柜盒 27 > relay 真边柜盒 12), 须 VLM 判 (后续);
  - 无新边缘的整面材质替换 (seedream 换木地板) 逃过边缘差分; 色度差分已试废
    (重绘的非均匀色偏让好图误报满屏)。
"""

from __future__ import annotations

import io

import numpy as np

from floorplan_core import catalog

from . import perspective

# 工作分辨率 (宽): 降噪 + 提速; 检查目标都是大尺度特征, 512 足够。
_WORK_W = 512
# furnished: 盒内 |生成-空房| 均值低于此 = 没画家具 (标定: 空房自身 ~3, 画了家具 ≥20)。
_FURNISH_MIN_DIFF = 10.0
# 盒在画幅内的可见面积 (工作分辨率像素) 低于此跳过判定 (画幅边缘被裁的酒柜类)。
_FURNISH_MIN_AREA = 300
# residue: 盒内 |生成-标注图| RGB 均差低于此 = 彩盒原样保留 (标定: 保留盒 ~5-12,
# 画了家具 ≥40; 未画家具时 |空房-标注图| 即盒子染色量 ~40-90, 不会与残留混淆)。
_RESIDUE_MAX_GUIDE_DIFF = 18.0
# 边缘: 梯度幅值超 _EDGE_TAU 记强边缘; 匹配时对方边缘图膨胀 _EDGE_DILATE px
# (吸收近似重绘的几像素漂移)。
_EDGE_TAU = 12.0
_EDGE_DILATE = 5
# structure: 盒区外逐 tile 统计「新出现的强边缘」占比, 超 _NEW_EDGE_TILE 记坏块,
# 坏块数 >= _NEW_EDGE_TILES_MIN 判结构被改 (孤块多为窗景重绘噪声)。
_STRUCT_TILE = 32
_NEW_EDGE_TILE = 0.08
_NEW_EDGE_TILES_MIN = 3
# reframe: 盒区外空房强边缘丢失占比超此 = 重取景/大面积重绘 (平移和缩放都表现为
# 原边缘大范围失配)。
_LOST_EDGE_FRAC = 0.50
# allowed 区世界坐标外扩 (mm): 餐桌类家具的配椅是 prompt 语义的一部分, 会合法地
# 长到盒外; 地毯是"座区下方"软指定, 实画常远大于矩形; 其余留少量溢出余量。
_MARGIN_MM = {"dining_table": 700, "desk": 700, "round_table": 700, "rug": 1000}
_MARGIN_MM_DEFAULT = 150
# allowed mask 追加膨胀半径 (相对工作宽度) + 盒区向下延伸倍数 (亮面地砖拖长倒影)。
_ALLOWED_DILATE_FRAC = 0.04
_REFLECT_EXTEND = 0.9


def _to_work(png: bytes, wh: tuple[int, int]) -> np.ndarray:
    from PIL import Image

    im = Image.open(io.BytesIO(png)).convert("RGB").resize(wh)
    return np.asarray(im, dtype=np.float64)


def _gray(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def _gain_fit(src: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """稳健全局亮度增益/偏置拟合 (吸收合法的整体曝光漂移, 保留内容差异)。

    两轮: 先全量拟合, 再剔除残差最大的 20% (家具/大改动像素是离群点, 单轮最小二乘
    会被黑白极值高杠杆点压塌斜率 —— 恰恰在最需要检测的大改动图上失真)。
    """
    s, r = src.ravel(), ref.ravel()
    a, b = np.polyfit(s, r, 1)
    res = np.abs(s * a + b - r)
    keep = res <= np.percentile(res, 80)
    a, b = np.polyfit(s[keep], r[keep], 1)
    return src * a + b


def _inflate_item(item: dict, mm_per_px: float) -> dict:
    """按类型把 footprint 在世界坐标外扩 (margin_mm), 供 allowed 区使用。"""
    m_px = _MARGIN_MM.get(item.get("t"), _MARGIN_MM_DEFAULT) / mm_per_px
    out = dict(item)
    if "dcx" in item or "dcy" in item:
        out["r"] = float(item.get("r", 20) or 20) + m_px
        return out
    out["dx"] = float(item.get("dx", 0) or 0) - m_px
    out["dy"] = float(item.get("dy", 0) or 0) - m_px
    out["w"] = float(item.get("w", 0) or 0) + 2 * m_px
    out["h"] = float(item.get("h", 0) or 0) + 2 * m_px
    return out


def _mask_to_work(mask, wh: tuple[int, int]) -> np.ndarray:
    return np.asarray(mask.resize(wh)) > 127


def _extend_down(m: np.ndarray, frac: float) -> np.ndarray:
    """把 mask 逐列向下延伸 (家具在亮面地板上的倒影区), 延伸量 = 各列高度×frac。"""
    out = m.copy()
    H = m.shape[0]
    ys, xs = np.where(m)
    if ys.size == 0:
        return out
    for x in np.unique(xs):
        col = ys[xs == x]
        top, bot = int(col.min()), int(col.max())
        ext = int((bot - top + 1) * frac)
        out[bot : min(H, bot + ext + 1), x] = True
    return out


def _dilate(m: np.ndarray, r: int) -> np.ndarray:
    from PIL import Image, ImageFilter

    if r <= 0:
        return m
    im = Image.fromarray((m * 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.MaxFilter(r * 2 + 1))) > 127


def _strong_edges(gray: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(gray)
    return np.hypot(gx, gy) > _EDGE_TAU


def evaluate_geometry_lock(
    empty_png: bytes,
    out_png: bytes,
    *,
    guide_png: bytes,
    cam,
    furniture: list[dict],
    rooms_by_id: dict,
    img_wh: tuple[int, int],
    mm_per_px: float,
) -> dict:
    """生成图 vs 空房照+标注图 -> 验收结论 (纯几何/像素, 不调模型)。

    返回 {ok, score, fail_reasons, checks}; score∈[0,1] 供多次尝试择优。
    """
    W, H = img_wh
    ww = _WORK_W
    wh = (ww, max(1, round(H * ww / W)))
    empty = _to_work(empty_png, wh)
    out = _to_work(out_png, wh)
    guide = _to_work(guide_png, wh)
    ge = _gray(empty)
    go = _gain_fit(_gray(out), ge)
    diff = np.abs(go - ge)

    # 逐件盒 mask (与 annotate_boxes 同过滤规则); 地毯不进盒检查但进 allowed。
    boxes: list[dict] = []
    allowed = np.zeros(wh[::-1], bool)
    for it in furniture:
        t = it.get("t")
        rect = rooms_by_id.get(it.get("room_id"))
        # decor-b1 F008 D10: 挂画/窗帘 (NOSHADOW_TYPES) 完全跳过 —— b1 不进第7步 prompt, 生成图
        # 里不出现, 无需 allowed 容差; rug 例外 (下方进 allowed, 因 prompt 仍带地毯)。
        if not t or t == "partition" or t in catalog.NOSHADOW_TYPES or not rect:
            continue
        infl, _n1 = perspective.footprint_mask(
            cam, [_inflate_item(it, mm_per_px)], rooms_by_id, img_wh, mm_per_px=mm_per_px
        )
        if not _n1:
            continue
        allowed |= _extend_down(_mask_to_work(infl, wh), _REFLECT_EXTEND)
        if t == "rug":
            continue  # 地毯走 prompt 文字, 不逐盒验收
        mask_img, _n2 = perspective.footprint_mask(
            cam, [it], rooms_by_id, img_wh, mm_per_px=mm_per_px
        )
        boxes.append({"t": t, "mask": _mask_to_work(mask_img, wh)})
    allowed = _dilate(allowed, max(2, int(ww * _ALLOWED_DILATE_FRAC)))

    fail: list[str] = []
    furnished_checks: list[dict] = []
    residue_checks: list[dict] = []
    furnished_ok = residue_ok_n = judged = 0
    for b in boxes:
        area = int(b["mask"].sum())
        if area < _FURNISH_MIN_AREA:
            furnished_checks.append({"t": b["t"], "skipped": "画幅内可见面积过小"})
            continue
        judged += 1
        mean_diff = float(diff[b["mask"]].mean())
        ok_f = mean_diff >= _FURNISH_MIN_DIFF
        furnished_ok += ok_f
        furnished_checks.append({"t": b["t"], "diff": round(mean_diff, 1), "ok": ok_f})
        if not ok_f:
            fail.append(f"{b['t']} 盒区未见家具 (盒内改动 {mean_diff:.0f})")
        guide_diff = float(np.abs(out - guide).mean(axis=2)[b["mask"]].mean())
        ok_r = guide_diff > _RESIDUE_MAX_GUIDE_DIFF or not ok_f  # 没画家具时不重复报残留
        residue_ok_n += ok_r
        residue_checks.append({"t": b["t"], "guide_diff": round(guide_diff, 1), "ok": ok_r})
        if not ok_r:
            fail.append(f"{b['t']} 标注彩盒未被替换 (与标注图差 {guide_diff:.0f})")

    # 边缘差分 (盒区外): 新增强边缘 = 结构被改; 原强边缘大量丢失 = 重取景。
    # 边缘图用稳健拟合后的灰度: 归一对比度 (未归一时 relay 好图的亚阈纹理越线误报),
    # 稳健拟合保证大改动图不被离群点压塌 (见 _gain_fit)。
    outside = ~allowed
    E_e = _strong_edges(ge)
    E_o = _strong_edges(go)
    new_edges = E_o & ~_dilate(E_e, _EDGE_DILATE) & outside
    lost_edges = E_e & ~_dilate(E_o, _EDGE_DILATE) & outside
    e_base = int((E_e & outside).sum())
    lost_frac = float(lost_edges.sum()) / max(1, e_base)
    reframed = lost_frac >= _LOST_EDGE_FRAC
    if reframed:
        fail.append(f"画面被重新取景或大面积重绘 (盒区外原有边缘丢失 {lost_frac:.0%})")

    tiles_bad = tiles_total = 0
    max_frac = 0.0
    T = _STRUCT_TILE
    for y in range(0, wh[1], T):
        for x in range(0, wh[0], T):
            om = outside[y : y + T, x : x + T]
            n_out = int(om.sum())
            if n_out < T * T * 0.3:  # tile 大半在家具/倒影区: 不判
                continue
            tiles_total += 1
            frac = float(new_edges[y : y + T, x : x + T].sum()) / n_out
            max_frac = max(max_frac, frac)
            tiles_bad += frac > _NEW_EDGE_TILE
    struct_ok = tiles_bad < _NEW_EDGE_TILES_MIN
    if not struct_ok:
        fail.append(f"盒区外出现新结构 (新边缘坏块 {tiles_bad}/{tiles_total})")

    furnished_frac = furnished_ok / judged if judged else 0.0
    residue_frac = residue_ok_n / judged if judged else 1.0
    struct_score = max(
        0.0,
        1.0
        - min(1.0, tiles_bad / max(_NEW_EDGE_TILES_MIN * 3, 1)) * 0.5
        - (0.5 if reframed else 0.0),
    )
    score = round(0.5 * furnished_frac + 0.2 * residue_frac + 0.3 * struct_score, 3)
    return {
        "ok": not fail,
        "score": score,
        "fail_reasons": fail,
        "checks": {
            "furnished": furnished_checks,
            "residue": residue_checks,
            "reframe": {"lost_edge_frac": round(lost_frac, 3), "ok": not reframed},
            "structure": {
                "bad_tiles": tiles_bad,
                "total_tiles": tiles_total,
                "max_tile_frac": round(max_frac, 3),
                "ok": struct_ok,
            },
        },
    }


def retry_hint(verdict: dict) -> str:
    """按失败项生成追加到重试 prompt 的修正指令 (英文, 与主 prompt 同语言)。"""
    reasons = " ".join(verdict.get("fail_reasons") or [])
    hints: list[str] = []
    if "未见家具" in reasons:
        hints.append(
            "Previous attempt left some marked boxes empty — EVERY box must contain its "
            "piece of furniture."
        )
    if "未被替换" in reasons:
        hints.append(
            "Previous attempt left colored box overlays visible — every colored box must "
            "be fully replaced by real furniture, no translucent overlays may remain."
        )
    if "重新取景" in reasons:
        hints.append(
            "Previous attempt shifted the framing — reproduce image 1's exact camera "
            "framing pixel for pixel."
        )
    if "新结构" in reasons:
        hints.append(
            "Previous attempt altered the room structure — do NOT add, remove or repaint "
            "doors, windows, walls, wall decorations, floor or ceiling; change nothing "
            "outside the furniture."
        )
    return (" " + " ".join(hints)) if hints else ""
