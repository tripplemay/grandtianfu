# -*- coding: utf-8 -*-
"""AI 软装风格服务 (软装重构 Phase C-2)。

布局由人工在户型基线锁定、不可移动。AI 不再落位 —— 它对一份既有(基线拷种子的)布局:
(1) 生成丰富的 style_prompt(材质/色彩/风格, 供 img2img 渲染驱动视觉风格);
(2) 可选地在每个房间把某类家具换成**同 swap_group** 内更贴合风格的件(from->to), 位置不变。
"生成候选" = 同一布局 × N 个风格方向。确定性地把选择套回布局坐标, catalog 补外观。
"""
from __future__ import annotations

import json
import math
from typing import Any

from floorplan_core import catalog


def _round_half_up(v: float) -> int:
    """半值向上取整, 与前端 Math.round 一致 (Python 内置 round 是银行家舍入, 会差 1px)。"""
    return math.floor(v + 0.5)


def _zh(t: str) -> str:
    return (catalog.CATALOG.get(t) or {}).get("zh", t)


# decor-b2: 可由 AI 放置的独立配饰件 (有独立坐标, 由 place_decor_standalone 落位)。
# 附着件 (cushions 等) 不在此列 —— 它们挂宿主, 走 attach 路径写宿主 decor 子列表。
_STANDALONE_DECOR = ("wall_art", "curtain", "plant")


def _room_names(G: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in G.get("rooms", []) or []:
        out[r["id"]] = (r.get("label") or {}).get("zh") or r["id"]
    return out


def _room_types(G: dict) -> dict[str, str]:
    """room_id -> geometry room.type (供 decor_slots 判该房可放哪些独立配饰件)。"""
    return {r["id"]: r.get("type") for r in G.get("rooms", []) or []}


def _standalone_slots(rtype: str | None) -> list[str]:
    """该 room.type 可放的独立配饰件 = _STANDALONE_DECOR ∩ 目录 rooms 白名单。"""
    if not rtype:
        return []
    return [t for t in _STANDALONE_DECOR if rtype in (catalog.CATALOG.get(t) or {}).get("rooms", [])]


def layout_summary(base_furniture: list[dict], G: dict) -> list[dict]:
    """把锁定布局按房间汇总成 LLM 可读的槽位清单。不含坐标。

    decor-b2: 每 piece 增 attach_options (该宿主可挂的附着配饰), 每房增 decor_slots
    (该房可放的独立配饰件) —— 供 LLM 决定"挂什么/放什么", 坐标由 Python 落位。
    """
    names = _room_names(G)
    rtypes = _room_types(G)
    by_room: dict[str, dict[str, int]] = {}
    order: list[str] = []
    for it in base_furniture:
        rid = it.get("room_id")
        t = it.get("t")
        if rid is None or not t:
            continue
        if rid not in by_room:
            by_room[rid] = {}
            order.append(rid)
        by_room[rid][t] = by_room[rid].get(t, 0) + 1
    rooms: list[dict] = []
    for rid in order:
        pieces = []
        for t, n in by_room[rid].items():
            group = catalog.swap_group(t)
            opts = [x for x in catalog.types_in_swap_group(group) if x != t]
            piece: dict = {"t": t, "zh": _zh(t), "count": n}
            if opts:
                piece["swap_options"] = [{"t": x, "zh": _zh(x)} for x in opts]
            attach = catalog.attach_types_for_host(t)  # decor-b2: 该宿主可挂配饰
            if attach:
                piece["attach_options"] = [{"t": x, "zh": _zh(x)} for x in attach]
            pieces.append(piece)
        slots = _standalone_slots(rtypes.get(rid))  # decor-b2: 该房可放独立配饰件
        room: dict = {"room_id": rid, "name": names.get(rid, rid), "pieces": pieces}
        if slots:
            room["decor_slots"] = [{"t": x, "zh": _zh(x)} for x in slots]
        rooms.append(room)
    return rooms


def build_messages(style_prompt: str, summary: list[dict], count: int) -> list[dict]:
    system = (
        "你是室内软装风格助理。布局已由人工在户型基线锁定、不可移动、不可增删。你的任务:"
        "(1) 为每个候选方案生成一段丰富的 style_prompt(材质、色彩、灯光、软装氛围, 用于 img2img 渲染驱动视觉风格);"
        "(2) 可选地在每个房间把某类家具换成其 swap_options 内更贴合该风格的件(from->to, 位置不变);"
        "(3) 可选地为房间添加软装配饰: 给某类宿主家具挂 attach_options 内的附着配饰(抱枕/床品/台灯/花瓶/摆件),"
        "或在有 decor_slots 的房间放独立配饰件(挂画/窗帘/绿植)提升品质氛围。"
        "不要输出坐标、尺寸或解释(配饰位置由系统确定性计算)。必须返回 JSON object。"
    )
    user = {
        "base_style": style_prompt,
        "candidate_count": count,
        "layout": summary,
        "instructions": [
            "输出 schemes 数组, 长度尽量等于 candidate_count",
            "每个 scheme 含 name(简短中文风格名) 与 style_prompt(丰富的渲染风格描述)",
            "可选 swaps 数组, 每项 {room_id, from, to}; to 必须取自该 from 件的 swap_options",
            "可选 decor 数组, 每项 {room_id, attach:[{host_t, add:[配饰type]}], standalone:[独立件type]};"
            " attach 的 host_t 必须是该房已有家具且 add 取自其 attach_options;"
            " standalone 只能取该房 decor_slots 内的类型; 不要出坐标",
            "配饰服务于风格氛围: 不同候选可用不同配饰组合(简约风少配饰、轻奢风多挂画摆件等)",
            "不同候选之间应有明显不同的风格方向",
        ],
    }
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": f"候选方案数量: {count}\n" + json.dumps(user, ensure_ascii=False),
        },
    ]


