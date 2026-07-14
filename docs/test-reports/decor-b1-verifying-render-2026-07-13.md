# decor-b1 · F009 轴测渲染正确性对抗验收报告

- **批次：** decor-b1（软装配饰 · 引擎 + 编辑器基座）
- **Feature：** F009 — 轴测渲染正确性对抗验收（floorplan_core 升档对抗验证，executor:evaluator）
- **阶段：** verifying（首轮，fix_rounds=0）
- **评估者：** local/evaluator-subagent（fresh context，自行读盘取证）
- **日期：** 2026-07-13
- **verdict：** **PASS**

---

## 0. 方法

按 CLAUDE.md「floorplan_core 几何/渲染正确性升档对抗验证」执行——不以「测试绿」为终点，而是**生成实际轴测 SVG/PNG 用对抗视角人工目检 + 逐图元几何断言**。取证来源：

1. 直接读源码：`axon.py`（SPECS/MODELS/`m_from_spec`/`_attach_prims`/`_SHADOW_EXCLUDE`/家具循环注入点/render）、`catalog.py`（DECOR_ATTACH/mount_z/NOSHADOW_TYPES/sanitize_decor）、`scene.py`（D13 豁免）、`furnish.py`（`_swap_item_type` D11）、`perspective.py`/`acceptance.py`（F008 D10 跳过）、`apps/web/.../decorAttach.ts`（前端 hosts 镜像）。
2. 构造含**全部配饰类型**的样例布局，`axon.render(geom, furniture, mode='photo')` 出图，`geom = geom_bundle(load('data/projects/D/geometry.json'), derive(...))`。
3. rsvg-convert 转 PNG 逐区域放大目检。
4. 临时验收脚本置于 `/tmp`（不入产品代码），仅 SVG 样本落 `docs/test-reports/`。

**渲染环境健全性：** `rsvg-convert`（/opt/homebrew）+ Noto CJK 就绪，render 测试**实跑非 skip**。两套 pytest 全绿：`floorplan_core 145 passed` / `apps/api 309 passed`。golden 字节快照 `test_render_snapshot.py` **5 passed**（含 `平面布置图.svg` + `D户型-空壳底图.svg` 逐字节比对）→ 无配饰 D 布局零回归硬证。

**产物：**
- SVG 样本：`docs/test-reports/decor-b1-render-sample-2026-07-13.svg`（120,161 B，含全部 8 件，其中 2 独立 + 6 附着宿主）
- 目检 PNG：全景 + 沙发/挂画、台灯、床、窗帘、挂画独立件 5 组放大裁切（会话内已核）

---

## 1. 对抗检查逐项结论

### 1.1 挂画 wall_art — PASS
| 检查 | 证据 | 结论 |
|---|---|---|
| 悬浮墙上部（非落地） | 画框盒 z=(1000,1400)，`min z0=1000 ≥ 800` | ✅ |
| 顶不穿墙 | `z1=1400 < WALL_H=1450` | ✅ |
| 画面朝房内 | vplane side=`opp`(orient) 竖面 polygon，朝向房内 | ✅ |
| 无地面阴影 | 单件渲染 `url(#sh)` 计数 = **0**；`wall_art∈NOSHADOW_TYPES`，家具循环 `t not in _SHADOW_EXCLUDE and t not in NOSHADOW_TYPES` 跳过 shadow | ✅ |
| 视觉目检 | 独立件放大图：北墙 + 西墙各一幅，均为「棕框 + 米色画面」悬于墙上部、朝房内、无落地投影 | ✅ |

### 1.2 窗帘 curtain — PASS
| 检查 | 证据 | 结论 |
|---|---|---|
| 贴墙半透长幔 | vplane fill=`#cbc3d2aa`（半透），side=opp 贴墙 | ✅ |
| 落地 | 长幔 z=(150,1400)，`z0=150 ≤ 200`（近落地小留边） | ✅ |
| 达墙上部 | `z1=1400 ≥ 1300`（帘头盒 1400–1450 接墙顶） | ✅ |
| 不遮结构墙/窗几何 | 半透，放大图中窗棂/窗框结构透过可见；单幅仅覆盖一窗跨（b1 手放，b2 自动吸附窗 span） | ✅ |
| 无地面阴影 | 单件 `url(#sh)`=0 | ✅ |

