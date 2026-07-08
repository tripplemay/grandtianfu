# -*- coding: utf-8 -*-
"""家具目录: 受控类型词表 + 默认外观 (Phase 1.5a)。

AI 摆家具只从本目录选 `t` 并出"摆放"({room_id, dx/dy 或 dcx/dcy, orient}); 渲染所需的
w/h(或 r)/z/color 由本目录补 —— schema 拆分: **摆放 (AI/用户)** vs **外观 (目录)**。
单位 (审计 P1-6 显式契约): dx/dy/dcx/dcy/w/h/r = px (1px=10mm); **z = mm** (与
meta.wall_height_mm 同单位, axon 按 z*ZK 折 px)。默认值取自 axon 渲染器 + D 真实家具分布。
结构件 (partition/entry_door/rug) 不入目录 (非可摆软装)。`rooms` = 适用的 geometry room.type。
"""
from __future__ import annotations

# 目录修订号 (审计 P2-6): 方案创建时记录 catalog_rev, 目录演进后可识别哪些方案
# 的固化外观可安全刷新 (「重新应用目录外观」按 rev 差异)。改动默认尺寸/配色时 +1。
CATALOG_REV = 1

# 目录条目 schema (P2 单一真源收敛 —— 「一个类型只在此处声明」):
#   en           : img2img 提示词英文短语 (prompt_gen 单一来源, 原 TYPE_EN 已删)
#   shape        : "rect" | "round"
#   w/h | r      : 默认尺寸 (px, 1px=10mm)
#   z            : 挤出高度 (mm, 可选)
#   color        : 轴测 3D 盒基色 (可选)
#   rooms        : 适用的 geometry room.type (AI 选型 + 校验)
#   zh           : 中文短标签 (前端家具库 / 列表显示; /api/catalog 出参)
#   category     : 前端家具库分组 key (bedroom/living/storage/kitchen/decor)
#   cat2d        : (fill, stroke) —— 2D 平面渲染配色 (原 axon.CAT2D)
#   label2d      : 2D 平面中文标注 (原 axon.NAME2D; 仅部分类型标注, 缺省不标)
#   tall         : True=高件, 受墙高夹取 (原 scene.HEIGHT_CONSTRAINED_DEFAULTS)
#   directional  : True=落位按贴靠最近墙写 orient (原 layout.DIRECTIONAL_TYPES)
# 派生消费方 (axon.CAT2D/NAME2D、scene 高件、layout 方向件) 均从本表推导, 逐字节由
# render 快照 golden 护栏 (test_render_snapshot) 锁死。
MAX_TALL_FURNITURE_Z = 1400

