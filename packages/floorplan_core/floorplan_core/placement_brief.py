# -*- coding: utf-8 -*-
"""placement_brief — 放置简报编译器 (render-relation-b1 F001, spec §D1/D4)。

把「方案家具在几何里的落位」编译成**中文自然语言约束清单** (放置简报), 供实拍出图
relational 档: 编辑模型按简报摆家具 (取代轴测软参考/彩盒几何锁定), VLM 按同一份清单
逐条验收。评测依据 (route-eval-real-render-2026-07-23): 关系约束通道放置命中率 93%,
显著优于轴测图通道 65% —— 视角不变的关系语言比跨视角的图像参考更能传递方案意图。

纯 stdlib、确定性 (同输入同输出), 对既有渲染零字节影响 (本模块只新增)。

语义规则 (与评测原型逐条核对, 勿随意改):
  - orient = 家具**靠背/所贴墙**的方向 (不是朝向) —— 沙发 orient=W 即靠背靠西墙、面向东;
  - 贴墙判定用**家具边缘与墙的缝隙** (≤300mm 贴墙, ≤1200mm 靠近, 更远=房间中部), 不用中心距;
  - 作用域 = 照片绑定房的 merge 组并集; 按**几何位置** (家具中心落在哪个成员 rect) 判
    「照片房 / 相连空间」—— 相连空间家具只进 linked_lines (可能在画面外), 不进验收约束;
  - 关系模板按实际数量生成 (几个床头柜写几个), 超编辑模型能力的约束软化
    (「整面悬挂窗帘」→「沿窗墙布置窗帘」)。

视角映射 (v0..v3 -> 镜头朝向, 世界系 X=东+, Y=南+): 自 apps/api/main.py 搬入 (单一真源,
main 改调本模块, 消除 _VIEW_FORWARDS/_VIEW_FACING_ZH 双写)。轴测镜头恒「从近角看向里角」
(k=0 里角=NW), v1/v2/v3 = 90/180/270° 顺时针; 生产交叉验证: f4d(v1) 朝 SW、798(v3) 朝 NE。
"""

from __future__ import annotations

from . import axon, catalog

# v0..v3 -> 期望相机水平朝向 (与 main.py 原 _VIEW_FORWARDS 逐值一致, 勿改)。
VIEW_FORWARDS = {"v0": (-1.0, -1.0), "v1": (-1.0, 1.0), "v2": (1.0, 1.0), "v3": (1.0, -1.0)}
# 同一映射的中文方位 (与 main.py 原 _VIEW_FACING_ZH 逐值一致)。
VIEW_FACING_ZH = {"v0": "西北", "v1": "西南", "v2": "东南", "v3": "东北"}

_SIDE_ZH = {"N": "北", "S": "南", "E": "东", "W": "西"}
# orient 文案适用的类型 (有明确靠背/床头语义的大件)。
_ORIENT_BACK_TYPES = {"sofa", "bed", "chaise", "media", "dresser", "desk", "bench"}
# 不进入简报的顶层类型 (结构件)。
_SKIP_TYPES = {"partition", "entry_door"}
# 贴墙缝隙阈值 (px, 1px=10mm): ≤30px=300mm 贴墙; ≤120px=1200mm 靠近; 更远=房间中部。
_FLUSH_GAP_PX = 30.0
_NEAR_GAP_PX = 120.0


def _rooms_by_id(G: dict) -> dict:
    return {str(r["id"]): r for r in G.get("rooms", []) if "id" in r}


def _members(G: dict, room_id: str) -> list[str]:
    try:
        ids = sorted(str(m) for m in axon.merge_group_ids(G, str(room_id)))
    except Exception:  # noqa: BLE001 - 房间已删/无 merge: 退回本房 (同 main 侧容错)
        ids = [str(room_id)]
    return ids or [str(room_id)]


def _rect_of(rooms_by_id: dict, room_id: str):
    x, y, w, h = rooms_by_id[room_id]["rect"]
    return float(x), float(y), float(x + w), float(y + h)


