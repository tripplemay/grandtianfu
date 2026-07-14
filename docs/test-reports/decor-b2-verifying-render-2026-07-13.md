# decor-b2 首轮验收报告 — 渲染/几何对抗验证域（F007）

- **批次**：decor-b2（软装配饰 AI 生成 + 实拍链路完整接入）
- **阶段**：verifying（首轮，fix_rounds=0）
- **域**：F007 — AI 配饰 + 第7步实拍**升档对抗验证**（floorplan_core 几何 + AIGC 链路双风险点，CLAUDE.md 要求）
- **executor**：evaluator（本报告 = 该功能的交付物）
- **评估者**：隔离 evaluator subagent（fresh context，自磁盘取证，不接受实现叙述）
- **评估 SHA**：HEAD=14a4f72（feat/decor-b2，stacked off feat/decor-b1）
- **日期**：2026-07-13
- **结论**：**F007 = PASS**（头号项 + 全部对抗检查通过）

> 姊妹报告：`decor-b2-verifying-python-2026-07-13.md`（F001-F004/F006）、`decor-b2-verifying-web-2026-07-13.md`（F005）。本报告覆盖 F007 并整合全批终判（§8）。

---

## 0. 方法学

对抗验证 ≠ 看测试绿。本报告用**真实 mask / 投影像素**做量化对抗，临时脚本落 `/tmp/decor-b2-scratch/`（不入产品代码），产物 mask/PNG 落 `docs/test-reports/assets` 引用。所有结论基于实际渲染/投影输出，未采信实现叙述或 commit message。

L1 基线（本地实跑，非叙述）：
| 套件 | 命令 | 结果 |
|---|---|---|
| 引擎 | `PYTHONPATH=packages/floorplan_core pytest packages/floorplan_core/tests -q` | **152 passed, 0 skip** |
| API | `PYTHONPATH=packages/floorplan_core:apps/api pytest apps/api/tests -q` | **320 passed, 0 skip** |
| golden 字节快照 | `test_render_snapshot.py`（含引擎套件） | 绿，**0 skip**（`rsvg-convert`=/opt/homebrew/bin 可用，非静默跳过） |

---

## 1. 头号验收项（审查 #3，最高敏感度）— PASS

**命题**：含挂画的 `evaluate_geometry_lock` 的 allowed 区，是否真覆盖挂画墙面区域（含画框略高于渲染顶 z=1400 的边界；allowed 抬顶 z=1500 是否够），确认不误判 structure、且挂画不进逐盒 furnished。

### 1.1 修正的对抗方法（关键）

首轮用现网单测 fixture 位置 `wall_art @ (dx=300,dy=300)` 复现时发现：该房内坐标映射到世界 `(3000,3000)mm` = **合成相机眼位**，投影退化 → allowed 覆盖**整画幅**（area=3145728=全帧）。**该位置无法真正考核"画框略高触发 structure 误判"边界**（allowed=全帧则画哪都不误判，trivially pass）。故改用相机正视野内的墙位 `wall_art @ (820,900)`（`box_usability` = usable/in_frame_frac=1.0/near=False）重做量化。

> ⚠️ **观察 O-3（测试质量，非产品缺陷）**：现网单测 `test_geometry_lock_decor_wall_art_paint_in_allowed_no_structure_fail`（test_acceptance.py:88）用的正是退化位置，其 structure 断言 trivially 成立。测试仍**正确 PASS**，但未真正压到边界。建议下批次把 fixture 挪到正视野内墙位（本报告已独立补齐边界验证）。

### 1.2 覆盖（渲染盒 ⊆ allowed 盒）— 0 未覆盖

| 盒 | z 带 | 像素范围 (y0,y1,x0,x1) | area |
|---|---|---|---|
| 渲染盒（annotate 画的） | z0=1000 → hz=1400 | (574,656,1098,1225) | 10165 |
| allowed 盒（水平外扩 150mm + z=1500 抬顶） | z0=1000 → 1500 | (553,658,1056,1266) | 21362 |

- **渲染盒未被 allowed 覆盖的像素 = 0**（完全覆盖）。
- **顶部余量**：allowed 顶 v=553 比渲染顶 v=574 **高 21 px**（z=1500 抬顶带来的容差，画框略高于渲染顶 1400 时被吸收）。
- **底部余量**：allowed 底 v=658 比渲染底 v=656 低 2 px；下方另有 `_extend_down(0.9)` 与 `_dilate(~20px@work→~80px@full)` 兜底。
- 视觉证据 `assets/decor-b2-wall_art_render_vs_allowed.png`：红（渲染盒）被绿（allowed）**四面包裹**，含顶部余量。