CATALOG: dict[str, dict] = {
    # —— 卧室 ——
    "bed": {"en": "a bed", "shape": "rect", "w": 180, "h": 200, "rooms": ["bedroom"],
            "zh": "床", "category": "bedroom", "directional": True,
            "cat2d": ("#e3c9a6", "#b78f5e"), "label2d": "双人床"},
    "nightstand": {"en": "a nightstand", "shape": "rect", "w": 40, "h": 45, "z": 470,
                   "color": "#8a633e", "rooms": ["bedroom"],
                   "zh": "床头", "category": "bedroom", "cat2d": ("#ece0c8", "#b9a274")},
    "wardrobe": {"en": "a wardrobe", "shape": "rect", "w": 120, "h": 60, "z": MAX_TALL_FURNITURE_Z,
                 "color": "#846752", "rooms": ["bedroom"],
                 "zh": "衣柜", "category": "bedroom", "tall": True, "directional": True,
                 "cat2d": ("#cdb18f", "#a9895c"), "label2d": "衣柜"},
    # —— 起居/书房 ——
    "sofa": {"en": "a sofa", "shape": "rect", "w": 210, "h": 90, "color": "#b07a4e",
             "rooms": ["living"],
             "zh": "沙发", "category": "living", "directional": True,
             "cat2d": ("#d8c19c", "#a9895c"), "label2d": "沙发"},
    "chaise": {"en": "a chaise lounge", "shape": "rect", "w": 105, "h": 170, "color": "#3d5440",
               "rooms": ["living", "bedroom"],
               "zh": "贵妃", "category": "living", "cat2d": ("#cdd9e0", "#7a93a0"), "label2d": "贵妃榻"},
    "coffee_table": {"en": "a coffee table", "shape": "rect", "w": 100, "h": 60,
                     "rooms": ["living"],
                     "zh": "茶几", "category": "living", "cat2d": ("#e7d9bb", "#b9ad8a"), "label2d": "茶几"},
    "dining_table": {"en": "a long dining table with chairs", "shape": "rect", "w": 300, "h": 110,
                     "rooms": ["living"],
                     "zh": "餐桌", "category": "kitchen", "cat2d": ("#ece0c8", "#b9a274"), "label2d": "餐桌"},
    "chair": {"en": "an accent chair", "shape": "rect", "w": 60, "h": 60,
              "rooms": ["living", "bedroom"],
              "zh": "椅", "category": "living", "cat2d": ("#cfe0d4", "#7fa088")},
    "swivel_chair": {"en": "a dark-green velvet swivel armchair", "shape": "rect", "w": 66, "h": 66,
                     "color": "#3d5440", "rooms": ["living"],
                     "zh": "旋椅", "category": "living", "cat2d": ("#cfe0d4", "#7fa088"), "label2d": "旋转椅"},
    "desk": {"en": "a desk", "shape": "rect", "w": 120, "h": 60, "rooms": ["bedroom", "living"],
             "zh": "书桌", "category": "storage", "directional": True,
             "cat2d": ("#ece0c8", "#b9a274"), "label2d": "书桌"},
    "bookshelf": {"en": "a full-height bookshelf", "shape": "rect", "w": 120, "h": 38, "z": MAX_TALL_FURNITURE_Z,
                  "color": "#846752", "rooms": ["bedroom", "living"],
                  "zh": "书柜", "category": "storage", "tall": True, "directional": True,
                  "cat2d": ("#ece0c8", "#b9a274"), "label2d": "书柜"},
    "media": {"en": "a low TV media console", "shape": "rect", "w": 180, "h": 44,
              "rooms": ["living", "bedroom"],
              "zh": "影视", "category": "living", "directional": True,
              "cat2d": ("#cdb18f", "#8a6a44"), "label2d": "影视柜"},
    "round_table": {"en": "a round side table", "shape": "round", "r": 20,
                    "rooms": ["living", "bedroom"],
                    "zh": "圆几", "category": "kitchen", "cat2d": ("#e7d9bb", "#b9ad8a")},
    # —— 通用收纳 ——
    "cabinet": {"en": "a cabinet", "shape": "rect", "w": 120, "h": 40, "z": 820, "color": "#8a633e",
                "rooms": ["living", "bedroom", "corridor"],
                "zh": "柜", "category": "storage", "cat2d": ("#ece0c8", "#b9a274")},
    "tall_cabinet": {"en": "a tall cabinet", "shape": "rect", "w": 120, "h": 38, "z": MAX_TALL_FURNITURE_Z,
                     "color": "#846752", "rooms": ["living", "bedroom", "corridor"],
                     "zh": "高柜", "category": "storage", "tall": True, "cat2d": ("#ece0c8", "#b9a274")},
    "bench": {"en": "a bench", "shape": "rect", "w": 165, "h": 50, "z": 430, "color": "#b07a4e",
              "rooms": ["living", "corridor"],
              "zh": "凳", "category": "living", "cat2d": ("#ece0c8", "#b9a274")},
    "plant": {"en": "potted plants", "shape": "round", "r": 20,
              "rooms": ["living", "bedroom", "outdoor", "corridor"],
              "zh": "绿植", "category": "decor", "cat2d": ("#cfe0cf", "#6b8a6b")},
    # —— 厨房 (wet 系: 厨房 + 卫浴同 type=wet, AI 按房名区分) ——
    "kitchen": {"en": "kitchen cabinets with stone countertop, hob and sink", "shape": "rect",
                "w": 320, "h": 60, "rooms": ["wet", "living"],
                "zh": "橱柜", "category": "kitchen", "cat2d": ("#ece0c8", "#b9a274"), "label2d": "橱柜"},
    "fridge": {"en": "a fridge", "shape": "rect", "w": 60, "h": 60, "z": MAX_TALL_FURNITURE_Z, "color": "#6a6d74",
               "rooms": ["wet", "living"],
               "zh": "冰箱", "category": "kitchen", "tall": True, "cat2d": ("#cdb18f", "#8a6a44"), "label2d": "冰箱"},
    "island": {"en": "a central island", "shape": "rect", "w": 120, "h": 130,
               "rooms": ["wet", "living"],
               "zh": "中岛", "category": "kitchen", "cat2d": ("#e7d9bb", "#b9ad8a"), "label2d": "中岛"},
    "washer_dryer": {"en": "a stacked washer-dryer", "shape": "rect", "w": 68, "h": 80, "z": MAX_TALL_FURNITURE_Z,
                     "rooms": ["wet", "outdoor"],
                     "zh": "洗烘", "category": "kitchen", "tall": True, "cat2d": ("#ece0c8", "#b9a274"), "label2d": "洗烘"},
    # —— 卫浴 ——
    "vanity": {"en": "a vanity with basin", "shape": "rect", "w": 120, "h": 55, "rooms": ["wet"],
               "zh": "台盆", "category": "kitchen", "cat2d": ("#dde7ec", "#8aa6b4"), "label2d": "台盆"},
    "toilet": {"en": "a toilet", "shape": "rect", "w": 55, "h": 80, "rooms": ["wet"],
               "zh": "马桶", "category": "kitchen", "cat2d": ("#dde7ec", "#8aa6b4"), "label2d": "马桶"},
    "tub": {"en": "a freestanding bathtub", "shape": "rect", "w": 72, "h": 160, "rooms": ["wet"],
            "zh": "浴缸", "category": "kitchen", "cat2d": ("#dde7ec", "#8aa6b4"), "label2d": "浴缸"},
    "shower": {"en": "a glass shower", "shape": "rect", "w": 95, "h": 120, "rooms": ["wet"],
               "zh": "淋浴", "category": "kitchen", "tall": True, "cat2d": ("#dde7ec", "#8aa6b4"), "label2d": "淋浴"},
    # —— P2 首批扩充 (声明式 spec 或复用基元; footprint px=10mm) ——
    "tv": {"en": "a wall-mounted flat-screen TV", "shape": "rect", "w": 140, "h": 10,
           "color": "#26262b", "rooms": ["living", "bedroom"],
           "zh": "电视", "category": "living", "directional": True,
           "cat2d": ("#3a3f45", "#22262b"), "label2d": "电视"},
    "floor_lamp": {"en": "a floor lamp", "shape": "rect", "w": 32, "h": 32,
                   "color": "#3a3a3a", "rooms": ["living", "bedroom"],
                   "zh": "落地灯", "category": "living", "cat2d": ("#d7d2c4", "#9a9482")},
    "armchair": {"en": "an armchair", "shape": "rect", "w": 75, "h": 78,
                 "color": "#a9744f", "rooms": ["living", "bedroom"],
                 "zh": "扶手椅", "category": "living", "directional": True,
                 "cat2d": ("#d8c0a4", "#a9895c"), "label2d": "扶手椅"},
    "ottoman": {"en": "an ottoman", "shape": "rect", "w": 60, "h": 45, "z": 420,
                "color": "#b07a4e", "rooms": ["living", "bedroom"],
                "zh": "脚凳", "category": "living", "cat2d": ("#dcc8a6", "#b9a274")},
    "sideboard": {"en": "a sideboard", "shape": "rect", "w": 160, "h": 45, "z": 750,
                  "color": "#8a633e", "rooms": ["living", "corridor"],
                  "zh": "餐边柜", "category": "storage", "directional": True,
                  "cat2d": ("#cdb18f", "#a9895c"), "label2d": "餐边柜"},
    "wine_cabinet": {"en": "a wine cabinet", "shape": "rect", "w": 60, "h": 40, "z": MAX_TALL_FURNITURE_Z,
                     "color": "#5a4332", "rooms": ["living"],
                     "zh": "酒柜", "category": "storage", "tall": True, "directional": True,
                     "cat2d": ("#8a6a52", "#5a4332"), "label2d": "酒柜"},
    "side_table": {"en": "a side table", "shape": "rect", "w": 45, "h": 45, "z": 500,
                   "color": "#d8c9ad", "rooms": ["living", "bedroom"],
                   "zh": "边几", "category": "living", "cat2d": ("#e7d9bb", "#b9ad8a")},
    "dresser": {"en": "a dresser", "shape": "rect", "w": 110, "h": 50, "z": 800,
                "color": "#8a633e", "rooms": ["bedroom"],
                "zh": "斗柜", "category": "storage", "directional": True,
                "cat2d": ("#cdb18f", "#a9895c"), "label2d": "斗柜"},
    "chest": {"en": "a storage chest", "shape": "rect", "w": 100, "h": 45, "z": 500,
              "color": "#846752", "rooms": ["bedroom"],
              "zh": "储物箱", "category": "storage", "cat2d": ("#cdb18f", "#a9895c"), "label2d": "储物箱"},
    "kids_bed": {"en": "a kids single bed", "shape": "rect", "w": 100, "h": 180,
                 "color": "#cdb98f", "rooms": ["bedroom"],
                 "zh": "儿童床", "category": "bedroom", "directional": True,
                 "cat2d": ("#e3c9a6", "#b78f5e"), "label2d": "儿童床"},
    "mirror": {"en": "a full-length mirror", "shape": "rect", "w": 60, "h": 8,
               "color": "#6a6d74", "rooms": ["bedroom", "living", "wet"],
               "zh": "穿衣镜", "category": "decor", "directional": True,
               "cat2d": ("#dbe6ec", "#8aa6b4"), "label2d": "镜"},
    "shoe_cabinet": {"en": "a shoe cabinet", "shape": "rect", "w": 90, "h": 35, "z": 1000,
                     "color": "#846752", "rooms": ["corridor", "living"],
                     "zh": "鞋柜", "category": "storage", "directional": True,
                     "cat2d": ("#cdb18f", "#a9895c"), "label2d": "鞋柜"},
    # —— P6 第二批 7 类 (补至 45 类) ——
    "bunk_bed": {"en": "a bunk bed", "shape": "rect", "w": 100, "h": 200,
                 "color": "#cdb98f", "rooms": ["bedroom"],
                 "zh": "上下铺", "category": "bedroom", "directional": True,
                 "cat2d": ("#e3c9a6", "#b78f5e"), "label2d": "上下铺"},
    "crib": {"en": "a crib", "shape": "rect", "w": 70, "h": 130, "z": 700,
             "color": "#cdb98f", "rooms": ["bedroom"],
             "zh": "婴儿床", "category": "bedroom", "cat2d": ("#e3c9a6", "#b78f5e"), "label2d": "婴儿床"},
    "desk_chair": {"en": "an office chair", "shape": "rect", "w": 55, "h": 55,
                   "color": "#3d5440", "rooms": ["bedroom", "living"],
                   "zh": "办公椅", "category": "storage", "cat2d": ("#cfe0d4", "#7fa088")},
    "bar_stool": {"en": "a bar stool", "shape": "rect", "w": 40, "h": 40, "z": 700,
                  "color": "#8a8a8a", "rooms": ["wet", "living"],
                  "zh": "吧凳", "category": "living", "cat2d": ("#dcc8a6", "#b9a274")},
    "console_table": {"en": "a console table", "shape": "rect", "w": 110, "h": 35, "z": 800,
                      "color": "#8a633e", "rooms": ["living", "corridor"],
                      "zh": "玄关台", "category": "storage", "directional": True,
                      "cat2d": ("#cdb18f", "#a9895c"), "label2d": "玄关台"},
    "coat_rack": {"en": "a coat rack", "shape": "rect", "w": 35, "h": 35, "z": MAX_TALL_FURNITURE_Z,
                  "color": "#6a5a48", "rooms": ["corridor", "bedroom"],
                  "zh": "衣帽架", "category": "storage", "tall": True, "cat2d": ("#cdb18f", "#a9895c")},
    "bidet": {"en": "a bidet", "shape": "rect", "w": 40, "h": 60, "rooms": ["wet"],
              "zh": "妇洗器", "category": "kitchen", "cat2d": ("#dde7ec", "#8aa6b4"), "label2d": "妇洗"},
    # —— rug 升格入目录 (P2): 可摆软装 + 真实默认尺寸; AI 不自动摆 (rooms 空, 平面避让语义特殊,
    #    由用户在编辑器手放)。渲染仍走 axon 内联平贴板, prompt_gen 跳过。 ——
    "rug": {"en": "a rug", "shape": "rect", "w": 200, "h": 140,
            "color": "#b8ad9a", "rooms": [], "inline": True,
            "zh": "地毯", "category": "decor"},
    # —— round_chair 补注册 (随访): 圆形件, draw_round 已支持 (深绿座); 前端 isCircleType 据 shape 判定 ——
    "round_chair": {"en": "a round accent chair", "shape": "round", "r": 30,
                    "color": "#3d5440", "rooms": ["living", "bedroom"],
                    "zh": "圆椅", "category": "living"},
}

