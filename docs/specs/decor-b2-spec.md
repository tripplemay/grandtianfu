# decor-b2 规格 — 软装配饰 AI 生成 + 实拍链路完整接入

> 批次类型：混合批次（F001-F006 generator，F007 evaluator）。状态流转 `planning → building → verifying → …`。
> 车道：快车道（同会话）。role_assignments：null。
> 分支：**feat/decor-b2（stacked off feat/decor-b1）** —— decor-b1 PR #82 未合并，b2 依赖 b1 代码（DECOR_ATTACH / wall_art/curtain / 第7步隔离兜底基座）。b1 合并到 main 后 b2 PR 自然收敛到只剩 b2 diff。

## 1. 背景与目标

decor-b1 已交付软装配饰的**引擎 + 编辑器基座**：配饰进目录/渲染/轴测预览可见、用户可手动摆放、换件透传、第7步隔离兜底（配饰不进实拍避免生产缺陷）。但 b1 有两个刻意留下的边界：
1. **配饰全靠用户手动摆**——furnish AI 生成方案时不产出配饰，用户得逐件手放。
2. **配饰不进实拍效果图**（第7步只隔离兜底未接入）——实拍图里配饰不会出现。

decor-b2 补齐这两块：让 furnish AI 按风格**自动生成配饰**（确定性落位），并把配饰**完整接入第7步实拍**，使配饰进入最终交付的实拍效果图。

## 2. 功能范围

**In scope：**
- furnish AI 配饰生成：LLM 为每个风格候选产出配饰清单（附着件挂谁 + 独立件放哪房），沿用"LLM 出清单不出坐标"契约。
- 确定性落位：独立配饰件（挂画/窗帘/绿植）由 Python 规则落坐标（挂画居中宿主墙、窗帘吸附窗、绿植空角）。
- 第7步实拍完整接入：挂画/窗帘进彩盒标注（墙面高度带）+ prompt 锚定短语 + acceptance allowed 墙面带扩展。
- 方案页配饰呈现（AI 配饰摘要）+ brief 配饰偏好字段。
- 回归评测集扩展（配饰落位场景 + 第7步断言）。

**Out of scope：**
- 新配饰类型（沿用 b1 的 wall_art/curtain + 5 类附着 + plant/rug）。
- 配饰的独立 AI 风格皮肤（配饰样式仍走目录默认，风格由 style_prompt 文字带）。
- 编辑器配饰交互（b1 已交付，b2 仅"AI 自动填 decor" + 方案页只读呈现）。

## 3. 数据模型

### 3.1 LLM 配饰输出（furnish candidate 扩展）

现有 candidate：`{name, style_prompt, swaps:[{room_id,from,to}]}`。b2 增可选 `decor`：

```jsonc
{
  "name": "...", "style_prompt": "...", "swaps": [...],
  "decor": [
    {"room_id": "r_live",
     "attach": [{"host_t": "sofa", "add": ["cushions"]}, {"host_t": "coffee_table", "add": ["vase"]}],
     "standalone": ["wall_art", "plant"]}
  ]
}
```

- `attach`：把附着配饰加到该房某类宿主（无坐标，写进宿主 `item.decor`）。
- `standalone`：该房要放的独立件类型（挂画/窗帘/绿植），坐标由 Python 落位。
- LLM **不出坐标**（与现有 swaps 同哲学）。

### 3.2 确定性落位产出

独立件落位后为标准 furniture item：`{t, room_id, dx/dy 或 dcx/dcy, orient, w/h/r}`（catalog.expand 补外观）。附着件写进宿主的 `decor` 子列表（无独立坐标，b1 已有 schema）。

### 3.3 第7步挂画墙面带

`perspective._box_polys` 增 `z0` 参数（默认 0.0，既有调用字节不变）。挂画彩盒从 z0=墙面带下沿（如 1000）投到 hz=1400，而非地面 0→600。

## 4. 关键设计决策