### 1.3 structure 误判边界（模型在不同高度画挂画）— 全不误判

在挂画墙面带按世界高度 z_top 画随机内容，跑 `evaluate_geometry_lock`：

| 场景 | 模型画到 z_top | v["ok"] | structure ok | bad_tiles | wall_art∈furnished |
|---|---|---|---|---|---|
| 画在渲染盒内（基准） | 1400 | True | True | 0/178 | **False** |
| 画框略高于渲染顶 | 1450 | True | True | 0/178 | False |
| 画到 allowed 顶 | 1500 | True | True | 0/178 | False |
| 远高于 allowed 顶（对抗） | 1600 | True | True | 0/178 | False |
| 极端高（对抗上限） | 1800 | True | True | 0/178 | False |

- 全部 5 档 **无 structure FAIL**，`wall_art` 全部**不在逐盒 furnished 检查**（`_ALLOWED_ONLY` 生效）。
- annotate 同步验证：`drawn=2`，legend=`[(purple,sofa),(blue,wall_art)]`——挂画用墙面带 z0 进彩盒。

### 1.4 load-bearing 反证（allowed 机制确实在防误判）

隔离 allowed 机制的作用（大挂画 + 棋盘格强边缘，保证 work-res 有信号）：

| allowed 配置 | bad_tiles | 判定 |
|---|---|---|
| 无 allowed（挂画不进 furniture） | **7/192** | **FAIL（会误判 structure）** |
| allowed 顶=1400（无 z-bump） | 0/178 | ok |
| allowed 顶=1500（现网 F004） | 0/175 | ok |

- **allowed 覆盖整体 load-bearing**：缺失时 7 坏块 ≥ 阈值 3 → structure FAIL；有覆盖 → 0 坏块。
- z=1500 抬顶在本 fixture 是 belt-and-suspenders（水平外扩 + extend_down + dilate 已覆盖 z=1480 过画）；但 z-bump 是**随透视缩放的正确守卫**（挂画投影在画面上部、垂直梯度陡时，固定像素 dilation 可能不够，z-bump 抬顶按世界坐标扩，语义正确）。保留合理。

**头号项判定：allowed 真覆盖挂画墙面区（0 未覆盖 + 21px 顶余量 + 视觉四面包裹），不误判 structure（5 档全过），不进逐盒 furnished。PASS。**

---

## 2. annotate 墙面带投影 — PASS

`annotate_boxes([sofa(+cushions), wall_art, curtain, rug])`：

- `drawn=3`，legend types = `[sofa, wall_art, curtain]`。
- **wall_art / curtain 进彩盒**；**rug 不进彩盒**（地面软装走 prompt 文字）；**cushions（attach）不进彩盒**（藏宿主 decor）。
- 墙面带 vs 地面（y 像素）：挂画盒 y∈[574,656]、窗帘盒 y∈[565,823]、地面 rug 盒 y∈[745,833]。**挂画盒最低点 656 < rug 盒最低点 833** → 挂画悬空在墙面带（非墙脚地面）；窗帘从墙面带垂到近地（floor-length）。

---

## 3. byte-safe（D3）— PASS（逐字节硬证）

- `_item_z0_mm`：wall_art=1000 / curtain=150 / **sofa,media,tv,coffee_table,dining_table,wardrobe,rug,plant,chair,bookshelf 全=0.0**。
- **独立实测**：sofa 的 `_box_polys` 用新逻辑（z0=_item_z0_mm）vs 手动强制 `pd(...,0.0)`（模拟 pre-F003）→ **byte-identical=True**（深度 <1e-12、像素相等）。sofa `footprint_mask` md5 稳定。
- git diff 佐证：`_box_polys` 唯一改动 `base=pd(px,py,0.0)` → `base=pd(px,py,z0)`，非 decor 件 z0=float(0.0)=旧值。
- golden 字节快照 `test_render_snapshot.py` 2 个 baseline **byte-for-byte 绿，0 skip**。

---

## 4. NOSHADOW 红线（D10）— PASS