_APPEARANCE_KEYS = ("z", "color")

# 换件分组 (软装重构 Phase C): 可互换件的语义分组 —— 方案换件在同组内进行, furnish 逐槽位
# 在同组内按风格选件, 保持锁定布局。单一归属 (clean swap UX)。纯元数据, 不进任何渲染路径
# (axon 2D/3D 只读 cat2d/label2d/shape/MODELS), golden 字节不受影响。
SWAP_GROUPS: dict[str, list[str]] = {
    "beds": ["bed", "kids_bed", "bunk_bed", "crib"],
    "sofas": ["sofa", "chaise"],
    "lounge_chairs": ["armchair", "swivel_chair", "round_chair", "ottoman"],
    "seats": ["chair", "desk_chair", "bar_stool", "bench"],
    "low_tables": ["coffee_table", "side_table", "round_table"],
    "consoles": ["console_table", "sideboard"],
    "dining": ["dining_table", "island"],
    "desks": ["desk"],
    "nightstands": ["nightstand"],
    "low_storage": ["cabinet", "media", "dresser", "chest", "shoe_cabinet"],
    "tall_storage": ["wardrobe", "tall_cabinet", "bookshelf", "wine_cabinet", "coat_rack"],
    "wc": ["toilet", "bidet"],
    "bathing": ["tub", "shower"],
    "basin": ["vanity"],
    "appliances": ["fridge", "washer_dryer"],
    "lighting": ["floor_lamp"],
    "screens": ["tv"],
    "mirrors": ["mirror"],
    "plants": ["plant"],
    "rugs": ["rug"],
    "kitchen_counter": ["kitchen"],
}
_TYPE_SWAP_GROUP: dict[str, str] = {
    t: g for g, types in SWAP_GROUPS.items() for t in types
}
# 注入 swap_group 到每条目录 (声明式旁表, 免逐条编辑 46 个字面量; 覆盖缺失即 None)。
for _t, _spec in CATALOG.items():
    _spec.setdefault("swap_group", _TYPE_SWAP_GROUP.get(_t))

