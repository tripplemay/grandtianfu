# decor-b1 验收报告 — 引擎/API 域（首轮 verifying）

- **批次**：decor-b1（软装配饰 · 引擎 + 编辑器基座）
- **验收域**：引擎/API 线 6 条 generator 功能 — F001, F002, F003, F004, F005, F008
- **不含**：前端 F006/F007（web 域）、F009（evaluator 对抗验证，独立执行）
- **执行者**：local/evaluator-subagent（fresh context，隔离验收）
- **日期**：2026-07-13
- **分支**：feat/decor-b1
- **结论**：**6 PASS / 0 PARTIAL / 0 FAIL**

---

## 0. 测试运行摘要（亲自执行，不采信实现叙述）

```
PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q
  → 145 passed in 0.50s   （0 skipped）

PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q
  → 309 passed in 15.90s  （0 skipped）
```

**Skip 核查（铁律：skip=未跑，非通过）**：
- `rsvg-convert` 已安装（`/opt/homebrew/bin/rsvg-convert`），render 测试未被 skipif 跳过。
- **golden 字节快照真跑真绿**：`test_render_snapshot::test_render_string_matches_baseline_byte_for_byte[平面布置图.svg]` 与 `[D户型-空壳底图.svg]` 均 PASSED（零回归硬证据）。
- decor 专项 18 个测试全部 PASSED（`test_decor.py` 11 + `test_decor_api.py` 3 + `test_perspective.py`/`test_acceptance.py`/`test_furnish.py` 中 decor 用例）。

---

## F001 — 目录新增 wall_art/curtain + noshadow 目录化 · **PASS**

**证据：**
- `catalog.py:189-196` wall_art/curtain 两条，字段齐全：en/shape/w/h/rooms/zh/`category:decor`/`directional:True`/`noshadow:True`/cat2d；wall_art 另带 label2d。
- SWAP_GROUPS `catalog.py:229-230` `"wall_arts":["wall_art"]`、`"curtains":["curtain"]`，每类恰归一组。`test_catalog_api.py:57-64` 三断言（每类有 swap_group / `grouped==set(CATALOG)` / `sum(len)==len(CATALOG)`）全绿。
- 阴影排除 D14：`axon.py:689` `_SHADOW_EXCLUDE=frozenset({"shower","entry_door","partition"})`，`axon.py:1244` 运行时 `t not in _SHADOW_EXCLUDE and t not in _catalog.NOSHADOW_TYPES`。既有 shower/entry_door/partition 仍在硬编码集 → 行为不变；**golden 字节快照全绿即字节级证明**。tv/mirror 无 noshadow 标志，不在 NOSHADOW_TYPES，仍投阴影（`test_decor_casts_no_ground_shadow` 对照 sofa 有 `url(#sh)`）。
- `/api/catalog` 出参含新类型（`test_catalog_serves_decor_types` PASS，category==decor、directional==True）。
- `CATALOG_REV=1`（`catalog.py:14`）**未 bump**（D7）。
- 零回归：无 wall_art/curtain 数据的既有渲染/prompt 由 golden 快照 + `test_d_data_has_no_decor_types`（D 默认方案不含配饰类型）护栏。

---

## F002 — 3D/2D 渲染 + scene 贴墙豁免 · **PASS**

**证据：**
- SPECS `axon.py:637-648`：wall_art 悬空框盒 `z(1000,1400)` + vplane 画面 `z(1030,1370)` 贴 opp 墙；curtain 帘头盒 `z(1400,1450)` + 半透长幔 vplane `z(150,1400)` 贴 opp 墙。MODELS 注册 `axon.py:683-684`（m_from_spec）。
- **不穿墙**：所有 box `z1<=1450`（挂画画框顶 1400 < 墙高 1450；`test_decor_registered_with_vplane_and_under_wall` 断言 `z1<=1450`）。
- **悬空**：`test_wall_art_is_floating` 断言 `min(box.z0)>=800`，实际 1000（离地约 1m 挂墙）。
- 全类型映射约束绿：`test_catalog::test_every_catalog_type_is_renderable`。
- 3D SVG：挂画有悬空盒 + vplane、无地面阴影；窗帘有贴墙 vplane（`test_decor_registered_with_vplane_and_under_wall` + `test_decor_casts_no_ground_shadow`）。
- 2D 贴墙薄矩形：`test_decor_2d_wall_hugging_rect`（`_furn2d_frags` 含 `<rect`）。
- **scene D13 豁免只作用 NOSHADOW_TYPES**：`scene.py:547` `wall_hugging = ax_item.get("t") in _catalog.NOSHADOW_TYPES`（={wall_art,curtain}）。`test_decor_exempt_from_inner_clearance`：挂画 `_dx==0/_dy==0`（不内缩），对照 sofa `_dx==13`（被内缩），挂画无 clearance-shift 记录。**tv/mirror 不在 NOSHADOW_TYPES → 行为不变，golden 快照佐证**。
- golden 字节快照 `test_render_snapshot` 全绿（零回归；不动 data/projects/D）。