| 核验项 | 证据 | 结论 |
|---|---|---|
| `catalog.NOSHADOW_TYPES` 定义未改 | `git diff b1..b2 catalog.py`：定义行 `frozenset(t for t,s in CATALOG.items() if s.get("noshadow"))` 无 +/-；仅删除派生常量 `SOFT_DECOR_TYPES` | ✅ 未变 |
| F003/F004 未复用 NOSHADOW_TYPES 做新跳过集 | perspective 用字面 `{partition,rug}`；acceptance 用 `_ALLOWED_ONLY`/`_WALL_BAND_ALLOWED_Z` 独立集合 | ✅ 独立 |
| axon 阴影 + scene clearance 行为未变 | `git diff b1..b2 axon.py scene.py` grep NOSHADOW/_SHADOW_EXCLUDE/wall_hugging = **无改动**；`test_decor.py` 14 测试绿（含 `test_decor_casts_no_ground_shadow`/`test_decor_exempt_from_inner_clearance`） | ✅ 未回归 |
| SOFT_DECOR_TYPES 移除无残引 | grep：仅存于注释，无产品代码引用 | ✅ 干净 |

---

## 5. prompt 锚定短语 + 附着聚合 — PASS

`_geometry_lock_prompt(legend, furniture=[sofa+cushions, wall_art, curtain, rug])`：

| 检查 | 命中 |
|---|---|
| 挂画锚定（`framed wall art ... on the wall` + `centered above the furniture`） | ✅ |
| 窗帘锚定（`floor-length curtains ... over the window`） | ✅ |
| rug 文字（`area rug ... under the seating`） | ✅ |
| 附着聚合（`soft furnishings: ... cushions`） | ✅ |
| 盒色仅标记（`position markers only`） | ✅ |

- **无配饰旁证**：`_geometry_lock_prompt([sofa], [sofa])` 不含 `framed wall art`/`floor-length curtains`/`soft furnishings`（历史 prompt 基线不受污染）。

---

## 6. furnish AI 配饰端到端 + 落位合理性 + 确定性 — PASS（真实 D 几何）

mock provider 出 `decor:[{room_id:r_live, attach:[{host_t:sofa, add:[cushions]}], standalone:[wall_art,curtain,plant]}]` → `generate_candidates`：

- **warnings=[]**（合法项全保留）；scheme.furniture 57 件（base 55 + 2 独立件）。
- **attach**：r_live 2 个 sofa 宿主均写 `decor=[{t:cushions}]`（无独立坐标）。
- **standalone**：新增 `wall_art`（有坐标 dx/dy/orient）、`plant`（有 dcx/dcy）。
- **确定性**：连跑 3 次，落位坐标逐字一致（True）。
- 落位合理性目检：
  - **绿植** dcx/dcy=(24,24) 到最近房角距 48 → 靠角 ✓
  - **窗帘** 独立测 13 个含窗房间：宽逐一对齐窗 span（对齐=True），N/S/E 墙均正确转置，含 full+normal wtype（审查 #4 全 wtype 生效）✓
  - **挂画** wall-flush 薄条、in-bounds、orient=宿主 orient（见观察 O-1）✓
- **[L1] 视觉旁证**：axon dollhouse SVG 渲染（纯 floorplan_core）含 decor vs 无 decor 的 diff +2567 字节；PNG 目检见 `assets/decor-b2-axon_with_decor.png`——沙发抱枕、控制台台灯、绿植、墙面挂画框均正确渲染，链路无破损。

### r_live 窗帘"未落位"= 正确行为（非缺陷）

e2e 中 r_live 的 curtain 被跳过：独立核查 r_live rect=[495,490,720,765] 的**4 面墙上无任何窗**（D 的 full 窗在 y=1410，位于 r_live S 墙 y=1255 之外，属相邻房/阳台）。`_place_curtain` 无 span → 返回 None（"不瞎放"）。**正确**。

---

## 7. [L2] 第7步真实出图 — 降级记账（环境限制，非 FAIL）

- 本机 `OPENAI_API_KEY` / `OPENAI_BASE_URL`（relay）**均未设**（`ai_enabled=False`，AI 端点 503）。**无法执行真实 provider 出图**验证"配饰进实拍图可见"。
- 属**环境限制**，非产品缺陷。spec F007 acceptance 明文允许该降级：*"配饰进实拍可见（若 AI 配置则真实出图，否则 SVG/mask 几何目检降级记账 [L2]）"*。
- **已执行的降级替代**：(a) annotate 彩盒墙面带投影目检（§2）；(b) allowed mask 对位 + structure 边界对抗（§1）；(c) prompt 锚定短语核查（§5）；(d) axon SVG/PNG 视觉旁证 decor 进渲染（§6）。挂画/窗帘从**彩盒 → prompt → allowed 验收**三段几何链路均在本地 L1 可判且已判。
- **兜底**：待用户授权 relay 后，可在 staging 跑一次 `_render_real_geometry_lock` 抽验（记 backlog `BL-decor-b2-L2-realphoto`）。

---

