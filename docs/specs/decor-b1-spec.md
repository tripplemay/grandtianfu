# decor-b1 规格 — 软装配饰功能 · 引擎 + 编辑器基座

> 批次类型：混合批次（F001–F008 generator，F009 evaluator）。状态流转 `planning → building → verifying → …`。
> 车道：快车道（同会话）。role_assignments：null（默认映射）。
> 上游计划：`~/.claude/plans/`（会话内）— 本 spec 为 spec-lock 权威版。

## 1. 背景与目标

效果图链路目前只覆盖 46 类固定家具目录，**软装配饰**（挂画、花瓶、点缀植物、抱枕、窗帘等）完全没有结构化处理——仅在实拍 prompt 的风格提示里被口头提及（`apps/api/main.py:2173-2176`），出不出、出在哪全由模型自由发挥。诊断文档 `docs/AIGC链路与提示词诊断-20260708.md:184,338,378` 已记载此短板。配饰对装修品质感至关重要。

用户决策（三选一确认）：
1. **路线三·全几何建模**——配饰进 floorplan_core 引擎渲染，轴测预览（第 4/5 步）中可见，而非仅靠 prompt 文字带出。
2. **AI 生成 + 用户可编辑**——最终目标（b2）由 furnish 按风格自动配饰，用户可增删改。
3. **基础包 + 织物件**——挂画 / 绿植 / 花瓶 / 台灯 / 摆件 + 窗帘 / 抱枕 / 床品搭毯。

**decor-b1（本批）目标**：把配饰做成引擎一等公民 + 编辑器可手动摆放/编辑的基座。交付后用户即可在编辑器摆挂画、给沙发床加抱枕，轴测 SVG 与第 5 步效果图可见，且换件不丢配饰、生成实拍图不因配饰出缺陷。**AI 自动配饰 + 第 7 步完整接入留 decor-b2。**

## 2. 功能范围

**In scope（b1）：**
- 独立配饰件 `wall_art`（挂画）、`curtain`（窗帘）进目录，走现有家具全链路（目录/2D/3D/prompt/编辑器）。
- 附着配饰机制：`cushions`/`bedding`/`table_lamp`/`vase`/`ornament` 挂在宿主家具上（无独立坐标），3D 在宿主顶面渲染，prompt 折进宿主短语。
- 第 5 步（轴测效果图）prompt 自动贯通配饰。
- 编辑器：独立配饰摆放 + 附着配饰增删编辑。
- 换件（swap）双端透传 decor 子列表。
- **第 7 步隔离兜底**：配饰不进彩盒标注、不进逐盒验收（防生产缺陷），但本批不做完整实拍接入。

**Out of scope（→ decor-b2）：**
- furnish AI 自动生成配饰 + 确定性落位规则。
- 第 7 步实拍完整接入（prompt 配饰文字层 + 锚定短语 + acceptance allowed 区扩展）。
- 方案中心页配饰呈现/编辑 UI。
- 回归评测集扩展 + 实拍真实出图评测。

## 3. 数据模型

### 3.1 独立配饰件（进 CATALOG）

与现有家具条目同 schema（`catalog.py:16-30`）。新增两类：

```python
"wall_art": {"en": "framed wall art", "shape": "rect", "w": 80, "h": 8,
             "rooms": ["living", "bedroom", "corridor"],
             "zh": "挂画", "category": "decor", "directional": True, "noshadow": True,
             "cat2d": (<浅框色>, <描边>), "label2d": "挂画"},
"curtain": {"en": "floor-length curtains", "shape": "rect", "w": 120, "h": 10,
            "rooms": ["living", "bedroom"],
            "zh": "窗帘", "category": "decor", "directional": True, "noshadow": True,
            "cat2d": (<布色>, <描边>)},
```

