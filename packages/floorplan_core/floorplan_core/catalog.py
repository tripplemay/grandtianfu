# -*- coding: utf-8 -*-
"""家具目录: 受控类型词表 + 默认外观 (Phase 1.5a)。

AI 摆家具只从本目录选 `t` 并出"摆放"({room_id, dx/dy 或 dcx/dcy, rot}); 渲染所需的
w/h(或 r)/z/color 由本目录补 —— schema 拆分: **摆放 (AI/用户)** vs **外观 (目录)**。
单位同几何 (px, 1px=10mm)。默认值取自 axon 渲染器 + data/projects/D 真实家具分布。
结构件 (partition/entry_door/rug) 不入目录 (非可摆软装)。`rooms` = 适用的 geometry room.type。
"""
from __future__ import annotations

# t -> {en, shape, 默认尺寸, [z], [color], rooms}
CATALOG: dict[str, dict] = {
    # —— 卧室 ——
    "bed": {"en": "a bed", "shape": "rect", "w": 180, "h": 200, "rooms": ["bedroom"]},
    "nightstand": {"en": "a nightstand", "shape": "rect", "w": 40, "h": 45, "z": 470,
                   "color": "#8a633e", "rooms": ["bedroom"]},
    "wardrobe": {"en": "a wardrobe", "shape": "rect", "w": 120, "h": 60, "z": 2000,
                 "color": "#846752", "rooms": ["bedroom"]},
    # —— 起居/书房 ——
    "sofa": {"en": "a sofa", "shape": "rect", "w": 210, "h": 90, "color": "#b07a4e",
             "rooms": ["living"]},
    "chaise": {"en": "a chaise lounge", "shape": "rect", "w": 105, "h": 170, "color": "#3d5440",
               "rooms": ["living", "bedroom"]},
    "coffee_table": {"en": "a coffee table", "shape": "rect", "w": 100, "h": 60,
                     "rooms": ["living"]},
    "dining_table": {"en": "a long dining table with chairs", "shape": "rect", "w": 300, "h": 110,
                     "rooms": ["living"]},
    "chair": {"en": "an accent chair", "shape": "rect", "w": 60, "h": 60,
              "rooms": ["living", "bedroom"]},
    "swivel_chair": {"en": "a dark-green velvet swivel armchair", "shape": "rect", "w": 66, "h": 66,
                     "color": "#3d5440", "rooms": ["living"]},
    "desk": {"en": "a desk", "shape": "rect", "w": 120, "h": 60, "rooms": ["bedroom", "living"]},
    "bookshelf": {"en": "a full-height bookshelf", "shape": "rect", "w": 120, "h": 38, "z": 2000,
                  "color": "#846752", "rooms": ["bedroom", "living"]},
    "media": {"en": "a low TV media console", "shape": "rect", "w": 180, "h": 44,
              "rooms": ["living", "bedroom"]},
    "round_table": {"en": "a round side table", "shape": "round", "r": 20,
                    "rooms": ["living", "bedroom"]},
    # —— 通用收纳 ——
    "cabinet": {"en": "a cabinet", "shape": "rect", "w": 120, "h": 40, "z": 820, "color": "#8a633e",
                "rooms": ["living", "bedroom", "corridor"]},
    "tall_cabinet": {"en": "a tall cabinet", "shape": "rect", "w": 120, "h": 38, "z": 2000,
                     "color": "#846752", "rooms": ["living", "bedroom", "corridor"]},
    "bench": {"en": "a bench", "shape": "rect", "w": 165, "h": 50, "z": 430, "color": "#b07a4e",
              "rooms": ["living", "corridor"]},
    "plant": {"en": "potted plants", "shape": "round", "r": 20,
              "rooms": ["living", "bedroom", "outdoor", "corridor"]},
    # —— 厨房 (wet 系: 厨房 + 卫浴同 type=wet, AI 按房名区分) ——
    "kitchen": {"en": "kitchen cabinets with stone countertop, hob and sink", "shape": "rect",
                "w": 320, "h": 60, "rooms": ["wet", "living"]},
    "fridge": {"en": "a fridge", "shape": "rect", "w": 60, "h": 60, "z": 1780, "color": "#6a6d74",
               "rooms": ["wet", "living"]},
    "island": {"en": "a central island", "shape": "rect", "w": 120, "h": 130,
               "rooms": ["wet", "living"]},
    "washer_dryer": {"en": "a stacked washer-dryer", "shape": "rect", "w": 68, "h": 80, "z": 1820,
                     "rooms": ["wet", "outdoor"]},
    # —— 卫浴 ——
    "vanity": {"en": "a vanity with basin", "shape": "rect", "w": 120, "h": 55, "rooms": ["wet"]},
    "toilet": {"en": "a toilet", "shape": "rect", "w": 55, "h": 80, "rooms": ["wet"]},
    "tub": {"en": "a freestanding bathtub", "shape": "rect", "w": 72, "h": 160, "rooms": ["wet"]},
    "shower": {"en": "a glass shower", "shape": "rect", "w": 95, "h": 120, "rooms": ["wet"]},
}

_APPEARANCE_KEYS = ("z", "color")


def types_for_room(room_type: str) -> list[str]:
    """该 room.type 可选的家具类型 (供 AI 选型 + 校验)。"""
    return [t for t, spec in CATALOG.items() if room_type in spec["rooms"]]


def appearance(t: str) -> dict | None:
    """类型的默认外观 (w/h 或 r, z?, color?); 未知类型返回 None。"""
    spec = CATALOG.get(t)
    if spec is None:
        return None
    out: dict = {}
    if spec["shape"] == "round":
        out["r"] = spec["r"]
    else:
        out["w"] = spec["w"]
        out["h"] = spec["h"]
    for k in _APPEARANCE_KEYS:
        if k in spec:
            out[k] = spec[k]
    return out


def expand(items: list[dict]) -> list[dict]:
    """把"摆放"件补全为可渲染的完整件 (目录填 w/h/r/z/color, 不覆盖已有值)。

    幂等: 对已含完整外观的现有数据为 no-op (setdefault); 未知类型/结构件原样透传。
    遵循不可变: 每件返回新 dict, 不改入参。
    """
    out = []
    for it in items:
        app = appearance(it.get("t"))
        ni = dict(it)
        if app is not None:
            for k, v in app.items():
                ni.setdefault(k, v)
        out.append(ni)
    return out