# 声明式俯视外形 (软装重构 Phase C-3 / 画家具外形 #3-2): 家具在 2D 平面/编辑器画布上除底框
# 外再叠的内部细节图元, 由 plan2d_shapes 解释器 (引擎) + furniture.ts 孪生解释器 (前端) 消费。
# part.k: edge(靠背/床头板/柜背, 贴 orient 边) | arms(沙发扶手) | inner(盆/内胆/床垫) | doors(门线)。
# 无 spec 的类型退回纯底框 (plan2d 逐字节与改造前一致)。会改 D 基线内已 spec 类型的 plan2d
# 字节 -> 需 golden 重冻 (人工目检)。
_PLAN2D_SPECS: dict[str, list[dict]] = {
    # 床: 床头板 + 床垫内胆
    "bed": [{"k": "edge", "depth": 0.12}, {"k": "inner", "inset": [0.08, 0.2, 0.08, 0.08], "rx": 4}],
    "kids_bed": [{"k": "edge", "depth": 0.14}, {"k": "inner", "inset": [0.1, 0.22, 0.1, 0.1], "rx": 4}],
    "bunk_bed": [{"k": "edge", "depth": 0.12}, {"k": "inner", "inset": [0.08, 0.2, 0.08, 0.08], "rx": 4}],
    "crib": [{"k": "inner", "inset": [0.12, 0.12, 0.12, 0.12], "rx": 4}],
    # 沙发/软座: 靠背 + 扶手
    "sofa": [{"k": "edge", "depth": 0.22}, {"k": "arms", "depth": 0.85, "width": 0.11}],
    "chaise": [{"k": "edge", "depth": 0.2}, {"k": "arms", "depth": 0.7, "width": 0.12}],
    "armchair": [{"k": "edge", "depth": 0.3}, {"k": "arms", "depth": 0.8, "width": 0.18}],
    "chair": [{"k": "inner", "inset": [0.18, 0.18, 0.18, 0.18], "rx": 3}],
    "swivel_chair": [{"k": "inner", "inset": [0.18, 0.18, 0.18, 0.18], "rx": 3}],
    # 收纳: 柜背 + 门线
    "wardrobe": [{"k": "edge", "depth": 0.12}, {"k": "doors", "n": 3}],
    "cabinet": [{"k": "edge", "depth": 0.14}, {"k": "doors", "n": 2}],
    "tall_cabinet": [{"k": "edge", "depth": 0.14}, {"k": "doors", "n": 2}],
    "bookshelf": [{"k": "edge", "depth": 0.12}, {"k": "doors", "n": 4}],
    "media": [{"k": "edge", "depth": 0.16}, {"k": "doors", "n": 3}],
    "sideboard": [{"k": "edge", "depth": 0.14}, {"k": "doors", "n": 3}],
    "dresser": [{"k": "edge", "depth": 0.14}, {"k": "doors", "n": 3}],
    "shoe_cabinet": [{"k": "edge", "depth": 0.14}, {"k": "doors", "n": 2}],
    "wine_cabinet": [{"k": "edge", "depth": 0.15}, {"k": "doors", "n": 2}],
    "console_table": [{"k": "edge", "depth": 0.16}, {"k": "doors", "n": 2}],
    "nightstand": [{"k": "doors", "n": 2}],
    "chest": [{"k": "doors", "n": 2}],
    "desk": [{"k": "edge", "depth": 0.1}],
    # 卫浴: 便器盆/浴缸内胆/台盆
    "toilet": [{"k": "edge", "depth": 0.22}, {"k": "inner", "inset": [0.2, 0.35, 0.2, 0.08], "rx": 12}],
    "tub": [{"k": "inner", "inset": [0.12, 0.1, 0.12, 0.1], "rx": 10}],
    "vanity": [{"k": "inner", "inset": [0.3, 0.28, 0.3, 0.3], "rx": 8}],
    "shower": [{"k": "inner", "inset": [0.1, 0.1, 0.1, 0.1], "rx": 2}],
    "bidet": [{"k": "inner", "inset": [0.22, 0.3, 0.22, 0.1], "rx": 10}],
}
for _t, _parts in _PLAN2D_SPECS.items():
    if _t in CATALOG:
        CATALOG[_t]["plan2d_spec"] = _parts

