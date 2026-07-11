# -*- coding: utf-8 -*-
"""布局质量 lint: 消费已建 scene, 产出设计质量问题 (与 validate_scene 的渲染安全校验分离)。

为什么独立成模块而非扩 validate_scene:
- validate_scene 是渲染安全闸 (ERROR→validation.ok=False 硬阻断 AI 出图 + 部署默认场景门禁),
  且其结果计数写进 render_manifest、绑定 golden 字节稳定。掺入"设计质量"判断会污染门禁语义。
- 布局 lint 是"设计建议"层: 生产实证 (酒柜悬空于动线中央/背贴落地窗, 但自动验收仍通过) 表明
  出图链路会忠实执行错误的落位数据。lint 在出图前对家具落位做几何体检, 作为可降级门禁提前拦下。

判定全部基于几何关系, 不依赖 orient (历史数据 orient 语义不一致, 不可信)。阈值以真实 D 户型
现有布局标定 (零误报): 柜类墙靠件贴墙 gap≤7px, 客厅沙发可合法悬空 128~158px, 地毯在家具下。

lint_layout(scene) 返回与 validate_scene 同构的信封 {ok, issues, errors, warnings}, 前端统一渲染。
"""

from __future__ import annotations

from typing import Any

from . import catalog
from . import geometry as _geometry

# —— 阈值 (px, 1px=10mm), 以真实 D 户型现有布局标定 —— #
# 柜类墙靠件到最近墙的 gap 超此值判"悬空": D 现有柜件贴墙 gap≤7px, 阈值 100px(1m)留足余量。
FLOATING_WALL_GAP_PX = 100.0
# 大件到落地窗的 gap 小于此值判"背贴落地窗": 10px(10cm) 即紧贴。
WINDOW_ADJ_PX = 10.0
# 仅连续宽度≥此值的落地窗算"玻璃幕墙"(大件背贴才成问题): 3m。玄关/卫浴的小装饰落地窗
# (D 定稿平面把玄关矮柜置于 1.6m 装饰窗下=合理设计) 不触发, 只拦客厅/阳台大玻璃墙前的大件。
# 按"同墙连续落地窗合并后总跨度"判定, 防大玻璃墙被拆成多条 <3m 记录时漏判。
WINDOW_MIN_SPAN_PX = 300.0
# 家具重叠面积超此值判"碰撞": 900px²(0.09m²=30×30cm), 排除擦碰级噪声。
MIN_OVERLAP_PX2 = 900.0

# —— 类型集 (lint 专属分类, 非 catalog 字段) —— #
# 柜类墙靠件 (悬空检查): 储物/展示柜背面必须贴实墙, 悬空即设计错误 (酒柜/衣柜/电视柜等)。
# console_table 不在此列 —— 玄关台/沙发背几案可合法置于浮岛沙发背后。座椅/床也不在此列
# (客厅沙发面对电视悬空、卧室岛床居中都是合法布局)。
WALL_UNIT_TYPES = frozenset(
    {
        "wardrobe",
        "bookshelf",
        "cabinet",
        "tall_cabinet",
        "sideboard",
        "wine_cabinet",
        "dresser",
        "shoe_cabinet",
        "media",
        "chest",
    }
)
# 背贴玻璃幕墙检查对象: 高储物柜 (挡光) + 大件座椅/床 (背朝玻璃观感差, Phase1 沙发贴窗病灶)。
# desk/console/低边柜/media 排除 —— 书桌面窗采光、边柜置于窗下都是合理设计, 不应误判。
BACKS_WINDOW_TYPES = frozenset(
    {
        "wardrobe",
        "wine_cabinet",
        "bookshelf",
        "tall_cabinet",
        "cabinet",
        "chest",
        "sofa",
        "bed",
        "bunk_bed",
        "kids_bed",
    }
)
# 叠放/挂靠件: 合法地与其他家具重叠, 碰撞检查一律跳过。
# rug=地毯铺家具下; tv=挂墙压电视柜; mirror=挂墙; plant/floor_lamp/coat_rack=小装饰。
OVERLAY_TYPES = frozenset({"rug", "tv", "mirror", "plant", "floor_lamp", "coat_rack"})
# 软体座椅: 转角沙发/组合沙发/沙发+贵妃常以多件拼接摆放 (footprint 相接或叠角), 两两跳过碰撞。
SOFT_SEATING_TYPES = frozenset({"sofa", "chaise", "armchair", "ottoman", "bench", "round_chair"})
# 座椅类 + 桌类: 椅子塞进桌下的重叠合法, 碰撞检查跳过此配对。
SEATING_TYPES = frozenset(
    {
        "chair",
        "swivel_chair",
        "armchair",
        "bar_stool",
        "bench",
        "ottoman",
        "round_chair",
        "desk_chair",
        "chaise",
    }
)
TABLE_TYPES = frozenset(
    {
        "dining_table",
        "round_table",
        "coffee_table",
        "desk",
        "side_table",
        "console_table",
        "island",
        "kitchen",
        "vanity",
    }
)
# 床头柜紧贴床摆放, 该配对重叠合法。
_BED_TYPES = frozenset({"bed", "kids_bed", "bunk_bed", "crib"})