### 1.3 附着件比例/位置/穿模 — PASS
| 宿主·配饰 | 证据 | 结论 |
|---|---|---|
| sofa+cushions（两只抱枕） | 从座面 470 起，x 中心 182.6/227.4 **错开不重叠**，高 130 | ✅ |
| sofa+vase | 瓶身+花冠两段，从座面 470 起 | ✅ |
| bed+[cushions,bedding] | 目检：床垫顶两枕 + 横搭毯，靠床头，未穿床架/未悬空 | ✅ |
| coffee_table+[vase,ornament] | 从台面 420 起，x 中心 137.5/162.5 错开，盒在宿主 footprint 内不飞出 | ✅ |
| nightstand+table_lamp | 灯杆+灯罩+发光点 `url(#glow)`；从台面 470 起；**目检：杆+发光灯罩比例真实** | ✅ |
| armchair+cushions | 座面 470 起（SPECS 坐垫顶） | ✅ |
| 深度键/旋转透传 | 附着盒 append 进宿主 boxes，与宿主同 `piece()`（painter 深度键 + rot 包裹自动生效）；rot=30 宿主+decor 渲染不崩且入 `rotate(30 …)` 组 | ✅ |

### 1.4 mount_z 对齐实际模型顶面（D12）— PASS
16 组 `attach_mount_z(t, host)` 逐一对照 `axon.py` 实际 m_* 顶面 z，**全部三方一致**（声明 = spec = 模型顶面）：

| 配饰@宿主 | mount_z | 模型顶面依据 |
|---|---|---|
| cushions@sofa | 470 | m_sofa 座垫 z(340,**470**) |
| cushions@bed / bedding@bed | 480 | m_bed 被面 z(430,**480**) |
| cushions@armchair | 470 | SPECS armchair 坐垫 (340,**470**) |
| cushions@chaise | 405 | m_chaise top_poly z=**405** |
| cushions@kids_bed | 400 | SPECS kids_bed 被面 (360,**400**) |
| cushions@bunk_bed | 420 | SPECS bunk_bed 下垫 (300,**420**) |
| vase/ornament@coffee_table | 420 | m_coffee `m_legs_top` ttop=**420** |
| vase/ornament@media | 520 | m_media 盒 z(0,**520**) |
| vase/ornament@dining_table | 750 | m_dining ttop=**750** |
| table_lamp@nightstand | 470 | nightstand m_cab z=**470** |
| table_lamp@side_table | 480 | side_table `m_legs_top` ttop=**480** |
| table_lamp@console_table | 800 | console m_cab z=**800** |
| table_lamp@sideboard | 750 | sideboard m_cab z=**750** |
| table_lamp@desk | 750 | m_desk `m_legs_top` ttop=**750** |

> 注：spec §3.3 的 mount_z 为**建议草案**（chaise 400/kids_bed 360/desk 740）。Generator 已按 D12 要求对照实际模型微调为 chaise **405**/kids_bed **400**/desk **750**——修正后**更贴顶面**（chaise top_poly=405、kids_bed 被面=400、desk ttop=750），偏离方向正确，非缺陷。

### 1.5 换件透传 decor（D11）实测 — PASS
`furnish._swap_item_type` 实调（apps/api）：

| 换件 | 输入 decor | 输出 decor | 规则 |
|---|---|---|---|
| sofa→armchair | cushions,vase | **cushions**（剥 vase） | armchair∈cushions.hosts，∉vase.hosts |
| sofa→chaise | cushions,vase | **cushions** | chaise∈cushions.hosts |
| sofa→coffee_table | cushions,vase | **vase**（剥 cushions） | coffee_table∈vase.hosts，∉cushions.hosts |
| sofa→coffee_table | 仅 cushions | **∅（decor 键移除）** | 全不兼容→剥净 |
| sofa→round_table（圆形） | cushions,vase | **∅** | 圆形宿主无 hosts→全剥 |
| bed→kids_bed | cushions,bedding | **cushions,bedding** | 两者均兼容 |

换件保持中心 + 采用新类型尺寸（coffee_table w=100 h=60）。✅

### 1.6 前后端 hosts 双端一致 — PASS
`catalog.DECOR_ATTACH.hosts`（后端）vs `apps/web/src/lib/floorplan/decorAttach.ts`（前端）——5 类附着型 hosts 白名单**集合逐一相等**（cushions/bedding/table_lamp/vase/ornament）。双份真源无漂移。✅

