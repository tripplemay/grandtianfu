# decor-b2 首轮验收报告 — Python 域（furnish / layout / 第7步 / 评测集）

- **批次**：decor-b2（软装配饰 AI 生成 + 实拍链路完整接入）
- **阶段**：verifying（首轮，fix_rounds=0）
- **域**：Python 线 — F001 / F002 / F003 / F004 / F006（不含 F005 web 域、F007 渲染对抗，另有独立验收）
- **评估者**：隔离 evaluator subagent（fresh context，自磁盘取证，不接受实现叙述）
- **评估 SHA**：HEAD=14a4f72（feat/decor-b2，stacked off feat/decor-b1 @ 4bc2bf7）
- **日期**：2026-07-13

## 结论速览

| Feature | 标题 | 判定 |
|---|---|---|
| F001 | furnish AI 配饰生成（summary 富化 + LLM schema + 校验剥离） | **PASS** |
| F002 | 确定性落位（挂画/窗帘/绿植） | **PASS** |
| F003 | 第7步 `_box_polys` z0 + annotate 放行独立件 | **PASS** |
| F004 | 第7步 prompt 锚定短语 + acceptance allowed 墙面带扩展 | **PASS** |
| F006 | 回归评测集扩展（配饰场景 + 第7步断言） | **PASS** |

**本域计数：PASS 5 · PARTIAL 0 · FAIL 0。**

## L1 测试基线（本地实跑，非叙述）

| 项 | 命令 | 结果 |
|---|---|---|
| 引擎套件 | `PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q` | **152 passed，0 skip** |
| API 套件 | `PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q` | **320 passed，0 skip** |
| golden 字节快照 | `test_render_snapshot.py`（含在引擎套件） | 绿，**0 skip**（`rsvg-convert` = /opt/homebrew/bin/rsvg-convert 可用，非静默跳过） |
| ruff | `python3 -m ruff check`（6 个改动文件） | All checks passed |

> 0 skip 已核（`-rs` 无输出）——golden 字节 / 渲染类测试真实运行，未被 skipif 静默跳过。

## 逐条验收（基于实物 + 实测）

### F001 — furnish AI 配饰生成 · PASS
- `layout_summary` 富化：每 piece 加 `attach_options`（`catalog.attach_types_for_host`）、每房加 `decor_slots`（`_standalone_slots` = `_STANDALONE_DECOR ∩ 目录 rooms 白名单`）。证据 `furnish.py:79-86`；`test_furnish.py:61` 断言 sofa→cushions、coffee_table→{vase,ornament}、plant 无 attach、living 房 decor_slots={wall_art,curtain,plant}。
- `build_messages` 扩 schema：instructions 增 decor 输出格式并明示"不要出坐标"。证据 `furnish.py:96-113`；`test_furnish.py:74` 断言 system 含"配饰"、user 含 "decor"/"standalone"。
- `validate_candidates` decor 校验（对抗核查重点）：
  - **attach 宿主实例存在性**：`present` 字典由 `base_furniture` 逐件建（room_id→该房实际家具类型集），`host_t not in room_present` → 剥离记 warning。证据 `furnish.py:152-153,199-201`。非仅类型合法——`test_furnish.py:95` 用 `host_t:bed` 但 r_live 无 bed → 剥离。
  - **attach 类型合法性**：`catalog.attach_mount_z(dt, host_t) is None` → 剥离（`furnish.py:158`）。`bedding` 挂 `sofa` → add 空 → 条目丢。
  - **standalone 同房去重**：`seen_s` 集合，同类 ≤1（`furnish.py:173`）。`["wall_art","wall_art","toilet"]` → `["wall_art"]`。
  - **standalone 房白名单**：`_standalone_slots(room_types[rid])`，`toilet` 非独立配饰 → 剥离。
  - **无 decor 候选行为不变**：`room_types` 缺省时 decor 全剥；无 decor 键归一为 `decor:[]`。`test_furnish.py:107` 断言。
- 结论：acceptance 全项实装且有断言。**PASS**。