def _validate_scheme_decor(
    decor_raw: Any,
    present: dict[str, set[str]],
    room_types: dict[str, str],
    warnings: list[str],
) -> list[dict]:
    """校验 scheme 的 decor 输出 (decor-b2)。返回归一化 [{room_id, attach, standalone}]。

    attach: host_t 必须是该房已有家具实例 (审查 #7) + add 类型对该宿主合法;
    standalone: 类型必须在该房 decor_slots 内 + 同房去重 (审查 #7 防两个挂画)。
    非法项剥离记 warning (与 swaps 校验同风格, 非阻断)。
    """
    if not isinstance(decor_raw, list):
        return []
    out: list[dict] = []
    for entry in decor_raw:
        if not isinstance(entry, dict):
            continue
        rid = entry.get("room_id")
        if not isinstance(rid, str) or rid not in present:
            warnings.append(f"配饰: 未知房间 {rid}")
            continue
        room_present = present.get(rid, set())
        attach_out: list[dict] = []
        for a in entry.get("attach") or []:
            if not isinstance(a, dict):
                continue
            host_t = a.get("host_t")
            if not isinstance(host_t, str) or host_t not in room_present:
                warnings.append(f"配饰: 房间 {rid} 无宿主 {host_t}")
                continue
            adds: list[str] = []
            seen: set[str] = set()
            for dt in a.get("add") or []:
                if not isinstance(dt, str) or catalog.attach_mount_z(dt, host_t) is None:
                    warnings.append(f"配饰: {dt} 不能挂 {host_t}")
                    continue
                if dt not in seen:
                    seen.add(dt)
                    adds.append(dt)
            if adds:
                attach_out.append({"host_t": host_t, "add": adds})
        slots = set(_standalone_slots(room_types.get(rid)))
        standalone_out: list[str] = []
        seen_s: set[str] = set()
        for st in entry.get("standalone") or []:
            if not isinstance(st, str) or st not in slots:
                warnings.append(f"配饰: {st} 不能放于房间 {rid}")
                continue
            if st not in seen_s:  # 同房每类独立件去重 (≤1)
                seen_s.add(st)
                standalone_out.append(st)
        if attach_out or standalone_out:
            out.append({"room_id": rid, "attach": attach_out, "standalone": standalone_out})
    return out


def validate_candidates(
    raw: Any,
    base_furniture: list[dict],
    room_ids: set[str],
    *,
    requested_count: int,
    room_types: dict[str, str] | None = None,
) -> tuple[list[dict], list[str]]:
    """校验 LLM 候选: style_prompt 规整 + swaps 必须是同组可换件且房间/源件存在。

    decor-b2: 增 decor 校验 (attach 挂谁 + standalone 放哪房)。room_types 缺省时 decor 全剥
    (向后兼容无 decor 的调用)。
    """
    warnings: list[str] = []
    schemes_in = raw.get("schemes") if isinstance(raw, dict) else None
    if not isinstance(schemes_in, list):
        warnings.append("LLM 未返回 schemes 数组")
        return [], warnings
    present: dict[str, set[str]] = {}
    for it in base_furniture:
        present.setdefault(it.get("room_id"), set()).add(it.get("t"))
    out: list[dict] = []
    cap = max(1, requested_count)
    # 先过滤有效项、再按请求数截断 (截断先于过滤会让窗口内的坏项挤掉窗口外的有效候选)。
    for i, sc in enumerate(schemes_in):
        if len(out) >= cap:
            break
        if not isinstance(sc, dict):
            warnings.append(f"方案 {i + 1} 格式无效")
            continue
        sp_raw = sc.get("style_prompt")
        style = sp_raw.strip() if isinstance(sp_raw, str) and sp_raw.strip() else None
        swaps_out: list[dict] = []
        for sw in sc.get("swaps") or []:
            if not isinstance(sw, dict):
                continue
            rid, frm, to = sw.get("room_id"), sw.get("from"), sw.get("to")
            # 非字符串字段 (LLM 偶发返 list/dict) 会让 swap_group(unhashable) 抛错, 先挡。
            if not (isinstance(rid, str) and isinstance(frm, str) and isinstance(to, str)):
                warnings.append("swap 字段非字符串, 已忽略")
                continue
            if rid not in room_ids:
                warnings.append(f"未知房间: {rid}")
                continue
            if frm not in present.get(rid, set()):
                warnings.append(f"房间 {rid} 无 {frm} 可换")
                continue
            group = catalog.swap_group(frm)
            if not group or to == frm or catalog.swap_group(to) != group:
                warnings.append(f"{frm}→{to} 非同组可换件, 已忽略")
                continue
            swaps_out.append({"room_id": rid, "from": frm, "to": to})
        decor_out = _validate_scheme_decor(sc.get("decor"), present, room_types or {}, warnings)
        out.append(
            {
                "name": (sc.get("name") or "").strip(),
                "style_prompt": style,
                "swaps": swaps_out,
                "decor": decor_out,
            }
        )
    return out, warnings


