# -*- coding: utf-8 -*-
"""
从 furniture.json + 几何SVG 自动生成 4D 图生图提示词(逐房家具+材质),与家具表永久同步。
被 build.py 调用,输出 4D提示词-自动生成.txt。也可单独:python3 prompt_gen.py
"""
import os, re, json, math
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
from . import axon as eng
from . import catalog as _catalog
from . import geometry as _geometry

# 墙面材质枚举 -> 英文描述 (材质A: 语义标签; photo_id 参考图为 P2 材质C)。
WALL_MATERIAL_EN = {
    "wood_panel": "warm walnut wood veneer paneling",
    "stone": "natural stone slab cladding",
    "tile": "glossy ceramic tile",
    "paint": "matte painted finish",
    "mirror": "full-height mirror finish",
    "wallpaper": "textured wallpaper",
}

# 家具英文短语单一真源 = catalog.CATALOG[t].en (原 TYPE_EN 重复词表已删, 逐字节等价)。
MAT = {"living": "warm beige travertine stone floor, off-white walls", "corridor": "travertine stone floor, off-white walls",
       "bedroom": "warm oak wood floor, off-white walls", "wet": "grey marble/microcement floor and walls",
       "outdoor": "grey microcement floor with greenery", "public": "plain neutral grey"}
CN = {"zh-label": ""}
NUM = {1: "", 2: "two ", 3: "three ", 4: "four "}

def room_names(svg_path):
    """房间矩形 -> 中文名(由 zh-label 落在矩形内匹配)。返回 {('type',x,y): name}"""
    svg = open(svg_path, encoding="utf-8-sig").read()
    geo = svg.split('transform="translate(150, 250)"')[1]
    body = geo.split('<g id="room_labels">'); labels = []
    if len(body) > 1:
        for m in re.finditer(r'<text class="zh-label" x="([\d.]+)" y="([\d.]+)">([^<]+)</text>', body[1]):
            labels.append((float(m.group(1)), float(m.group(2)), m.group(3)))
    rooms, _, _ = eng.parse_geometry(svg_path)
    out = {}
    for t, x, y, w, h in rooms:
        # 忽略"入户门"这类标注label,取真正的房名
        nm = next((n for lx, ly, n in labels if x <= lx <= x+w and y <= ly <= y+h and n not in ("入户门",)), t)
        out[(t, int(x), int(y))] = nm
    return out
NAME_MAT = {"厨房": "light grey porcelain tile floor, pale grey cabinetry walls",
            "生活阳台": "grey microcement floor (laundry/utility)"}

def room_names_geo(G):
    """从 geometry.json 的 G dict 取房名映射 {(type,int(x),int(y)): name} (方案B 单一真源)。"""
    out = {}
    for r in G["rooms"]:
        x, y = r["rect"][0], r["rect"][1]
        nm = (r.get("label") or {}).get("zh") or r["type"]
        out[(r["type"], int(x), int(y))] = nm
    return out

def rooms_by_id(G):
    """room_id -> (中文名, room_type) (B1: 家具按 room_id 取房名)。"""
    out = {}
    for r in G["rooms"]:
        nm = (r.get("label") or {}).get("zh") or r["type"]
        out[r["id"]] = (nm, r["type"])
    return out

def _zone_phrase(it, rect, base_off=(0.0, 0.0)):
    """家具相对偏移 + 房间 rect -> 房内方位短语 (沿北/东墙 / 居中 / 西北角)。

    强化 img2img 模型"保持家具不漂移": 由 {dx,dy}(矩形中心=偏移+半尺寸) 或 {dcx,dcy}(圆形中心)
    与房间 rect 的三等分判定方位。坐标系同平面 (北=dy 小)。
    base_off (P5 异形二期): 成员腿原点相对逻辑房并集原点的偏移 —— 把成员相对中心平移到并集
    坐标系后按并集 rect 三等分, 使 L 形房方位一致。缺省 (0,0) 时与改造前逐字节一致。
    """
    rw, rh = rect[2], rect[3]
    if "dcx" in it or "dcy" in it:            # 圆形件: 中心即 dcx/dcy
        cx, cy = it.get("dcx", 0), it.get("dcy", 0)
    else:                                     # 矩形件: 中心 = 偏移 + 半尺寸
        cx = it.get("dx", 0) + it.get("w", 0) / 2
        cy = it.get("dy", 0) + it.get("h", 0) / 2
    cx += base_off[0]
    cy += base_off[1]
    ns = "north" if cy < rh / 3 else ("south" if cy > 2 * rh / 3 else "")
    ew = "west" if cx < rw / 3 else ("east" if cx > 2 * rw / 3 else "")
    if ns and ew:
        return f"in the {ns}-{ew} corner"
    if ns:
        return f"against the {ns} wall"
    if ew:
        return f"against the {ew} wall"
    return "in the centre"