def _wall_openings(G: dict, members: list[str], rooms_by_id: dict) -> dict:
    """{member_id: {side: [开口描述]}} — 开口须贴该成员的对应边界。"""
    rects = {m: _rect_of(rooms_by_id, m) for m in members if m in rooms_by_id}
    out = {m: {"N": [], "S": [], "E": [], "W": []} for m in rects}
    for op in G.get("openings", []) or []:
        wall = op.get("wall") or {}
        axis, at, span = wall.get("axis"), wall.get("at"), wall.get("span")
        if axis not in ("h", "v") or at is None or not span or len(span) != 2:
            continue
        at = float(at)
        for m, (x0, y0, x1, y1) in rects.items():
            side = None
            if axis == "v" and abs(at - x0) <= 1.0:
                side = "W"
            elif axis == "v" and abs(at - x1) <= 1.0:
                side = "E"
            elif axis == "h" and abs(at - y0) <= 1.0:
                side = "N"
            elif axis == "h" and abs(at - y1) <= 1.0:
                side = "S"
            if side is None:
                continue
            lo, hi = (y0, y1) if axis == "v" else (x0, x1)
            if float(span[1]) < lo - 1 or float(span[0]) > hi + 1:
                continue
            kind = op.get("kind")
            if kind == "window":
                desc = (
                    "落地窗"
                    if op.get("wtype") == "full"
                    else ("高窗" if op.get("wtype") == "high" else "窗")
                )
            elif kind == "door":
                mat = "玻璃推拉门" if op.get("material") == "glass" else "木门"
                bt = [b for b in (op.get("between") or []) if b]
                desc = f"{mat}(通往{bt[0] if bt else '相邻空间'})"
            else:
                desc = "门洞"
            out[m][side].append(desc)
    return out


def _wall_desc(openings: list[str], side: str) -> str:
    if not openings:
        return f"{_SIDE_ZH[side]}侧实墙"
    return f"{_SIDE_ZH[side]}墙（{'、'.join(sorted(set(openings)))}）"


def _group_wall_labels(G: dict, members: list[str], rooms_by_id: dict, ops: dict) -> dict:
    """世界方向 -> 组级墙标签 (该方向全体成员的开口描述并集), 供画面四至锚定。"""
    labels = {}
    for side in ("N", "S", "E", "W"):
        descs: list[str] = []
        for m in members:
            descs += (ops.get(m) or {}).get(side, [])
        labels[side] = _wall_desc(descs, side)
    return labels


def _locate_member(cx: float, cy: float, members: list[str], rooms_by_id: dict) -> str:
    """家具中心几何位置 -> 所在成员房 (判『照片房/相连空间』用, 不用 _room_id ——
    merge 组内家具的登记房与几何位置可不同, 如登记 r_live 实际落在相邻窄条)。"""
    for m in members:
        if m not in rooms_by_id:
            continue
        x0, y0, x1, y1 = _rect_of(rooms_by_id, m)
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return m
    return members[0]


def _item_abs_rect(it: dict, rooms_by_id: dict):
    """场景家具 (含 _dx/_dy 归一化回填) -> 绝对 px 矩形; 无坐标 (未落位) 返回 None。"""
    rid = str(it.get("_room_id") or it.get("room_id") or "")
    if rid not in rooms_by_id:
        return None
    dx = it.get("_dx", it.get("dx"))
    dy = it.get("_dy", it.get("dy"))
    if dx is None or dy is None:
        return None
    x0, y0, _, _ = _rect_of(rooms_by_id, rid)
    return x0 + float(dx), y0 + float(dy), float(it.get("w") or 0), float(it.get("h") or 0)


def _nearest_side(cx: float, cy: float, rect) -> str:
    x0, y0, x1, y1 = rect
    d = {"W": cx - x0, "E": x1 - cx, "N": cy - y0, "S": y1 - cy}
    return min(d, key=d.get)


def _edge_gap(ax: float, ay: float, w: float, h: float, rect, side: str) -> float:
    x0, y0, x1, y1 = rect
    return {
        "W": ax - x0,
        "E": x1 - (ax + w),
        "N": ay - y0,
        "S": y1 - (ay + h),
    }[side]


def _along_frac(pos: float, lo: float, hi: float) -> float:
    return (pos - lo) / max(1.0, hi - lo)


def _along_text(frac: float, side: str) -> str:
    a, b = {"N": ("西", "东"), "S": ("西", "东"), "W": ("北", "南"), "E": ("北", "南")}[side]
    if frac < 0.33:
        return f"靠{a}端"
    if frac > 0.67:
        return f"靠{b}端"
    return "中部"