def _zh(t: Any) -> str:
    return catalog.CATALOG.get(str(t), {}).get("zh", str(t))


def _issue(level: str, code: str, message: str, **meta: Any) -> dict[str, Any]:
    return {"level": level, "code": code, "message": message, **meta}


def _box(it: dict[str, Any]) -> tuple[float, float, float, float] | None:
    """家具 footprint (x0,y0,x1,y1) 绝对坐标; 圆形件取外接方; 无坐标返回 None。"""
    if all(k in it for k in ("x", "y", "w", "h")):
        x, y = float(it["x"]), float(it["y"])
        return (x, y, x + float(it["w"]), y + float(it["h"]))
    if all(k in it for k in ("cx", "cy", "r")):
        cx, cy, r = float(it["cx"]), float(it["cy"]), float(it["r"])
        return (cx - r, cy - r, cx + r, cy + r)
    return None


def _room_group_map(scene: dict[str, Any]) -> dict[str, str]:
    """room_id -> 逻辑房分组键: 属 merge 组的成员共用组 id, 其余用自身 id。碰撞检查据此判
    "同一连通空间" (L 形合并房内跨成员的家具重叠也应查, 而非仅同 _room_id)。"""
    out: dict[str, str] = {}
    try:
        for gid, gr in _geometry.merge_groups({"rooms": scene.get("rooms", [])}).items():
            for rid in gr["members"]:
                out[str(rid)] = str(gid)
    except Exception:  # noqa: BLE001 — 无 merge 数据/派生失败: 全走单房 (fallback)
        pass
    return out


def _nearest_wall_gap(box: tuple, wall_bboxes: list[dict]) -> float:
    """footprint 到最近墙矩形的间隙 (px): 仅计沿某轴投影重叠的墙 (真正正对的那面),
    排除仅对角相邻的墙。房内任意件都会与四周墙投影重叠, 故返回有限值; 无墙返回 inf。"""
    best = float("inf")
    for w in wall_bboxes:
        wx0, wy0, wx1, wy1 = float(w["x0"]), float(w["y0"]), float(w["x1"]), float(w["y1"])
        overlap_x = min(box[2], wx1) - max(box[0], wx0)
        overlap_y = min(box[3], wy1) - max(box[1], wy0)
        if overlap_x <= 0 and overlap_y <= 0:
            continue  # 仅对角相邻, 非正对
        dx = max(wx0 - box[2], box[0] - wx1)  # 横向分离 (>0=分开)
        dy = max(wy0 - box[3], box[1] - wy1)  # 纵向分离
        gap = max(dx, dy)
        if gap < best:
            best = gap
    return best