- `noshadow: True`（**新目录标志**，见 §4 D14）：该件不投地面阴影。
- 两类都 `directional`（贴墙），编辑器用户手放 + 吸附（`furniture.ts:700` 已有近墙吸附）。
- **SWAP_GROUPS 硬约束**（`test_catalog_api.py:61-64`）：每新类型必须**恰好归属一个** swap group。新增 `"wall_arts": ["wall_art"]`、`"curtains": ["curtain"]` 两组（或并入合适现有组），且 `sum(len(v)) == len(CATALOG)` 与 `grouped == set(CATALOG)` 必须成立。

### 3.2 附着配饰子列表（decor）

宿主 furniture item 增可选 `decor` 键：

```json
{"t": "sofa", "room_id": "r_live", "dx": 225, "dy": 518, "w": 210, "h": 90,
 "orient": "E", "decor": [{"t": "cushions"}, {"t": "vase"}]}
```

- `decor` = 附着元素列表，每元素至少含 `t`（附着类型）。
- 无 `decor` 键 = 无附着配饰（向后兼容；缺省行为逐字节不变）。
- 附着元素**无独立坐标**——渲染时按宿主 footprint + 注册表 mount_z 定位。

### 3.3 附着配饰注册表（DECOR_ATTACH，新建于 catalog.py）

```python
# 附着配饰: 挂在宿主家具顶面, 无独立坐标。mount_z = 该宿主"顶面高度"(mm),
# 显式声明(不可从 3D 模型启发式推导, 见 spec §4 D12)。hosts = 允许宿主白名单。
DECOR_ATTACH: dict[str, dict] = {
  "cushions":   {"zh": "抱枕",   "en": "decorative cushions",
                 "hosts": {"sofa": 470, "chaise": 400, "armchair": 470,
                           "bed": 480, "kids_bed": 360, "bunk_bed": 420}},
  "bedding":    {"zh": "床品搭毯", "en": "a folded throw blanket",
                 "hosts": {"bed": 480, "kids_bed": 360, "bunk_bed": 420}},
  "table_lamp": {"zh": "台灯",   "en": "a table lamp",
                 "hosts": {"nightstand": 470, "side_table": 480,
                           "console_table": 800, "sideboard": 750, "desk": 740}},
  "vase":       {"zh": "花瓶花艺", "en": "a vase with flowers",
                 "hosts": {"coffee_table": 420, "dining_table": 750, "console_table": 800,
                           "sideboard": 750, "media": 520, "side_table": 480}},
  "ornament":   {"zh": "摆件",   "en": "decorative ornaments",
                 "hosts": {"coffee_table": 420, "dining_table": 750, "console_table": 800,
                           "sideboard": 750, "media": 520, "side_table": 480}},
}
```

- mount_z 数值为**建议草案**：Generator 应对照实际 3D 模型（`axon.py` 各 m_* 的顶面 z）微调，但**每个宿主必须显式声明**，不得用 `max(box.z1)` 之类启发式（sofa max z=760 是靠背非座面，`axon.py:411` 座面才 470）。
- **圆形宿主**（round_table、round_chair 等走 `draw_round` 路径，`axon.py:1158-1159`）**不得**作宿主——不进任何 `hosts` 白名单。
- 校验（`furnish` / API / scene 三处按需）：`decor[].t` 不在 DECOR_ATTACH → WARN 剥离；宿主类型不在该配饰 `hosts` → WARN 剥离。不阻断渲染（与 scene 非阻断 WARN 一致，`axon.py:1164` 注释同款意图）。

## 4. 关键设计决策