| # | 决策 |
|---|---|
| D1 | AI 配饰沿用 furnish 契约：LLM 出 `decor` 清单（attach 挂谁 / standalone 放哪房），不出坐标；`validate_candidates` 复用 `catalog.attach_mount_z`（附着合法性）+ `catalog.types_for_room` ∩ decor 类型（独立件合法性）剥离非法项记 warning。 |
| D2 | 确定性落位在 Python（新增 `layout.place_decor_standalone`）：**挂画**从同房宿主(sofa/bed) footprint 取贴墙边 → `layout._nearest_wall` 定墙 → 沿墙居中于宿主 x/y 中点写 dx/dy+orient；**窗帘**复用 `layout._window_zones`（落地窗 span）→ 宽对齐 span 贴该墙；**绿植**复用 `scene._room_free_rects` 找空闲矩形落空角。避让复用 `_boxes_intersect`/`_door_zones`。 |
| D3 | **z0 逐件派生**（审查修正）：`_box_polys(cam, item, ...)` 是逐件调用，z0 不能是整调用固定值。加 `_item_z0_mm(item)` 助手（镜像 `_item_height_mm`，`perspective.py:58-62`）：wall_art→1000、curtain→150、其余→0；`_box_polys`（`perspective.py:210`）内 `z0=_item_z0_mm(item)`，底面 `pd(px,py,z0)`（`:225`）。**默认（其余件 z0=0）保既有字节逐字节不变**。`_DEFAULT_HEIGHT_MM` 增 wall_art:1400/curtain:1450，使盒 z 带=(1000,1400)/(150,1450) **与 SPECS 渲染画框 z 一致**。 |
| D4 | `annotate_boxes` 放行独立件到墙面带彩盒（审查修正）：**不复用 SOFT_DECOR_TYPES**，skip 改为**字面 `{partition, rug}`**（rug 仍不给盒——地面软装走 prompt 文字；wall_art/curtain 移出 skip 用 z0 墙面带画盒进 legend）。附着件仍藏宿主 decor 不进彩盒（折宿主短语）。 |
| D5 | `acceptance.evaluate_geometry_lock` 扩 allowed（审查修正）：**不复用/不改 NOSHADOW_TYPES**（见 D10 红线），用**独立显式条件**让 wall_art/curtain 进 allowed（墙面带 z0，盒 z 带同渲染画框）；**allowed 盒须加垂直上沿余量**（`_inflate_item` 只扩水平不扩高度——模型画框略高于 z1 会冒出 allowed 上沿触发 structure 误判；hz 传 1500 而渲染 1400，或 allowed 专用抬顶）；但**不进逐盒 furnished 检查**（悬空件像素判不稳）。rug 保持既有（进 allowed）。 |
| D6 | `_geometry_lock_prompt` 增配饰锚定短语：挂画 "framed art centered on the wall above the sofa"、窗帘 "floor-length curtains over the window"（宿主/窗锚定）；附着件走宿主折叠短语（`catalog.attach_en`，与轴测 prompt_gen 一致）。 |
| D7 | 第7步几何/渲染正确性**升档对抗验证**（F007）：挂画 allowed 区对位墙面带不误判 structure、彩盒墙面带投影正确、配饰进实拍可见。CLAUDE.md 要求（floorplan_core 几何 + AIGC 链路双风险点）。 |
| D8 | **byte-safe / 兼容**：`_box_polys` z0 默认 0 → 既有 footprint_mask/annotate 调用字节不变；无 decor 的 furnish 输出不变；无独立件的第7步链路不变。golden 字节快照零回归（不碰 data/projects/D）。 |
| D9 | 落位确定性：同 geometry + 同 LLM 选择 → 同坐标（可复现，供回归评测门）。落位规则纯函数，不依赖随机。 |
| **D10** | **NOSHADOW_TYPES 红线（审查发现）**：`catalog.NOSHADOW_TYPES`（={wall_art,curtain}）**同时承载** axon 阴影排除（b1 D14，挂画不投地面影）**和** scene D13 clearance 豁免（挂画贴墙不内缩）。F003/F004 **绝不得改动 `NOSHADOW_TYPES` 定义、绝不得复用它做 annotate/acceptance 的新跳过集**——否则会连带破坏阴影/贴墙行为。perspective/acceptance 的新逻辑一律用**独立显式条件**（字面类型判断或新集合）。 |

**编排：** stacked off feat/decor-b1。building **两线并行**：Python 线 F001-F004+F006（furnish/layout/第7步/评测，主上下文）∥ 前端线 F005（方案页，subagent worktree）。verifying：三域 fan-out（furnish-layout / 第7步实拍 / web）+ F007 升档对抗。第7步（F003/F004）依赖 F002 落位产出坐标——Python 线内串行 F002→F003→F004。