def _swap_item_type(item: dict, new_type: str) -> dict:
    """换件保持中心, 与前端 swapFurnitureType 同构 (白名单式, 从头构造):
    保留 id/room_id/rot/zorder/label/color(非空), 采用新类型目录尺寸/形状, 中心不变,
    矩形件 orient 缺省 'N'; 矩形↔圆形自动切键。丢弃类型专属旧键(w/h/seats/hob…)。未知类型不换。"""
    app = catalog.appearance(new_type)
    if app is None:
        return dict(item)
    if item.get("dcx") is not None or item.get("dcy") is not None:
        cx, cy = float(item.get("dcx", 0)), float(item.get("dcy", 0))
    else:
        cx = float(item.get("dx", 0)) + float(item.get("w", 0)) / 2
        cy = float(item.get("dy", 0)) + float(item.get("h", 0)) / 2
    new: dict = {"t": new_type}
    # 身份/风格键白名单 (与前端逐字段对齐: rot 真值、zorder 非 None、label/color 非空)。
    if item.get("id") is not None:
        new["id"] = item["id"]
    if item.get("room_id") is not None:
        new["room_id"] = item["room_id"]
    if item.get("rot"):
        new["rot"] = item["rot"]
    if item.get("zorder") is not None:
        new["zorder"] = item["zorder"]
    if item.get("label"):
        new["label"] = item["label"]
    if item.get("color"):
        new["color"] = item["color"]
    if "r" in app:  # 新件为圆形
        new["r"] = app["r"]
        new["dcx"] = _round_half_up(cx)
        new["dcy"] = _round_half_up(cy)
    else:
        w, h = app["w"], app["h"]
        new["w"] = w
        new["h"] = h
        new["dx"] = _round_half_up(cx - w / 2)
        new["dy"] = _round_half_up(cy - h / 2)
        new["orient"] = item.get("orient") or "N"
    # decor-b1 D11: 换件透传附着配饰, 按新宿主重新校验 (不兼容项剥离; 圆形新件宿主白名单空 -> 全剥)。
    if item.get("decor"):
        kept, _w = catalog.sanitize_decor(new_type, item["decor"])
        if kept:
            new["decor"] = kept
    return new


def apply_swaps(base_furniture: list[dict], swaps: list[dict]) -> list[dict]:
    """把 (room_id, from)->to 的换件套到锁定布局, 其余件原样保留。不可变: 每件新 dict。"""
    m = {(s["room_id"], s["from"]): s["to"] for s in swaps}
    out: list[dict] = []
    for it in base_furniture:
        key = (it.get("room_id"), it.get("t"))
        out.append(_swap_item_type(it, m[key]) if key in m else dict(it))
    return out


def generate_candidates(
    G: dict,
    provider,
    *,
    base_furniture: list[dict],
    style_prompt: str,
    count: int,
    base_scheme_id: str,
    model: str | None = None,
) -> dict:
    """N 个风格候选 = 同一锁定布局 × 各自 style_prompt (+ 可选同组换件)。不落位。"""
    summary = layout_summary(base_furniture, G)
    room_ids = {r["room_id"] for r in summary}
    messages = build_messages(style_prompt, summary, count)
    raw = provider.chat_json(messages, model=model, temperature=0.5)
    candidates, warnings = validate_candidates(
        raw, base_furniture, room_ids, requested_count=count, room_types=_room_types(G)
    )
    if not candidates:
        warnings.append("LLM 未返回有效候选, 已按原布局生成 1 个方案")
        candidates = [{"name": "", "style_prompt": None, "swaps": [], "decor": []}]
    elif len(candidates) < count:
        warnings.append(f"AI 仅返回 {len(candidates)} 个有效候选(请求 {count})")
    schemes: list[dict] = []
    for idx, cand in enumerate(candidates[:count], start=1):
        furniture = catalog.expand(apply_swaps(base_furniture, cand["swaps"]))
        name = (cand.get("name") or "").strip() or f"AI 方案 {idx}"
        schemes.append(
            {
                "name": name,
                "source": "ai",
                "style_prompt": cand["style_prompt"] or style_prompt,
                "base_scheme_id": base_scheme_id,
                "furniture": furniture,
            }
        )
    # 跨候选去重 (同一告警在多候选重复时只留一条, 保序)。
    return {"schemes": schemes, "warnings": list(dict.fromkeys(warnings))}