| # | 决策 |
|---|---|
| D1 | 挂画/窗帘 3D 走声明式 `SPECS` + `m_from_spec`（浮空盒 + vplane），**不写手工 m_* 函数**。挂画：画框薄盒 z≈(1150,1550) 悬空 + vplane 画面贴 opp 侧墙；窗帘：贴 opp 侧墙半透 vplane 长幔 z≈(150,1420)。具体数值 Generator 定，约束=挂画悬空离地约 1.35m 中心、窗帘落地贴窗。 |
| D2 | 阴影排除从硬编码 tuple `("shower","entry_door","partition")`（`axon.py:1183`）→ 读目录 `noshadow` 标志。 |
| D3 | **不动 `data/projects/D` 活数据、不改既有类型的 plan2d/尺寸/配色** → golden 字节快照零重冻。新类型测试一律用 fixtures。 |
| D4 | 配饰一律**不进第 7 步彩盒**（小件污染标注，仿 rug 软装层）。 |
| D5 | 第 5 步 prompt：独立件经 `catalog.en` 自动进逐房清单（`prompt_gen.py:163-170`）；附着件折进宿主短语。**无配饰数据时输出逐字节不变**（保历史基线，与 rug/brief 同款兼容策略）。 |
| D6 | （b2）AI 配饰沿用 furnish 契约：LLM 出语义选择 + 语义锚，确定性落位转坐标。b1 不涉及。 |
| D7 | `CATALOG_REV` **不 bump**（纯新增类型，不影响既有方案外观刷新语义）。 |
| D8 | curtain：b1 用户在编辑器手放贴墙（复用近墙吸附）；b2 AI 按窗户 span 自动吸附。 |
| D9 | 附着件校验非法宿主 / 未知类型 → WARN 剥离不阻断。 |
| **D10** | **第 7 步隔离兜底必须在 b1**：`annotate_boxes` 只跳 `("partition","rug")`（`perspective.py:321`），且 `_box_polys` 固定从 z=0 投影（fallback 高度 600，`perspective.py:63-67`）——不兜底则用户摆挂画后生成实拍图会得到"墙脚地面彩盒 → 模型在地板画画 + 验收压分"的**生产可见缺陷**。做法：目录导出独立配饰跳过集合（把 rug 收编进同一机制），`annotate_boxes` + `evaluate_geometry_lock`（`acceptance.py:161-181`）建盒处均跳过配饰类型。 |
| **D11** | **双端换件透传 decor**：`furnish._swap_item_type`（`furnish.py:138-175`）与前端 `swapFurnitureType`（`furniture.ts:532-563`）的白名单都不含 `decor`，换件会静默丢弃宿主配饰。两端同批加 `decor` 透传 + 换件后**按新宿主 `hosts` 白名单过滤**（新宿主不兼容的附着项剥离，WARN）。 |
| **D12** | 附着注册表按宿主类型**显式声明 mount_z**（§3.3），不用启发式。 |
| **D13** | scene photo 模式 inner-clearance（`WALL_CLEARANCE=13px=130mm`，`scene.py:19,198-221,561-565`）对**贴墙配饰类型（noshadow/directional 薄件）加豁免**（不内缩），否则挂画/窗帘 vplane 浮空 130mm 离墙。既有类型（tv/mirror）行为不变——它们今天就被推离墙 13px，属既有妥协，**另立 backlog 观察项，不在本批改**。 |
| **D14** | noshadow 目录化的实现兜底：`entry_door`/`partition` **不在 CATALOG**（结构件，`catalog.py:8`），故阴影排除集必须是 **"目录 noshadow 标志 ∪ 结构件硬编码集 `{shower,entry_door,partition}`"**，否则结构件平白多出阴影（视觉回归）。 |

**编排：** building **两线并行**（worktree 隔离，文件集不重叠）——引擎/API 线 F001-F005+F008（Python）∥ 前端线 F006-F007（TS）。verifying **三域 fan-out**（engine/api/web 隔离 evaluator）+ F009 独立执行。F009 按 CLAUDE.md 对 floorplan_core 渲染正确性**升档对抗验证**（渲染错隐蔽）。

## 5. Feature 逐条 acceptance