## 5. Feature 逐条 acceptance

### F001 — furnish AI 配饰生成 · generator
- `layout_summary`（`furnish.py:34`）富化：每 piece 增 `attach_options`（`catalog.attach_types_for_host(t)`）；每房增 `decor_slots`（该 room.type 可放独立件 = `catalog.types_for_room(rtype)` ∩ {wall_art,curtain,plant}）。
- `build_messages`（`furnish.py:62`）扩 schema：instructions 增 decor 输出格式（attach/standalone，明示不出坐标）。
- `validate_candidates`（`furnish.py:89`）增 decor 校验：attach 用 `attach_mount_z(dt,host_t) is not None`（类型合法）**+ 该房确有该 host_t 家具实例**（审查 #7：LLM 说 host_t:sofa 但该房无 sofa → 剥离记 warning，不静默丢）；standalone 用 room 白名单 **+ 同房每类独立件去重/cap（≤1，审查 #7 防两个挂画）**；非法剥离记 warning（与 swaps 校验同风格）。
- 单测：LLM mock 返回 decor → 合法项保留、非法项（错宿主/错房/未知类型/**宿主实例不存在**/**同房重复**）剥离；无 decor 的候选行为不变。

### F002 — 确定性落位 · generator
- 新增 `layout.place_decor_standalone(G, room_id, standalone_types, existing_furniture)`：产出 placement-only item（dx/dy 或 dcx/dcy + orient）。审查修正：
  - **挂画**：居中同房宿主(sofa/bed)贴墙 → `_nearest_wall` 定墙 → 沿墙居中宿主中点；**该房无 sofa/bed 宿主 → 跳过 wall_art**（审查 #5，不瞎猜墙）。
  - **窗帘**：读 `geometry.derive(G)["windows"]` **全 wtype**（审查 #4：`_window_zones` 只返 full 落地窗，normal/high 窗房间会漏）→ 宽对齐 span、贴该墙、写 orient。
  - **绿植**：`scene._room_free_rects` **额外把既有家具作 obstacle 减去**（审查 #6：原只减墙）+ **选最靠房角的空 rect**（原返中央大块 → 绿植落中央不合理）。
- `furnish` 新增 `apply_decor(furniture, cand_decor, G)`：attach 写宿主 `item.decor`（`sanitize_decor` 校验）；standalone 调 `place_decor_standalone` 落坐标；在 `generate_candidates`（`furnish.py:216`）`apply_swaps` 后、`expand` 前接入。
- 单测：挂画 orient == 宿主贴墙方向 + 无宿主房跳过；窗帘覆盖窗（含 normal/high wtype）；绿植落靠角空 rect 不撞墙/门/既有家具；确定性（同输入同坐标）；落位件经 scene build_scene 不被推离墙（复用 b1 D13 豁免）。

### F003 — 第7步 `_box_polys` z0 + annotate 放行独立件 · generator
- 新增 `_item_z0_mm(item)` 助手（镜像 `_item_height_mm`，`perspective.py:58-62`）：wall_art→1000、curtain→150、其余→0。`_box_polys`（`perspective.py:210`）加 `z0` 参数，内部 `z0=_item_z0_mm(item)` **逐件派生**（审查 #1：不是整调用固定值），底面 `pd(px,py,z0)`。
- `_DEFAULT_HEIGHT_MM`（`perspective.py:58`）增 wall_art:1400/curtain:1450，使盒 z 带对齐 SPECS 渲染画框 z(1000,1400)/(150,1450)。
- `annotate_boxes`（`perspective.py:322-324`）：skip 改为**字面 `{partition, rug}`**（不复用 SOFT_DECOR_TYPES，D4）；wall_art/curtain 用墙面带 z0 画盒 + 进 legend。
- 单测：含挂画布局 annotate → legend 含 wall_art、彩盒在墙面高度带（非墙脚，断言盒 y 像素在上部）；**既有普通件（sofa 等 z0=0）annotate/footprint_mask 逐字节不变（byte-safe 硬证）**；rug/附着仍不进彩盒。

