# -*- coding: utf-8 -*-
"""几何锁定出图【语义】验收 (P0-4 后半): VLM 兜住启发式验收 (acceptance.py) 的盲区。

acceptance.py 是纯 PIL/numpy 零成本几何验收, 文件头已如实记录两类它判不了、须 VLM 的盲区:
  - 盒内类别错: 整图重绘把空盒区重绘一遍的"隐性漏画", 或家具移位到别处 (生产实证: 酒柜
    从红盒移到左墙变嵌入式) —— 盒内像素有改动但画的不是预期家具, 启发式漏判。
  - 盒外保真: 无新边缘的整面材质替换 (换木地板)、色温/明显偏色漂移 —— 边缘差分逃过, 色度
    差分对好图误报, 只能靠 VLM 语义看。

设计: 独立模块, chat_json 由调用方依赖注入 (不 import providers), 保持可离线单测 + acceptance
纯几何不变。默认关 (GEOMETRY_ACCEPT_VLM), 启用才花 VLM 调用/预算。任何 VLM 异常一律降级为
放行 (不因超时/解析失败阻断交付), 只在启发式已通过的图上做"第二意见"以省调用。
"""
from __future__ import annotations

import base64
import io
from typing import Any, Callable

from . import perspective

# 盒内类别判定的对象: 类别错会造成明显问题且 VLM 能可靠识别的大件 (酒柜/衣柜/沙发/床/
# 电视柜/餐桌等); 小装饰/椅子等不查 (裁剪里难辨且错了影响小)。
_CHECK_TYPES = frozenset(
    {
        "wine_cabinet", "cabinet", "tall_cabinet", "wardrobe", "sideboard", "dresser",
        "shoe_cabinet", "bookshelf", "media", "tv", "sofa", "bed", "bunk_bed", "kids_bed",
        "chaise", "dining_table", "coffee_table", "desk", "console_table", "chest",
    }
)
# 逐盒裁剪最多送 VLM 的盒数 (按盒面积降序取, 超出记 dropped 不静默); 控成本/payload。
_MAX_BOXES = 6
# 盒 bbox 全分辨率面积低于此 (px²) 跳过 (画幅边缘被裁/太小, VLM 难辨)。
_MIN_BBOX_AREA = 4000
# VLM 输入图缩放上限 (长边 px): 省 token, 结构/类别判定不需原分辨率。
_MAX_SIDE = 768


def _b64(png: bytes) -> str:
    return base64.b64encode(png).decode()


def _as_bool(v, default: bool) -> bool:
    """稳健布尔: VLM 在 json_object 下可能返字符串 'false'/'no'/数字 0; bool('false')==True 会
    误判, 故显式识别否定形。"""
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("false", "no", "0", "n", "否", "不是"):
            return False
        if s in ("true", "yes", "1", "y", "是"):
            return True
    return default


def _downscale(png: bytes, max_side: int = _MAX_SIDE) -> bytes:
    from PIL import Image

    im = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = im.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _img_part(png: bytes) -> dict:
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_b64(png)}"}}


def check_outside_fidelity(empty_png: bytes, out_png: bytes, chat_json: Callable) -> dict:
    """盒外保真: VLM 比对空房照与成图的墙/地/顶/门窗材质与结构是否被改 (忽略新增家具+轻微曝光)。"""
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                "图1是空房实拍照, 图2是在同一空房里摆了家具后的室内效果图。请【忽略新增的家具】, "
                "只对比两张图的墙面、地面、天花、门窗的材质/颜色/结构是否保持一致。轻微的曝光、"
                "亮度、白平衡差异属正常, 不算改动; 家具下方/周围新增的地面倒影与接触阴影也属"
                "正常渲染, 不算地面材质改变。若地面材质被换 (如大理石变木地板)、墙面加了护墙板/"
                "换色、门窗位置或数量变了、出现原本没有的结构, 才算被改。"
                '返回 JSON: {"structure_preserved": true/false, "changes": ["简述改动", ...]}。'
            ),
        },
        {"type": "text", "text": "图1 (空房):"},
        _img_part(_downscale(empty_png)),
        {"type": "text", "text": "图2 (效果图):"},
        _img_part(_downscale(out_png)),
    ]
    out = chat_json([{"role": "user", "content": content}])
    preserved = _as_bool(out.get("structure_preserved"), True)
    changes = [str(c) for c in (out.get("changes") or [])][:3]
    return {"ok": preserved, "changes": changes}