def generate(furniture_json, geometry, with_positions=False, style=None):
    """逐房家具 img2img 提示词。

    furniture_json: 路径 或 已载入的家具列表 (供 API 直接传内存数据)。
    with_positions=True: 每件附"房内方位"短语, 强化模型保家具不漂移 (Phase1.5b, A/B 验证后定默认)。
    默认 False -> 与历史输出逐字节一致 (build.py / 既有 4D 提示词不变)。"""
    items = (json.load(open(furniture_json, encoding="utf-8"))
             if isinstance(furniture_json, str) else furniture_json)
    is_G = isinstance(geometry, dict)
    rn = room_names_geo(geometry) if is_G else room_names(geometry)
    id2room = rooms_by_id(geometry) if is_G else {}
    id2rect = {r["id"]: r["rect"] for r in geometry["rooms"]} if is_G else {}
    # 异形 (P3): merge 组成员 -> 代表房, 使同组家具并入同一条逻辑房 prompt line。
    # 无 merge 时为空表 -> rep==rid, 输出逐字节不变。
    group_rep = _geometry.group_rep_map(geometry) if is_G else {}
    # 异形二期 (P5): 方位短语按逻辑房【并集 bbox】三等分 (而非单腿), L 形方位才正确。
    mg = _geometry.merge_groups(geometry) if is_G else {}
    grp_of = {rid: gid for gid, gr in mg.items() for rid in gr["members"]}
    # 墙面材质标注 (升级计划 P1 / 墙面材质A): 逐墙英文短语, 无标注时输出逐字节不变。
    name2walls = {}
    if is_G:
        for r in geometry["rooms"]:
            nm = (r.get("label") or {}).get("zh") or r["id"]
            if isinstance(r.get("walls"), dict):
                name2walls.setdefault(nm, {}).update(r["walls"])
    # 按房间聚合家具 (条目 = (type, zone|None))
    by_room = {}
    for it in items:
        if it["t"] in ("partition", "rug"): continue
        rid = it.get("room_id")
        if rid is not None and is_G:          # B1: room_id -> 房名 (单一真源)
            rep = group_rep.get(rid, rid)     # 异形: 归到代表房 -> 同组家具并一条 line
            name, rtype = id2room.get(rep, ("其它", "living"))
            zone = None
            if with_positions and rid in id2rect:
                gid = grp_of.get(rid)
                if gid:                        # 异形二期: 按并集 bbox 定方位
                    gx0, gy0, gx1, gy1 = mg[gid]["bbox"]
                    mrect = id2rect[rid]
                    zone = _zone_phrase(
                        it, (gx0, gy0, gx1 - gx0, gy1 - gy0),
                        base_off=(mrect[0] - gx0, mrect[1] - gy0),
                    )
                else:                          # 单房: 与改造前逐字节一致
                    zone = _zone_phrase(it, id2rect[rid])
        else:                                 # 向后兼容: 旧 room 复合键
            key = it.get("room", "?")
            try:
                t, xy = key.split(":"); x, y = xy.split(","); rk = (t, int(x), int(y))
            except Exception:
                rk = None
            name = rn.get(rk, "其它")
            rtype = rk[0] if rk else "living"
            zone = None
        by_room.setdefault((name, rtype), []).append((it["t"], zone))
    lines = []
    for (name, rtype), entries in by_room.items():
        if name in ("公共电梯厅", "公共楼梯间"): continue
        cnt = {}  # (type, zone) -> count, 保持出现顺序; zone=None 时退化为原 (按 type) 分组
        for t, zone in entries:
            if t in ("entry_door",):  # 入户门单独描述
                cnt[("entry", None)] = 1; continue
            # 单一真源 (升级计划 P0/P2): 家具英文短语全部取 catalog.en ——
            # 目录扩充期新增类型不再在提示词里静默漏述。
            if (_catalog.CATALOG.get(t) or {}).get("en"):
                k = (t, zone); cnt[k] = cnt.get(k, 0) + 1
        if not cnt: continue
        parts = []
        if cnt.pop(("entry", None), 0): parts.append("the entry door on its outer wall")
        for (t, zone), n in cnt.items():
            d = (_catalog.CATALOG.get(t) or {}).get("en")
            if n > 1:  # 复数化
                d = NUM.get(n, f"{n} ") + d.replace("a ", "", 1).replace("an ", "", 1) + ("s" if not d.endswith("s") and not d.startswith("kitchen") else "")
            if zone:
                d = d + " " + zone
            parts.append(d)
        mat = NAME_MAT.get(name, MAT.get(rtype, "off-white walls"))
        for side, finish in sorted((name2walls.get(name) or {}).items()):
            # 材质C (P2): 该面已贴实拍参考图 -> 语义短语让位给真图 (作为 edits 参考注入),
            # 避免'文字说木饰面 vs 照片是别的'双重信号。无 photo_id 时按材质A 出短语。
            if isinstance(finish, dict) and finish.get("photo_id"):
                continue
            material = (finish or {}).get("material") if isinstance(finish, dict) else None
            phrase = WALL_MATERIAL_EN.get(material)
            if phrase:
                side_en = {"N": "north", "S": "south", "E": "east", "W": "west"}.get(side)
                if side_en:
                    parts.append(f"the {side_en} wall clad in {phrase}")
        lines.append(f"- {name} [{mat}]: " + ", ".join(parts) + ".")
    # style 贯通 (审计 P0-6): 方案的 style_prompt 注入 head, 并把默认 palette 从指令降级为建议;
    # style=None 时保持既有字节输出不变 (保护 build.py 与历史提示词基线)。
    style_head = (
        f"Make this 3D isometric furnished apartment photorealistic in this style: {style}.\n"
        if style
        else "Make this 3D isometric furnished apartment photorealistic in a modern light-luxury (现代轻奢) style.\n"
    )
    head = (
        style_head
        + "KEEP EXACTLY the same camera angle, isometric 3D geometry, walls, window positions, and every piece of\n"
        "furniture in its drawn position, size and orientation — do NOT move, add, remove, merge or re-assign\n"
        "anything. Only convert flat shapes into realistic materials, lighting and soft furnishings. No roof.\n"
        "Room labels are for reference only; do not render any text.\n\nPer room (furniture & materials):")
    palette_line = (
        "Palette: follow the requested style above; default accents only if unspecified.\n"
        if style
        else "Palette: walnut wood, beige travertine, white marble, grey microcement, caramel leather, dark-green velvet,\n"
        "brushed brass, cream textiles, sheer curtains, warm cove lighting, soft daylight, ultra detailed.\n"
    )
    tail = (
        "\n\nWindows: clear glass; south-facing windows are floor-to-ceiling; bathrooms have high clerestory windows.\n"
        + palette_line
        + "Camera: strong 35-45° isometric — do NOT flatten to top-down.")
    return head + "\n" + "\n".join(lines) + tail

def write(furniture_json, geometry_svg, out_txt, with_positions=False):
    p = generate(furniture_json, geometry_svg, with_positions=with_positions)
    open(out_txt, "w", encoding="utf-8").write(p)
    print(f"wrote {out_txt}")
    return p

if __name__ == "__main__":
    write(f"{HERE}/furniture-D户型.json", f"{ROOT}/平面布置图-无家具.svg", f"{HERE}/4D提示词-自动生成.txt")