### F001 — 目录新增 wall_art/curtain + noshadow 目录化 · generator
- CATALOG 增 `wall_art`、`curtain` 两条，字段齐全（en/shape/w/h/rooms/zh/category:decor/directional/noshadow/cat2d[/label2d]）。
- 两类各归属**恰好一个** SWAP_GROUPS 组；`test_catalog_api.py:61-64` 三条断言（每类有 swap_group / grouped==set(CATALOG) / 总数相等）全绿。
- 阴影排除改为"目录 `noshadow` 标志 ∪ 结构件硬编码集"（D14）；既有 `shower/entry_door/partition` 阴影行为逐字节不变。
- `to_public()`（`catalog.py:359`）出参含 noshadow（若前端需要）；`/api/catalog` 出参含新类型。
- 既有渲染/prompt 输出零回归（无 wall_art/curtain 数据的场景逐字节不变）。

### F002 — 3D/2D 渲染 + scene 贴墙豁免 · generator
- `SPECS` 增 wall_art（悬空框盒 + vplane 画面）、curtain（贴墙半透 vplane 长幔）；`MODELS` 注册 `lambda it: m_from_spec(it, SPECS[...])`。
- `test_catalog.py` 全类型映射约束绿（矩形非-inline 类型必在 MODELS）。
- 含 wall_art/curtain 的 **fixture** 渲染 3D SVG：挂画含悬空盒 + vplane、无地面阴影；窗帘含贴墙 vplane。
- 2D 平面：贴墙薄矩形（`_furn2d_frags`），无需内部细节 spec。
- scene build_scene 对贴墙配饰类型豁免 inner-clearance 内缩（D13）——含配饰的 scene 不产生 `axon-clearance-shift` note 把配饰推离墙。
- **golden 字节快照测试全绿**（`test_render_snapshot.py`）——证明零回归。

### F003 — 附着配饰机制 + furnish 换件透传 · generator
- catalog.py 新建 `DECOR_ATTACH` 注册表（§3.3），5 类含 per-host mount_z；提供查询 helper（`attach_hosts(t)` / `attach_mount_z(t, host_t)` / `is_attach_type(t)` 等）。
- axon 家具循环（`axon.py:1141-1184`）在 `fn(it)` 返回 boxes 后、`piece()` 前，把宿主 `decor` 子列表按 mount_z 渲染成顶面小盒/微柱/发光点，append 进 boxes（painter 深度键 + rot 旋转包裹自动生效）。table_lamp 仿 floor_lamp 缩小版（微柱 + glowdot）。
- 圆形宿主排除；非法宿主/未知附着类型 WARN 剥离。
- `furnish._swap_item_type` 白名单加 `decor` 透传（D11）：换件保留宿主 decor，并按**新宿主** hosts 过滤不兼容项。
- 含附着 fixture 的 3D SVG 有对应图元；无 decor 数据的输出逐字节不变；`test_furnish.py` 换件透传用例绿。

### F004 — prompt_gen 配饰贯通 · generator
- 独立件（wall_art/curtain）经 `catalog.en` 自动进逐房清单（已有机制，验证生效即可）。
- 附着件折进宿主短语：宿主家具短语后追加 "with <decor.en>"（如 "a sofa with decorative cushions and a vase with flowers"）。
- 含配饰 fixture 的 prompt 含对应英文短语；**无配饰的 prompt 输出逐字节不变**（保 build.py + 历史基线，比对既有 golden prompt 快照/测试）。

### F005 — API 出参 + decor 结构校验 + 单测 · generator
- `/api/catalog` 出参含 wall_art/curtain（`test_catalog_api.py` 绿）。
- furniture 保存校验 `_furniture_items_error`（`main.py`）扩展：`decor` 若存在必须是列表，元素含合法 `t`（在 DECOR_ATTACH 内），宿主兼容做**软校验**（不兼容 → 响应 warnings，不硬拒）。
- 带 `decor` 子列表的 furniture 保存 → 读取往返无损（decor 键不被存储层丢弃）。
- api pytest 全绿。

### F006 — 前端独立配饰摆放 + 换件透传 · generator
- 家具库「装饰」组（`furniture.ts:220-223` FURN_CATEGORY_DEFS）出现 wall_art/curtain（category:decor 自动并入）。
- 拖放 / 点选 / 贴墙吸附 / 换件可用（复用 buildFurnitureAt/clampToRoom/近墙吸附）。
- `swapFurnitureType`（`furniture.ts:532`）白名单加 `decor` 透传 + 按新宿主 hosts 过滤（D11 前端侧）。
- 画布孪生渲染新薄件（2D 贴墙矩形）。
- `yarn lint` + `tsc` + `yarn build` 全绿。