def _frame_text(direction, labels: dict) -> str | None:
    """拍摄视角 -> 画面四至中文描述 (v0..v3 均斜向: 前方=两面墙夹角, 左右按右向量区分)。"""
    fwd = VIEW_FORWARDS.get(direction or "")
    if fwd is None:
        return None
    fx, fy = fwd
    rx, ry = -fy, fx  # 相机右手方向的世界向量
    ahead_s = {"E": fx, "W": -fx, "S": fy, "N": -fy}
    right_s = {"E": rx, "W": -rx, "S": ry, "N": -ry}
    front = sorted((s for s in "ESWN" if ahead_s[s] > 0.1), key=lambda s: (-ahead_s[s], s))
    back = sorted((s for s in "ESWN" if ahead_s[s] < -0.1), key=lambda s: (ahead_s[s], s))
    if len(front) >= 2:
        right = max(front, key=lambda s: right_s[s])
        left = min(front, key=lambda s: right_s[s])
        return (
            f"这张照片是从房间的{'、'.join(labels[s] for s in back)}夹角一侧，"
            f"朝{'与'.join(labels[s] for s in front)}的夹角方向拍摄的。"
            f"画面中：左侧远处是{labels[left]}；右侧远处是{labels[right]}；"
            "正前方是这两面墙的夹角区域。"
        )
    if front:
        return (
            f"这张照片朝{labels[front[0]]}方向拍摄，"
            f"正前方是{labels[front[0]]}，背面是{labels[back[0]] if back else '身后'}。"
        )
    return None


# catalog 的 zh 是 2D 平面图短标签 (media->影视, bed->床, curtain->窗帘, nightstand->床头,
# cabinet->柜) —— 简报是自然语言文本 (给编辑模型/VLM 看), 对 terse 短标签做自然名覆盖;
# 未覆盖的回退 catalog zh (新类型零成本接入)。
_LABEL_OVERRIDES = {
    "media": "电视柜",
    "curtain": "落地窗帘",
    "bed": "双人床",
    "nightstand": "床头柜",
    "cabinet": "边柜",
}


def _zh(t: str) -> str:
    if t in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[t]
    return str((catalog.CATALOG.get(t) or {}).get("zh") or t)