---

## F003 — 附着配饰机制 + furnish 换件透传 · **PASS**

**证据：**
- `DECOR_ATTACH` 注册表 `catalog.py:308-333`：cushions/bedding/table_lamp/vase/ornament，各含 hosts 白名单 + per-host mount_z。helper：`is_attach_type`/`attach_mount_z`/`attach_types_for_host`/`attach_en`/`sanitize_decor`（`catalog.py:414-452`）。
- **D12 mount_z 显式对齐实际 3D 模型顶面（对抗核验，非采信注释）**——独立脚本比对每个 (attach,host) 的 `mount_z` vs 该宿主模型 `max(box.z1)`：
  - 平顶件（nightstand/side_table/console_table/sideboard/desk/coffee_table/dining_table/media）：`mount_z == 模型顶` **完全一致**。
  - 座/床件：`mount_z` 命中**座面/床垫面**而非最高盒 —— sofa 470（模型顶 760=靠背）、chaise 405（顶 780）、armchair 470（顶 720）、bed 480（顶 980=床头板）、kids_bed 400（顶 720）、bunk_bed 420（顶 1420=上铺，配饰落下铺）。**证明未用 `max(box.z1)` 启发式**，正是 spec D12 点名的 sofa 座面 470 非靠背 760。
- axon 家具循环 `axon.py:1239-1242`：`if it.get("decor")` → `_attach_prims` 结果 append 进 boxes+extra，与宿主同 `piece()`（深度键/rot 自动生效）。`_attach_prims`（`axon.py:692-726`）table_lamp 仿 floor_lamp（微柱+glowdot `url(#glow)`）。
- **圆形宿主排除**：round 类型走 `draw_round` 于 `axon.py:1216` `continue`，永不进 `_attach_prims`；且 `sanitize_decor` 对 round 宿主全剥（`test_attach_excludes_round_hosts`：`attach_types_for_host(round_t)==[]`）。
- 非法宿主/未知类型 WARN 剥离不阻断（`sanitize_decor`，`test_attach_prims_render_at_host_top`：wall_art 挂 cushions → `([],"")`）。
- **furnish 换件透传 D11**：`furnish.py:175-179` decor 透传 + `sanitize_decor(new_type,...)` 按新宿主过滤。`test_swap_transfers_compatible_decor_and_strips_incompatible`：bed(cushions+bedding)→sofa 保 cushions 剥 bedding；→coffee_table 全剥；→round_table 全剥。
- **无 decor 数据逐字节不变**：`test_attach_render_integration_bytesafe`（`render({**sofa}) == base`；带 decor 时 `!= base` 且更长）。

---

## F004 — prompt_gen 配饰贯通 · **PASS**

**证据：**
- 独立件经 `catalog.en` 自动进逐房清单：`prompt_gen.py:178,185`。`test_prompt_independent_decor_phrases`：输出含 "framed wall art" + "floor-length curtains"。
- 附着件折进宿主短语：`prompt_gen.py:188-189` `d + " with " + _join_en([attach_en(dt) ...])`（在方位短语之前）。`test_prompt_attached_decor_folds_into_host`：`"a sofa with decorative cushions"`、`"a coffee table with a vase with flowers and decorative ornaments"`。
- **无配饰 prompt 逐字节不变（D5）**：`_decor_key` 无 decor/全非法 → `()`，grouping key `(t,zone,())` 与旧 `(t,zone)` 语义等价。`test_prompt_no_decor_is_byte_identical`：无 decor 键 / 空 decor / 全非法 decor 三种均 `== base`。历史 prompt golden（`test_prompt_positions`/`test_room_brief`/`test_partition_still_skipped`）全绿。

---

## F005 — API 出参 + decor 结构校验 + 单测 · **PASS**