### F004 — 第7步 prompt 锚定短语 + acceptance allowed 扩展 · generator
- `_geometry_lock_prompt`（`main.py:2259`）：wall_art/curtain 生成锚定短语（挂画"framed art centered on the wall above the sofa"、窗帘"floor-length curtains over the window"，宿主/窗锚定）；附着件折宿主短语（`catalog.attach_en`）。
- `acceptance.evaluate_geometry_lock`（`acceptance.py:171`）：**用独立显式条件**（不复用/不改 NOSHADOW_TYPES，D10）让 wall_art/curtain 进 allowed（墙面带 z0 盒同渲染画框）；**allowed 盒加垂直上沿余量**（审查 #3：`_inflate_item` 只扩水平，模型画框略高于 z1 会冒出 allowed 上沿触发 structure 误判——allowed 专用 hz 传 1500 或抬顶）；不进逐盒 furnished；rug 行为不变。
- 单测：含挂画的 geometry_lock prompt 含锚定短语；含挂画的 evaluate 不因墙面新增（挂画）误判 structure FAIL（含画框略高于渲染 z1 的边界用例）；无独立件的链路字节/行为不变。

### F005 — 方案页配饰呈现 + brief 配饰偏好 · generator
- `scheme/page.tsx` 卡片增「配饰 N 项」摘要（读 furniture decor 计数 + 独立件计数）。
- `SchemeBriefEditor.tsx` 增「配饰偏好」LIST_FIELD（可选：多/少配饰、偏好类型），编译进 prompt（brief 贯通已有机制）。
- 逐件编辑复用 b1 已有 FurnitureSidePanel 分节（无需新 UI）。
- `yarn lint`+`tsc`+`build` 绿。

### F006 — 回归评测集扩展 · generator
- `eval_scenarios.py`（`:42`）增配饰场景：`decor_wall_art_above_sofa`（挂画居中沙发墙不误报碰撞/悬空）、`curtain_on_window`（窗帘对齐 span 不触发背窗 lint）、`plant_in_free_corner`；`forbid_lint` 断言不误报。
- `test_layout.py` 增落位断言（挂画 orient/窗帘 span/绿植空角）；`test_decor.py`/furnish 测试增 AI 配饰生成 + 落位断言；第7步断言（annotate 墙面带 / prompt 锚定 / allowed 不误判）。
- 两套 pytest 全绿。

### F007 — AI 配饰 + 第7步实拍对抗验收 · evaluator
- **头号验收项（审查 #3）**：拿真实 mask 目检——含挂画的 `evaluate_geometry_lock` 的 allowed 区是否真覆盖挂画墙面区域（含画框略高于渲染 z1 的边界情形），确认不误判 structure。这是本批唯一"隐蔽渲染错"的点。
- 生成含 AI 配饰的方案 → 轴测 + 第7步实拍链路对抗检查：挂画彩盒墙面带投影正确（非墙脚）、prompt 锚定短语、配饰进实拍可见（若 AI 配置则真实出图，否则 SVG/mask 几何目检降级记账 [L2]）。
- 确定性落位复现验证（同输入同坐标）；落位合理性目检（挂画居中宿主墙/窗帘对齐窗/绿植靠角）。
- **NOSHADOW 红线核验（D10）**：确认 F003/F004 未改动 `NOSHADOW_TYPES` 定义、axon 阴影排除 + scene clearance 豁免行为未变（golden 字节快照 + b1 decor 测试仍绿）。
- 报告落盘 `docs/test-reports/decor-b2-verifying-*.md`。

## 6. 测试与验收基线

- 本地两套 pytest（CI 不跑 pytest）：engine + api。
- golden 字节快照全绿（`_box_polys` z0 默认 0 的 byte-safe 硬证）。
- web：tsc/lint/build。
- 第7步：含配饰的 annotate PNG / acceptance mask 目检（挂画墙面带、allowed 不误判）。

## 7. 风险与缓解

- **第7步 correctness（F003/F004 高风险）**：挂画 allowed 区对位墙面高度带是核心——若 allowed 未覆盖挂画墙面区，模型画的挂画边缘会触发 structure FAIL。F007 升档对抗验证专门守此。
- **落位美学**：挂画居中/窗帘对齐是启发式，F007 目检 + 回归场景门兜底；不追求完美，追求"合理且不误判"。
- **byte-safe**：`_box_polys` z0 默认 0 是既有调用零回归的关键，F003 单测必须验证既有调用字节不变。