def _wide_full_window_ids(windows: list[dict]) -> set[str]:
    """判定哪些落地窗属"玻璃幕墙": 同墙 (axis,at) 连续 full 窗合并后总跨度≥WINDOW_MIN_SPAN。
    防大玻璃墙被建模成多条 <3m 记录时逐条被过滤而全部漏判。返回合格窗 id 集。"""
    by_wall: dict[tuple[str, float], list[tuple[float, float, Any]]] = {}
    for w in windows:
        if w.get("wtype") != "full":
            continue
        axis, at, span = w.get("axis"), w.get("at"), w.get("span") or [0, 0]
        if axis is None or at is None:
            continue
        by_wall.setdefault((str(axis), float(at)), []).append(
            (float(span[0]), float(span[1]), w.get("id"))
        )
    wide: set[str] = set()
    for spans in by_wall.values():
        spans.sort()
        run_ids = [spans[0][2]]
        run_s0, run_s1 = spans[0][0], spans[0][1]
        for s0, s1, wid in spans[1:]:
            if s0 <= run_s1 + 1:  # 相邻/重叠 (1px 容差) -> 同一玻璃墙
                run_s1 = max(run_s1, s1)
                run_ids.append(wid)
            else:
                if run_s1 - run_s0 >= WINDOW_MIN_SPAN_PX:
                    wide.update(str(i) for i in run_ids if i is not None)
                run_ids = [wid]
                run_s0, run_s1 = s0, s1
        if run_s1 - run_s0 >= WINDOW_MIN_SPAN_PX:
            wide.update(str(i) for i in run_ids if i is not None)
    return wide


def _full_window_adjacent(box: tuple, windows: list[dict], wide_ids: set[str]) -> str | None:
    """footprint 是否紧贴玻璃幕墙 (id 在 wide_ids, gap<WINDOW_ADJ_PX 且沿窗方向投影重叠); 返回窗 id。"""
    for w in windows:
        if w.get("wtype") != "full" or str(w.get("id")) not in wide_ids:
            continue
        axis, at, span = w.get("axis"), w.get("at"), w.get("span") or [0, 0]
        if axis is None or at is None:
            continue
        at = float(at)
        s0, s1 = float(span[0]), float(span[1])
        if axis == "h":  # 横墙 y=at: 家具 x 投影须与窗 span 重叠, 上/下边贴近 at
            if min(box[2], s1) - max(box[0], s0) <= 0:
                continue
            if min(abs(box[1] - at), abs(box[3] - at)) <= WINDOW_ADJ_PX:
                return str(w.get("id") or "?")
        elif axis == "v":  # 竖墙 x=at
            if min(box[3], s1) - max(box[1], s0) <= 0:
                continue
            if min(abs(box[0] - at), abs(box[2] - at)) <= WINDOW_ADJ_PX:
                return str(w.get("id") or "?")
    return None


def _overlap_expected(t_a: Any, t_b: Any) -> bool:
    """该家具配对的重叠是否合法 (叠放件/组合沙发拼接/椅塞桌/床头贴床), 合法则碰撞检查跳过。"""
    if t_a in OVERLAY_TYPES or t_b in OVERLAY_TYPES:
        return True
    if t_a in SOFT_SEATING_TYPES and t_b in SOFT_SEATING_TYPES:
        return True  # 转角/组合沙发多件拼接
    if (t_a in SEATING_TYPES and t_b in TABLE_TYPES) or (
        t_b in SEATING_TYPES and t_a in TABLE_TYPES
    ):
        return True
    if (t_a in _BED_TYPES and t_b == "nightstand") or (t_b in _BED_TYPES and t_a == "nightstand"):
        return True
    return False