### 1.7 圆形宿主排除 / 非法项剥离（D9）— PASS
- `_attach_prims(round_table + vase)` → `([], "")` 圆形宿主不渲染附着。✅
- `_attach_prims(wall_art + cushions)` → `([], "")` 非宿主剥离。✅
- `sanitize_decor("sofa", [{"t":"bedding"}])` → `([], warns)` 不兼容宿主 WARN 剥离不阻断。✅

### 1.8 golden 零回归 / byte-safe — PASS
- `test_render_snapshot.py` 5 passed（D 布局逐字节不变）。
- 无 `decor` 键 == 空 `decor: []`（逐字节相等）。
- 全景含配饰 SVG=120,161 B vs 剥配饰控制组=113,884 B（+6,277 B 为配饰图元增量）。
- 全景 `url(#sh)` 计数 = **6** = 恰为 6 件实心宿主（sofa/coffee_table/armchair/nightstand×2/bed）；2 独立配饰 + 全部附着件**不新增阴影**。✅

### 1.9 边缘健全性 — PASS
含配饰 SVG 合法 XML（minidom 可解析）、无 NaN/inf 坐标、rot 宿主+decor 不崩。

---

## 2. 第 5 步真实出图（axon-photoreal）—— [L2] 降级记账，不阻断

- 本机 `OPENAI_API_KEY` / `OPENAI_BASE_URL` **均未配置** → `config.ai_enabled=False`，AI 端点返回 503。
- 真实出图属 **[L2]**（真实外部 relay 调用 + 计费），需用户明确授权；本会话**未授权**。
- **降级方案：** 第 5 步 img2img 的输入即本报告核验的轴测 SVG——配饰已在 SVG 层几何正确进入渲染管线（独立件悬空贴墙 + 附着件顶面成形），img2img 仅做风格化叠加。**「配饰进渲染管线可见」在 SVG 层已获硬证**；AI 风格化不改变几何输入，属独立环节。
- **结论：** 第 5 步真实出图记为「[L2] 未执行，待授权/环境限制」，**不算 FAIL**（符合 F009 acceptance「若无可降级为 SVG 目检并记账」及 evaluator L1/L2 分层）。

---

## 3. 软观察（Soft-watch，不影响 F009 PASS）

| # | 观察 | 影响 | 兜底 |
|---|---|---|---|
| S1 | wall_art/curtain 目录默认 footprint（80×8 / 120×10）面向**水平墙（N/S）**；放到**竖直墙（W/E）**需把 w/h 转置（本报告手动传 8×80 即渲染正确）。 | 与既有薄贴墙件 **mirror（60×8）行为一致**，非新缺陷。b1 由编辑器近墙吸附 + 用户手放处理，b2 自动吸附。 | 已属既有约定；建议 b2 auto-place 时随墙轴转置 footprint。归 BL-decor-b2。 |
| S2 | 窗帘 vplane（y=1400）与外墙块（y≈1410）painter 深度键近似（≈2265），本布局渲染正确无遮挡；不同布局理论上存在 z-fighting 余地。 | 本样例目检无遮挡/闪面。 | 观察项；如后续出现贴墙件与墙 z-fighting，b2 可给贴墙件深度键微偏置。 |

两条均为**信息性观察**，已有明文兜底/归属，不构成 acceptance 偏离。

---

## 4. 结论

**F009：PASS。** 软装配饰在轴测 3D 渲染中几何正确——挂画悬空贴墙、画面朝房内、无地面阴影；窗帘贴墙半透长幔落地不遮结构；附着件（抱枕/搭毯/花瓶/摆件/台灯）在宿主顶面正确高度、比例真实、多件错开不穿模不悬空；mount_z 16 组全对齐实际模型顶面（D12）；换件 decor 双端透传 + 按新宿主过滤（D11）实测正确；圆形排除/非法剥离（D9）生效；golden 字节零回归。第 5 步真实出图因 AI 未配置降级为 SVG 几何目检并记账（[L2] 环境限制，不阻断）。

**未发现任何几何/渲染缺陷。**

### 附：命中的验收依据
- acceptance 全项代码层 + 实测 PASS；F008 D10 隔离兜底（perspective 用 `SOFT_DECOR_TYPES`、acceptance 用 `NOSHADOW_TYPES`+rug 单独进 allowed）读码一致，语义符合。
- Soft-watch S1/S2 均有明文兜底与归属（BL-decor-b2 / 观察项）。