### F002 — 确定性落位 · PASS
- `place_decor_standalone(G, room_id, standalone_types, existing_furniture)` 产出 placement-only item。证据 `layout.py:487-530`。
- **挂画**：`_place_wall_art` 取同房宿主（`_WALL_ART_HOSTS={sofa,chaise,bed,kids_bed,bunk_bed}`）贴墙 orient 居中宿主中点；**无宿主返回 None**（`layout.py:420-445`）。`test_layout.py:345` orient==宿主贴墙 + flush；`:357` coffee_table 非宿主 → `[]`。
- **窗帘**：读 **`_room_window_spans`（全 wtype，无 `wtype!="full"` 过滤）**，非 `_window_zones`（仅 full）。证据 `layout.py:379-398,512`。**独立实测**：normal / high wtype 窗 `_room_window_spans` 返回 span、`_place_curtain` 成功落位；同窗 `_window_zones` 返 `[]`（证明旧路径会漏，审查 #4 已修）。
- **绿植**：`_place_plant` 试 4 角、避让既有家具（`obstacles=既有件 footprint`）+ 门口净空，选最靠角空位。证据 `layout.py:469-484,513`。**独立实测**：TL 角被占 → 落 TR（dcx=576）；无障碍 → 首角（24,24，非中央）；四角全占 → None（不瞎放）。
- **确定性**：纯函数无随机；`test_layout.py:379` 同输入两次 `a==b`。
- **落位件不被 scene 推离墙**：`test_layout.py:388` 复用 b1 D13 豁免，S 墙 flush 保持。
- `apply_decor` 接入：attach 写宿主 `decor`（去重）、standalone 调 `place_decor_standalone`；`generate_candidates` 中 `apply_swaps` 后、`expand` 前接入（`furnish.py:300-326,354-355`）。`test_furnish.py:115` 断言 + 不可变性（原 furn 未改）。
- 结论：**PASS**。

### F003 — 第7步 `_box_polys` z0 + annotate · PASS
- `_item_z0_mm(item)` 逐件派生（`_ITEM_Z0_MM={wall_art:1000,curtain:150}`，其余 0.0）。证据 `perspective.py:76-78`；`test_perspective.py:178` 断言 wall_art=1000/curtain=150/sofa=0/coffee_table=0。
- `_box_polys` 内 `z0=_item_z0_mm(item)`，底面 `pd(px,py,z0)`（`perspective.py:227,235`）。`_DEFAULT_HEIGHT_MM` 增 wall_art:1400/curtain:1450（`perspective.py:57-62`）。
- **byte-safe 硬证（对抗核查重点）**：git diff 显示唯一改动为 `pd(px,py,0.0)` → `pd(px,py,z0)`，既有类型 `_item_z0_mm` 返 `float(0.0)` → 逐字节等价。**独立实测**：对 sofa/tv/coffee_table 的 `footprint_mask` 计算 sha256，新逻辑 vs 强制 z0=0（模拟 pre-F003）**byte-identical=True**。叠加 golden 字节快照 0-skip 绿。
- `annotate_boxes` skip 改为**字面 `{partition, rug}`**（不复用 SOFT_DECOR_TYPES），wall_art/curtain 进 legend。证据 `perspective.py:334-337`；`test_perspective.py:163` drawn==3、legend={wall_art,curtain,sofa}、rug 跳。
- 彩盒墙面带非墙脚：`test_perspective.py:189` 挂画盒最低点 y < 地面盒最低点（悬空在墙面带）。
- 结论：**PASS**。

### F004 — prompt 锚定 + acceptance allowed 扩展 · PASS（最高风险块）
- **`_ALLOWED_ONLY = frozenset({rug,wall_art,curtain})` 独立显式集合**，非复用 NOSHADOW_TYPES。证据 `acceptance.py:64,188`；git diff 显示 `from floorplan_core import catalog` 已删除、`t in catalog.NOSHADOW_TYPES` 分支已移除——acceptance.py 不再引用 catalog（D10 红线满足）。
- **allowed 盒垂直上沿余量**：`_WALL_BAND_ALLOWED_Z={wall_art:1500,curtain:1550}`（高于渲染顶 1400/1450）；墙面带件 `infl_item={**infl_item,"z":...}` 抬 allowed 顶（`acceptance.py:67,178-179`）。防模型画框略高于 z1 冒出 allowed 触发 structure 误判（审查 #3）。
- **不进逐盒 furnished**：`if t in _ALLOWED_ONLY: continue`（`acceptance.py:188-189`）。`test_acceptance.py:88` 断言 wall_art 不在 furnished_types。
- **rug 行为不变**：git diff 显示 rug 仍 `allowed |= _extend_down(...)` 后 `continue`（原 `if t=="rug": continue` → 现 `if t in _ALLOWED_ONLY`，rug ∈ 集合），逐条等价。
- **含挂画 evaluate 不误判 structure**：`test_acceptance.py:88` 在 allowed 抬顶 z=1500 区画内容（含渲染顶 1400→1500 的边界带）→ `v["ok"]` True，无 structure FAIL。
- `_geometry_lock_prompt`：挂画 "framed wall art ... mounted on the wall, centered above the furniture beneath it"、窗帘 "floor-length curtains hanging over the window"；附着件 `catalog.attach_en` 聚合软装短语。证据 `main.py:2299-2326`；`test_render_real_geometry.py:273` 断言锚定短语 + 附着聚合 + 无配饰不加短语。
  - 备注：spec §5 举例短语 "framed art centered on the wall above the sofa" 被实现泛化为 "above the furniture beneath it"（宿主可为 sofa/bed 等），语义锚定一致，非缺陷。