def lint_layout(scene: dict[str, Any], room_ids: set[str] | None = None) -> dict[str, Any]:
    """对 scene 的家具落位做设计质量体检 (纯只读, 不改 scene)。

    检查项 (均基于原始 furniture 落位 = 用户设计意图, 与轴测归一化前一致):
    - LAYOUT_WALL_UNIT_FLOATING: 柜类墙靠件远离所有墙面悬空 (酒柜/衣柜立于房间中央)。
    - LAYOUT_LARGE_BACKS_FULL_WINDOW: 大件紧贴玻璃幕墙 (背/侧贴落地窗, 挡光且不合理)。
    - LAYOUT_FURNITURE_OVERLAP: 两件家具明显重叠 (排除地毯/挂件/组合沙发/椅塞桌/床头贴床)。

    room_ids: 若提供, 只体检 _room_id 在其中的家具 (实拍出图只渲染照片那间房, 门禁按房作用域,
    避免另一间房脏牵连误拦); None=全屋 (编辑器/scene 端点主动展示)。

    门口/通道净空由 validate_scene 的 FURNITURE_BLOCKS_DOOR 覆盖, 此处不重复。
    """
    issues: list[dict[str, Any]] = []
    furniture = scene.get("furniture", [])
    if room_ids is not None:
        furniture = [it for it in furniture if str(it.get("_room_id")) in room_ids]
    wall_bboxes = scene.get("wall_bboxes", [])
    windows = scene.get("windows", [])
    wide_ids = _wide_full_window_ids(windows)
    group_of = _room_group_map(scene)

    boxes: list[tuple[dict, tuple]] = []
    for it in furniture:
        box = _box(it)
        if box is None:
            continue
        boxes.append((it, box))
        t = it.get("t")
        # 悬空: 仅柜类墙靠件 (座椅/床/几案可合法悬空)。
        if t in WALL_UNIT_TYPES:
            gap = _nearest_wall_gap(box, wall_bboxes)
            if gap > FLOATING_WALL_GAP_PX:
                issues.append(
                    _issue(
                        "WARN",
                        "LAYOUT_WALL_UNIT_FLOATING",
                        f"{_zh(t)}悬空于房间中央 (距最近墙 {gap * 10 / 1000:.1f}m), 柜类应背靠实墙",
                        index=it.get("_index"),
                        room_id=it.get("_room_id"),
                        wall_gap_mm=round(gap * 10, 0),
                    )
                )
        # 背贴玻璃幕墙: 高储物柜 + 大件座椅/床。
        if t in BACKS_WINDOW_TYPES:
            win = _full_window_adjacent(box, windows, wide_ids)
            if win is not None:
                issues.append(
                    _issue(
                        "WARN",
                        "LAYOUT_LARGE_BACKS_FULL_WINDOW",
                        f"{_zh(t)}紧贴落地窗 ({win}), 大件背/侧贴玻璃幕墙挡光且观感差",
                        index=it.get("_index"),
                        room_id=it.get("_room_id"),
                        window_id=win,
                    )
                )

    # 家具碰撞: 同一连通空间 (merge 组或同房) 两两比对, 排除合法重叠配对与擦碰级噪声。
    for i in range(len(boxes)):
        it_a, box_a = boxes[i]
        ga = group_of.get(str(it_a.get("_room_id")), str(it_a.get("_room_id")))
        for j in range(i + 1, len(boxes)):
            it_b, box_b = boxes[j]
            gb = group_of.get(str(it_b.get("_room_id")), str(it_b.get("_room_id")))
            if ga != gb:
                continue
            if _overlap_expected(it_a.get("t"), it_b.get("t")):
                continue
            ox = min(box_a[2], box_b[2]) - max(box_a[0], box_b[0])
            oy = min(box_a[3], box_b[3]) - max(box_a[1], box_b[1])
            if ox <= 0 or oy <= 0 or ox * oy < MIN_OVERLAP_PX2:
                continue
            issues.append(
                _issue(
                    "WARN",
                    "LAYOUT_FURNITURE_OVERLAP",
                    f"{_zh(it_a.get('t'))}与{_zh(it_b.get('t'))}明显重叠 "
                    f"({ox * 10 / 1000:.1f}×{oy * 10 / 1000:.1f}m), 应错开摆放",
                    index=it_a.get("_index"),
                    other_index=it_b.get("_index"),
                    room_id=it_a.get("_room_id"),
                    overlap={"x": round(ox, 1), "y": round(oy, 1)},
                )
            )

    errors = [i for i in issues if i.get("level") == "ERROR"]
    warnings = [i for i in issues if i.get("level") == "WARN"]
    return {
        "ok": not issues,  # 任一布局问题即非 ok (供可降级门禁判断); 全为 WARN 级 (设计建议)
        "issues": issues,
        "errors": errors,
        "warnings": warnings,
    }