## 8. 全批终判（整合三域）

| Feature | 标题 | executor | 域 | verdict |
|---|---|---|---|---|
| F001 | furnish AI 配饰生成 | generator | python | **PASS** |
| F002 | 确定性落位 | generator | python | **PASS** |
| F003 | 第7步 _box_polys z0 + annotate | generator | python | **PASS** |
| F004 | 第7步 prompt 锚定 + acceptance allowed | generator | python | **PASS** |
| F005 | 方案页配饰呈现 + brief 配饰偏好 | generator | web | **PASS** |
| F006 | 回归评测集扩展 | generator | python | **PASS** |
| F007 | AI 配饰 + 第7步实拍对抗验收 | evaluator | render | **PASS** |

**PASS 7 · PARTIAL 0 · FAIL 0。**

> F001-F006 判定：python 域独立 evaluator 报告 + 本 render 域独立复核（头号项 / byte-safe / NOSHADOW / prompt / e2e），结论一致。F005 判定：web 域独立 evaluator 报告 + 本域独立 spot-check（后端持久化 9 passed + web tsc exit 0）。三域结论互不软化。

### 首轮 PASS 三条硬条件（evaluator.md §14）

| 条件 | 满足 |
|---|---|
| (a) Acceptance 全代码层 PASS | ✅ 7/7 feature 实装且符合；两套 pytest 152+320 全绿 0 skip；单测 ≥ spec 要求 case 数 |
| (b) L1 + L2 全 PASS | ✅ L1 全绿；L2 真实出图为 spec 明文授权的 [L2] 降级（SVG/mask 几何目检已执行），非产品 FAIL |
| (c) 所有 soft-watch 有明文兜底 | ✅ 见下 |

### Soft-watch（全部明文兜底，不阻断 done）

| # | 项 | 兜底 |
|---|---|---|
| SW-1 | 落位美学（挂画居中/窗帘对齐为启发式） | spec §7 明文（"F007 目检 + 回归场景门兜底；不追求完美，追求合理且不误判"）；F006 三场景回归门 + 本报告 §6 目检已守 |
| SW-2 | [L2] 第7步真实出图未执行 | spec F007 明文降级（SVG/mask 几何目检）；已执行替代 §7；记 backlog BL-decor-b2-L2-realphoto |
| SW-3 | 挂画 orient=facing vs backing（观察 O-1） | 落位在"合理且不误判"标准内（wall-flush/in-bounds/确定性），归 spec §7 启发式声明；建议后续 polish（见观察） |
| SW-4 | 测试 fixture 增强（O-1 非-full wtype 断言 / O-2 perspective byte-for-byte / O-3 head-line 非退化 fixture） | 本报告已独立补齐三项实测；建议下批次固化为 pytest 断言（记 backlog） |

---

## 9. 观察（非阻断，供 Planner 下批次参考）

- **O-1（落位·挂画 orient 语义）**：`_place_wall_art` 以 `host.orient` 作为挂画贴墙方向（设计意图=宿主"背靠墙"，见单测 `test_place_wall_art_on_host_backing_wall`）。但真实 D 数据里部分沙发的 `orient` 是**朝向**而非背靠墙——r_live 首个 sofa `orient='E'` 而实际贴 S 墙（`_nearest_wall`=S），致挂画落在**沙发朝向的 E 墙**而非严格"沙发上方"。输出仍 wall-flush / in-bounds / 确定性（不误判），落在 spec §7 启发式区。**建议 polish**：当 `host.orient` 看似朝向（与 `_nearest_wall` 冲突）时优先取 `_nearest_wall` 作背靠墙，使挂画更贴"宿主上方"。
- **O-2**：perspective 层无"改动前后逐字节对比"pytest；本报告以 sha256/多边形逐点独立实测补齐 byte-identical 硬证。建议固化一条 perspective 单测。
- **O-3**：现网 head-line 单测 fixture 用退化相机眼位（allowed=全帧），未真正压边界；本报告用正视野墙位补齐。建议迁移 fixture。
- **O-4（去重边界）**：`apply_decor` 的 standalone 仅在同一候选内去重（≤1/类型/房），不与该房**既有** standalone 家具去重。D 现无 decor 且 validation 已 cap，低风险；若未来户型预置挂画/绿植，LLM 追加可能重叠。建议 backlog 记录。

---

_产出：隔离 evaluator subagent（local/evaluator-subagent）。结论基于实测（真实 mask/投影/渲染输出）与实物代码，未软化。临时脚本 `/tmp/decor-b2-scratch/*.py`（不入产品代码）。_