- 结论：**PASS**。

### F006 — 回归评测集扩展 · PASS
- `eval_scenarios.py` 增 3 配饰场景。**独立实测** `run_scenarios(G, geo)` 于真实 D 户型：
  - `decor_wall_art_above_sofa`：ok=True，lint=[]，false_positive=[]
  - `decor_curtain_on_window`：ok=True，lint=[]，false_positive=[]
  - `decor_plant_in_corner`：ok=True，lint=[]，false_positive=[]
  - coverage：9/9 all_pass=True，failure_types 覆盖完整。
- `lint.OVERLAY_TYPES` 增 wall_art/curtain（`lint.py:72-73`），`_overlap_expected` 任一在集合即跳碰撞（`lint.py:215`），挂画叠宿主/窗帘覆窗合法不误报。
- 落位断言：`test_layout.py:345-399`（挂画 orient/窗帘 span/绿植空角/确定性）；AI 配饰生成 + 第7步断言散落 `test_furnish.py` / `test_perspective.py` / `test_acceptance.py` / `test_render_real_geometry.py`。
- `test_eval_scenarios.py::test_all_scenarios_pass_on_real_d` 回归门断言全场景过。
- 两套 pytest 全绿。结论：**PASS**。

## D10 NOSHADOW 红线核验（专项）

| 核验项 | 证据 | 结论 |
|---|---|---|
| `catalog.NOSHADOW_TYPES` 定义未改 | git diff `catalog.py`：`frozenset(t for t,s in CATALOG.items() if s.get("noshadow"))` 逐字节不变（仅删 b1 的 `SOFT_DECOR_TYPES` 派生常量） | ✅ 未变 |
| F003/F004 未复用 NOSHADOW_TYPES | grep：仅 `axon.py`/`scene.py` 引用（b1 D14 阴影 + D13 clearance，本批未改）；perspective/acceptance 用独立集合 `_ITEM_Z0_MM`/`_ALLOWED_ONLY`/`_WALL_BAND_ALLOWED_Z` | ✅ 独立 |
| SOFT_DECOR_TYPES 移除无 dangling 引用 | grep：仅存于注释；无产品代码引用 | ✅ 无残引 |
| axon 阴影 + scene clearance 行为未变 | `test_decor.py` 53 测试绿（含 `test_decor_casts_no_ground_shadow` / `test_decor_exempt_from_inner_clearance`）+ golden 字节 0-skip | ✅ 未回归 |

## 观察（非阻断，供参考）

- **O-1（F002 测试增强建议）**：`test_place_curtain_covers_window_span` 用 r_master（其 S 窗 wtype 恰为 full），未在 pytest 层直接覆盖 normal/high wtype 窗。代码路径正确（`_room_window_spans` 无 wtype 过滤，本报告已独立实测 normal/high 均落位），非缺陷；建议下批次补一条非-full wtype 断言固化审查 #4 回归门。
- **O-2（F003 byte-safe 硬证）**：perspective 层无专用"改动前后逐字节对比"pytest（现有 `test_item_z0_and_height_wall_band` 断言 z0 值 + golden 快照兜底 floorplan_core 侧）。本报告以 sha256 独立实测补齐硬证，结论 byte-identical；建议下批次可将该对比固化为一条 perspective 单测。

两项均为测试覆盖增强建议，不影响本轮任一判定。

## L2 / F007 边界说明

- **[L2] 真实出图未执行**：本域不含真实 provider 调图；`OPENAI_API_KEY`/relay 未授权。挂画进实拍可见性、真实 mask allowed 对位目检属 **F007（executor:evaluator，独立对抗验收）** 范畴，本报告不覆盖，标注待 F007 记账。
- 本域仅就 F001/F002/F003/F004/F006 的代码实装 + 确定性输入侧（mask/几何/lint/prompt 纯函数）验收，全部本地 L1 可判且已判。

---
_产出：隔离 evaluator subagent（local/evaluator-subagent）。结论基于实物与实测，未软化。_