### F007 — 前端附着配饰编辑（SidePanel「配饰」分节）· generator
- `FurnitureSidePanel.tsx` 对白名单宿主（DECOR_ATTACH.hosts 含该宿主类型）显示「配饰」分节：可勾选/增删该宿主允许的附着类型。
- 数组字段（decor）走**专用 handler**（非 `onSetFurnField` 标量通道，`useFurnitureEditor.ts:577`）。
- 增删往返保存（写入宿主 item.decor）；非宿主类型不显示分节；posLocked 状态下配饰编辑仍可用（换件不挪位场景）。
- `yarn lint` + `tsc` + `yarn build` 全绿。

### F008 — 第 7 步隔离兜底（D10）· generator
- catalog 导出「独立配饰跳过集合」（含 wall_art/curtain，把 rug 收编进同一语义集合，保持 rug 现有行为）。
- `perspective.annotate_boxes`（`:319-322`）跳过集扩展为该集合；`acceptance.evaluate_geometry_lock`（`:161-181`）建盒 + 逐盒验收跳过配饰。
- 单测：含 wall_art 的布局 → `annotate_boxes` legend 不含配饰、`drawn` 不计配饰；含 wall_art 的 `evaluate_geometry_lock` 不因配饰盒 FAIL。
- 既有 rug 跳过行为逐字节等价（收编不改 rug 语义）。

### F009 — 轴测渲染正确性对抗验收 · evaluator
- 生成含全部配饰类型（独立 + 附着）的样例布局 fixture，渲染轴测 3D SVG，人工目检 + 对抗检查：
  - 挂画悬浮在墙上正确高度、无地面阴影；
  - 窗帘贴墙覆盖窗户区、不遮挡结构；
  - 附着件（抱枕/花瓶/台灯）在宿主顶面正确高度、比例合理、不悬空/不穿模；
  - 换件后 decor 透传实测（沙发→贵妃榻换件保留兼容配饰、剥离不兼容）。
- **至少 1 次第 5 步真实出图**（axon-photoreal，验证配饰进照片级效果图可见）。
- 报告落盘 `docs/test-reports/decor-b1-verifying-*.md`。

## 6. 测试与验收基线

- **本地两套 pytest**（CI 不跑 pytest，唯一 Python 门）：
  `PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q`
  `PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q`
- **golden 字节快照必须全绿**（零回归硬证据）；render 测试需 rsvg + Noto CJK，缺失时 skip 视为"未跑"非"通过"。
- web：`yarn lint` + `tsc --noEmit` + `yarn build` 绿 + 编辑器手动冒烟（摆挂画 → 轴测预览可见）。
- ruff：编辑 Python 手工匹配仓库风格，只用 `ruff check` 查真错（不跑 `ruff format .`，会全文件重排，见 project-status 记忆）。

## 7. 已知裂缝与 b2 边界

- **b1 交付后**：用户可摆配饰、轴测可见、实拍图不因配饰崩（D10 兜底）——但实拍图里配饰**不会主动出现**（第 7 步只跳过，未接入 prompt/allowed）。这是预期的 b1/b2 边界，不算缺陷。
- **b2 承接**：furnish AI 配饰生成 + 落位规则；第 7 步完整接入（`_geometry_lock_prompt` 配饰文字层 + 锚定短语；acceptance allowed 区扩展——需给 `_box_polys` 加 z0 参数使挂画 allowed 区对位墙面高度带；`room_hint` 对配饰噪声处理）；方案页配饰 UI；回归评测集 + 实拍实测。→ 已写入 `backlog.json`（BL-decor-b2）。
- **D13 遗留**：tv/mirror 既有 13px 离墙妥协 → 另立 backlog 观察项。