def build_brief(G: dict, scene: dict, room_id: str, direction: str | None = None) -> dict:
    """编译放置简报 -> {room_id, members, direction, frame, placement_lines, constraints,
    linked_lines}。

    G: 户型几何 dict (rooms/openings/meta); scene: build_scene 输出 (axon_furniture 已归一化,
    _dx/_dy 回填); room_id: 照片绑定房; direction: v0..v3 或 None (缺省时 frame=None 降级)。
    placement_lines = 生成 prompt 用的全量约束 (照片房 + 相连空间均列出);
    constraints = 验收用的可核对清单 (仅照片房 + 房内关系, 相连空间不入 —— 可能在画面外);
    linked_lines = 相连空间家具行 (附『可能在画面外』后缀)。
    """
    rooms_by_id = _rooms_by_id(G)
    room_id = str(room_id)
    members = _members(G, room_id)
    ops = _wall_openings(G, members, rooms_by_id)
    labels = _group_wall_labels(G, members, rooms_by_id, ops)
    frame = _frame_text(direction, labels)

    items: list[dict] = []
    for it in scene.get("axon_furniture", []) or []:
        t = it.get("t")
        if not t or t in _SKIP_TYPES:
            continue
        rid = str(it.get("_room_id") or it.get("room_id") or "")
        if rid not in members:
            continue
        rect = _item_abs_rect(it, rooms_by_id)
        if rect is None:
            continue  # 未落位 (plants 等无坐标)
        items.append((it, rect))

    lines: list[str] = []
    constraints: list[str] = []
    linked_lines: list[str] = []
    located: dict[str, list] = {}  # t -> [(cx, cy, scope)] 供关系模板
    art_idx = 0
    for it, (ax, ay, w, h) in items:
        t = it["t"]
        zh = _zh(t)
        cx, cy = ax + w / 2, ay + h / 2
        home = _locate_member(cx, cy, members, rooms_by_id)
        scope = "photo_room" if home == room_id else "linked"
        located.setdefault(t, []).append((cx, cy, scope))
        mrect = _rect_of(rooms_by_id, home)
        side = _nearest_side(cx, cy, mrect)
        gap = _edge_gap(ax, ay, w, h, mrect, side)
        wall = _wall_desc((ops.get(home) or {}).get(side, []), side)
        frac = _along_frac(
            cx if side in ("N", "S") else cy,
            mrect[0] if side in ("N", "S") else mrect[1],
            mrect[2] if side in ("N", "S") else mrect[3],
        )
        along = _along_text(frac, side)
        size_m = f"{max(w, h) / 100:.1f}m" if max(w, h) > 0 else ""
        if t == "curtain":
            c = f"{zh}沿{wall}布置（落地帘，从墙的一端到另一端）"
        elif t == "rug":
            c = f"{zh}（约{w / 100:.1f}×{h / 100:.1f}m）铺在房间中部活动区地面"
        elif t == "wall_art":
            art_idx += 1
            c = f"{zh}#{art_idx}挂在{wall}（{along}位置，挂画中心约离地1.5m）"
        elif gap <= _FLUSH_GAP_PX:
            c = f"{zh}（长约{size_m}）贴{wall}摆放，位于该墙{along}"
        elif gap <= _NEAR_GAP_PX:
            c = f"{zh}（长约{size_m}）靠近{wall}摆放（距墙约{gap * 10:.0f}mm），位于该墙{along}"
        else:
            c = f"{zh}（长约{size_m}）位于房间中部区域，与{wall}保持明显距离"
        orient = it.get("orient")
        if orient in ("N", "S", "E", "W") and t in _ORIENT_BACK_TYPES:
            face = {"N": "S", "S": "N", "E": "W", "W": "E"}[orient]
            c += f"，{'床头' if t == 'bed' else '靠背'}靠{_SIDE_ZH[orient]}侧、面向{_SIDE_ZH[face]}"
        lines.append(c)
        if scope == "photo_room":
            constraints.append(c)
        else:
            linked_lines.append(c + "（相连空间，可能在画面外）")

    # 关键相对关系 (类型模板, 按实际数量生成 —— 评测缺陷 D4-2: 不得硬写数量)。
    def centers(t: str, scope: str = "photo_room") -> list:
        return [(x, y) for x, y, s in located.get(t, []) if s == scope]

    rels: list[str] = []
    sofas, medias, coffees = centers("sofa"), centers("media"), centers("coffee_table")
    if sofas and medias:
        rels.append("沙发组合与电视柜面对面布置（人坐在沙发上正好面对电视柜）")
    if coffees and sofas:
        rels.append("茶几在沙发组合旁边（紧邻沙发、方便伸手取物）")
    if centers("rug") and (sofas or coffees):
        rels.append("地毯压在沙发/茶几区域下方")
    if centers("dining_table"):
        kitchen_wall = None
        for m in members:
            for side in ("N", "S", "E", "W"):
                for d in (ops.get(m) or {}).get(side, []):
                    if "kitchen" in d or "厨房" in d:
                        kitchen_wall = _wall_desc((ops.get(m) or {}).get(side, []), side)
        rels.append(f"餐桌位于{kitchen_wall or '厨房门'}附近")
    beds, nights = centers("bed"), centers("nightstand")
    if beds and nights:
        n = len(nights)
        if n >= 2:
            rels.append(f"{n}个床头柜分列双人床左右两侧、紧贴床头")
        else:
            rels.append("床头柜紧靠双人床床头一侧摆放")
    if centers("wine_cabinet"):
        rels.append("酒柜位于入户门厅一侧的墙边")
    lines += rels
    constraints += rels  # 关系约束均针对照片房内家具, 可核对
    # 相连空间的关系行 (评测实证: 酒柜落 merge 组相邻窄条但客厅照可见 —— 进 linked 不入验收)
    if any(s == "linked" for _x, _y, s in located.get("wine_cabinet", [])):
        linked_lines.append("酒柜位于入户门厅一侧的墙边（相连空间，可能在画面外）")

    return {
        "room_id": room_id,
        "members": members,
        "direction": direction,
        "frame": frame,
        "placement_lines": lines,
        "constraints": constraints,
        "linked_lines": linked_lines,
    }