# 派生集合 (供 scene/layout 从本表推导, 避免各自维护词表)。
HEIGHT_CONSTRAINED_TYPES: frozenset[str] = frozenset(
    t for t, s in CATALOG.items() if s.get("tall")
)
DIRECTIONAL_TYPES: frozenset[str] = frozenset(
    t for t, s in CATALOG.items() if s.get("directional")
)
ROUND_TYPES: frozenset[str] = frozenset(
    t for t, s in CATALOG.items() if s.get("shape") == "round"
)


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


def cat2d(t: str) -> tuple[str, str] | None:
    """类型的 2D 平面 (fill, stroke); 未收录返回 None (调用方自带兜底色)。"""
    c = (CATALOG.get(t) or {}).get("cat2d")
    return tuple(c) if c else None


def label2d(t: str) -> str | None:
    """类型的 2D 平面中文标注; 未收录 (小件不标) 返回 None。"""
    return (CATALOG.get(t) or {}).get("label2d")


def is_tall(t: str) -> bool:
    return bool((CATALOG.get(t) or {}).get("tall"))


def is_directional(t: str) -> bool:
    return bool((CATALOG.get(t) or {}).get("directional"))


def is_round(t: str) -> bool:
    return (CATALOG.get(t) or {}).get("shape") == "round"