def _box_crops(
    out_png: bytes, cam, furniture: list[dict], rooms_by_id: dict, img_wh, mm_per_px: float
) -> tuple[list[dict], int]:
    """逐件大件盒的全分辨率裁剪 (含少量 padding): [{t, png}]; 按盒面积降序, 截断到 _MAX_BOXES。"""
    from PIL import Image

    out_im = Image.open(io.BytesIO(out_png)).convert("RGB")
    if out_im.size != tuple(img_wh):
        out_im = out_im.resize(tuple(img_wh))
    W, H = img_wh
    cand: list[dict] = []
    for it in furniture:
        t = it.get("t")
        if not t or t not in _CHECK_TYPES or not rooms_by_id.get(it.get("room_id")):
            continue
        mask_img, n = perspective.footprint_mask(cam, [it], rooms_by_id, img_wh, mm_per_px=mm_per_px)
        if not n:
            continue
        bbox = mask_img.getbbox()  # (x0,y0,x1,y1) 全分辨率盒包围盒
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        area = (x1 - x0) * (y1 - y0)
        if area < _MIN_BBOX_AREA:
            continue
        pad_x, pad_y = int((x1 - x0) * 0.12), int((y1 - y0) * 0.12)
        crop = out_im.crop(
            (max(0, x0 - pad_x), max(0, y0 - pad_y), min(W, x1 + pad_x), min(H, y1 + pad_y))
        )
        buf = io.BytesIO()
        crop.save(buf, "PNG")
        # 裁剪也降采样 (与整图同口径省 token): 近场大件全分辨率裁剪可上千像素。
        cand.append({"t": t, "area": area, "png": _downscale(buf.getvalue())})
    cand.sort(key=lambda c: -c["area"])
    return cand[:_MAX_BOXES], max(0, len(cand) - _MAX_BOXES)


def check_box_categories(
    out_png: bytes, cam, furniture: list[dict], rooms_by_id: dict, img_wh, mm_per_px: float,
    chat_json: Callable, *, catalog=None,
) -> dict:
    """盒内类别: 逐大件盒裁剪送 VLM, 判每盒主要家具是否为预期类型 (抓移位/漏画/画错件)。"""
    crops, dropped = _box_crops(out_png, cam, furniture, rooms_by_id, img_wh, mm_per_px)
    if not crops:
        return {"mismatches": [], "checked": 0, "dropped": dropped}

    def _label(t: str) -> str:
        if catalog is not None:
            zh = (catalog.CATALOG.get(t) or {}).get("zh")
            en = (catalog.CATALOG.get(t) or {}).get("en")
            return f"{zh or t} ({en or t})"
        return t

    content: list[dict] = [
        {
            "type": "text",
            "text": (
                "下面每张图是一张室内效果图里【一个家具位置的裁剪】, 每张前标注了该位置【预期的"
                "家具类型】。请判断每张裁剪里占主体的家具, 是否就是预期类型 (同类不同款算符合; "
                "预期处根本没有该类家具、或画成了别的类别, 算不符)。"
                '返回 JSON: {"results": [{"box": 序号(从0), "is_expected": true/false, '
                '"actual": "实际看到的家具"}, ...]}。'
            ),
        }
    ]
    for i, c in enumerate(crops):
        content.append({"type": "text", "text": f"box {i} 预期={_label(c['t'])}:"})
        content.append(_img_part(c["png"]))
    out = chat_json([{"role": "user", "content": content}])
    results = out.get("results") or []
    mismatches: list[dict] = []
    for res in results:
        if not isinstance(res, dict):
            continue  # VLM 偶发吐出非 dict 项 (字符串/None): 跳过, 不连累其他合法项
        try:
            idx = int(res.get("box"))
        except (TypeError, ValueError):
            continue
        # is_expected 缺省视为符合 (只在明确判"不符"时报, 避免漏字段误报)。
        if 0 <= idx < len(crops) and not _as_bool(res.get("is_expected"), True):
            mismatches.append(
                {"t": crops[idx]["t"], "actual": str(res.get("actual") or "未知")}
            )
    return {"mismatches": mismatches, "checked": len(crops), "dropped": dropped}


def evaluate_semantic(
    empty_png: bytes,
    out_png: bytes,
    *,
    cam,
    furniture: list[dict],
    rooms_by_id: dict,
    img_wh,
    mm_per_px: float,
    chat_json: Callable,
    catalog=None,
) -> dict:
    """VLM 语义验收: 盒外保真 + 盒内类别。返回 {ok, fail_reasons, checks}; 单项 VLM 失败降级跳过。

    与 acceptance.evaluate_geometry_lock 的 verdict 合并 (调用方): fail_reasons 追加, ok 取与。
    """
    fail: list[str] = []
    checks: dict[str, Any] = {}
    try:
        fid = check_outside_fidelity(empty_png, out_png, chat_json)
        checks["fidelity"] = fid
        if not fid["ok"]:
            detail = ("；".join(fid["changes"])) if fid["changes"] else ""
            fail.append(f"盒区外结构/材质被改{('：' + detail) if detail else ''}")
    except Exception as exc:  # noqa: BLE001 - VLM 失败降级, 不阻断交付
        checks["fidelity"] = {"skipped": str(exc)[:200]}
    try:
        cat = check_box_categories(
            out_png, cam, furniture, rooms_by_id, img_wh, mm_per_px, chat_json, catalog=catalog
        )
        checks["categories"] = cat
        for m in cat["mismatches"]:
            zh = (catalog.CATALOG.get(m["t"]) or {}).get("zh", m["t"]) if catalog else m["t"]
            fail.append(f"{zh} 盒区画的是「{m['actual']}」不是预期家具")
    except Exception as exc:  # noqa: BLE001
        checks["categories"] = {"skipped": str(exc)[:200]}
    return {"ok": not fail, "fail_reasons": fail, "checks": checks}