**证据：**
- `/api/catalog` 出参含 wall_art/curtain + attach 注册表：`test_catalog_serves_decor_types` + `test_catalog_serves_attach_registry`（`set(attach)==set(DECOR_ATTACH)`）PASS。
- `_furniture_items_error`（`main.py:1273-1279`）：decor 若存在必须是 list（硬）；元素必须是 dict 且 `t` 在 DECOR_ATTACH（硬）；宿主兼容**软校验放行**。`test_decor_api.py`：
  - `test_validate_accepts_valid_decor`：合法 cushions、不兼容 bedding（放行）、无 decor、空 decor → 均 None。
  - `test_validate_rejects_malformed_decor`：非数组 / 元素非对象 / 未注册类型 / 家具非配饰 → 均报错。
- 存取往返无损：`test_expand_preserves_decor_roundtrip`（`catalog.expand` 保 decor 键 + 补外观）。
- api pytest 全绿（309）。

---

## F008 — 第 7 步隔离兜底（D10 生产裂缝）· **PASS**

**证据：**
- `SOFT_DECOR_TYPES`（`catalog.py:302`）= `{"rug"} | NOSHADOW_TYPES` = {rug, wall_art, curtain}。
- **annotate_boxes 跳彩盒**：`perspective.py:324` `if not t or t=="partition" or t in catalog.SOFT_DECOR_TYPES`。`test_annotate_boxes_skips_decor_wall_art_and_curtain`：wall_art+curtain+sofa → `drawn==1`、`legend==[sofa]`（配饰不进彩盒 → 堵住"挂画得墙脚地面盒 → 模型地板画画"）。
- **evaluate_geometry_lock 跳逐盒**：`acceptance.py:171` 跳 `catalog.NOSHADOW_TYPES`（wall_art/curtain 完全跳过，不建盒/不进 allowed/不逐盒验收）。`test_geometry_lock_ignores_decor_wall_art`：含挂画仍 `v["ok"]`（不因配饰盒 FAIL）。
- **既有 rug 跳过逐字节等价（git diff main...HEAD 核验）**：
  - annotate_boxes：旧 `t in ("partition","rug")` → 新 `t in SOFT_DECOR_TYPES`（rug ∈ SOFT_DECOR）→ rug 仍跳，行为不变。
  - evaluate_geometry_lock：旧 skip 条件不含 rug → 新增 `t in NOSHADOW_TYPES`（rug ∉ NOSHADOW）→ rug 仍流到 `acceptance.py:179` 进 allowed 后 continue，行为不变。
- **额外隔离核验（对抗）**：`footprint_mask`（`perspective.py:261` 仅跳 partition）只被 acceptance（NOSHADOW 过滤后逐件调）与 semantic_accept（`_CHECK_TYPES` 白名单逐件调）使用；`semantic_accept._CHECK_TYPES` 不含 wall_art/curtain/cushions/rug；附着件（cushions/vase 等）藏于宿主 decor 子列表、永不作为顶层 item 出现 → **第 7 步全链路对配饰完全隔离**。

---

## 发现的问题

无。6 条功能均基于实物（代码 + 亲自运行的测试输出 + 独立对抗脚本）达标，无 FAIL/PARTIAL。

## 观察项（非缺陷，不阻断签收）

- `footprint_mask`（inpaint 区域 mask）本身只跳 partition，未跳软装件。但在第 7 步路径中它仅被 acceptance/semantic_accept 在各自过滤后逐件调用，独立配饰无法经此路径生成"墙脚彩盒/逐盒验收压分"缺陷（D10 关注点已由 annotate_boxes + evaluate_geometry_lock 双跳堵死）。若 b2 将配饰接入第 7 步 prompt/allowed，届时再评估区域 mask 是否需纳入配饰（与 spec §7 b2 边界一致）。
- b1 边界（预期，非缺陷）：实拍图里配饰不会主动出现（第 7 步只跳过未接入），与 spec §7 一致。

## 与 F009 的衔接

本域已验证渲染/几何的**存在性与字节安全**；F009（floorplan_core 升档对抗验证）负责渲染**正确性目检**（挂画悬浮高度视觉合理性、窗帘覆盖窗区、附着件不穿模比例）+ 至少 1 次第 5 步真实出图（axon-photoreal）。本报告的 mount_z↔模型顶面对齐核验、悬空/贴墙 z 区间、无阴影可作为 F009 的量化输入。