def swap_group(t: str) -> str | None:
    """类型的换件分组名; 未收录返回 None。"""
    return (CATALOG.get(t) or {}).get("swap_group")


def types_in_swap_group(group: str | None) -> list[str]:
    """同组可互换类型 (声明序); group 为空返回空表。"""
    return list(SWAP_GROUPS.get(group, [])) if group else []


def plan2d_spec(t: str) -> list[dict] | None:
    """类型的声明式俯视外形 part 列表; 未定义返回 None (调用方退回纯底框)。"""
    return (CATALOG.get(t) or {}).get("plan2d_spec")


def to_public() -> list[dict]:
    """/api/catalog 出参: 前端家具库单一真源 (类型清单 + 真实默认尺寸 + 分组 + 标签)。

    只暴露前端渲染/摆放所需字段; 顺序即 CATALOG 声明序 (前端库分组内保持稳定)。
    结构件 (partition/entry_door/rug) 不在目录, 前端另有本地补充。
    """
    out: list[dict] = []
    for t, s in CATALOG.items():
        entry: dict = {
            "t": t,
            "en": s["en"],
            "shape": s["shape"],
            "rooms": list(s["rooms"]),
            "zh": s.get("zh", t),
            "category": s.get("category", "other"),
        }
        if s["shape"] == "round":
            entry["r"] = s["r"]
        else:
            entry["w"] = s["w"]
            entry["h"] = s["h"]
        for k in ("z", "color"):
            if k in s:
                entry[k] = s[k]
        if "cat2d" in s:  # 2D 平面/编辑器画布填充色 (前端新类型缩略图/画布用)
            entry["color2d"] = s["cat2d"][0]
        if s.get("tall"):
            entry["tall"] = True
        if s.get("directional"):
            entry["directional"] = True
        if s.get("swap_group"):  # 换件分组 (Phase C): 前端按此约束换件下拉
            entry["swap_group"] = s["swap_group"]
        if s.get("plan2d_spec"):  # 声明式俯视外形 (Phase C-3): 前端孪生解释器画细节
            entry["plan2d_spec"] = s["plan2d_spec"]
        out.append(entry)
    return out
