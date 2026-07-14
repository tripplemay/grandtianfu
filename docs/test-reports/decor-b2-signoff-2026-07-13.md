# decor-b2 Signoff 2026-07-13

> 状态：**Evaluator 首轮验收 PASS**（progress.json status=verifying → done）
> 触发：软装配饰第二批交付完成——furnish AI 自动生成配饰（确定性落位）+ 第7步实拍完整接入。

---

## 变更背景

decor-b1 已交付软装配饰的**引擎 + 编辑器基座**（配饰进目录/渲染/轴测/手动摆放/换件透传/第7步隔离兜底），但刻意留下两个边界：(1) 配饰全靠用户手动摆；(2) 配饰不进实拍效果图。decor-b2 补齐这两块：让 furnish AI 按风格**自动生成配饰**并**完整接入第7步实拍**。第7步几何/渲染正确性为最高风险块（挂画 allowed 区对位墙面高度带否则 structure 误判），CLAUDE.md 要求 F007 升档对抗验证专门守此。

---

## 变更功能清单

### F001：furnish AI 配饰生成 · generator · **PASS**
- **文件**：`apps/api/furnish.py`（修改）
- **改动**：`layout_summary` 富化（每 piece 加 attach_options、每房加 decor_slots）；`build_messages` 扩 LLM schema（decor: attach/standalone，明示不出坐标）；`validate_candidates` 增 decor 校验（attach 宿主实例存在性 + 类型合法性；standalone 房白名单 + 同房去重 ≤1；非法剥离记 warning）。
- **验收**：e2e mock provider 出合法 decor → warnings=[] 全保留；单测覆盖非法（错宿主/错房/未知/宿主不存在/重复）剥离；无 decor 候选行为不变。

### F002：确定性落位 · generator · **PASS**
- **文件**：`packages/floorplan_core/floorplan_core/layout.py`（新增 `place_decor_standalone` + `_place_wall_art`/`_place_curtain`/`_place_plant`/`_room_window_spans`）、`apps/api/furnish.py`（`apply_decor`）
- **改动**：挂画居中同房宿主贴墙（无宿主跳过）；窗帘吸附最大窗跨（**全 wtype**，审查 #4）；绿植落最靠角空位（避让既有家具+门，审查 #6）。attach 写宿主 decor、standalone 落坐标。
- **验收**：独测 13 个含窗房间窗帘 span 对齐（含 full+normal wtype）；绿植靠角；挂画 wall-flush；确定性 3 次一致；r_live 无窗正确跳过窗帘（"不瞎放"）。

### F003：第7步 `_box_polys` z0 + annotate 放行独立件 · generator · **PASS**
- **文件**：`apps/api/aigc/perspective.py`（`_item_z0_mm`/`_box_polys` z0/`_DEFAULT_HEIGHT_MM`/`annotate_boxes` skip）、`packages/floorplan_core/floorplan_core/catalog.py`（移除派生常量 SOFT_DECOR_TYPES）
- **改动**：挂画/窗帘盒从墙面带 z0（1000/150）投到顶（1400/1450）；annotate skip 改字面 `{partition,rug}`，wall_art/curtain 进 legend。
- **验收**：sofa `_box_polys` 逐字节等价（z0=0.0）；golden 字节快照 0 skip 绿；挂画盒在墙面带（y 靠上非墙脚）；rug/attach 不进彩盒。

### F004：第7步 prompt 锚定 + acceptance allowed 扩展 · generator · **PASS**（最高风险块）
- **文件**：`apps/api/main.py`（`_geometry_lock_prompt`）、`apps/api/aigc/acceptance.py`（`_ALLOWED_ONLY`/`_WALL_BAND_ALLOWED_Z`/allowed 抬顶）
- **改动**：wall_art/curtain 锚定短语 + 附着聚合短语；acceptance 用**独立显式集合**让墙面带件进 allowed（抬顶 z=1500/1550 加垂直上沿余量）+ 不进逐盒 furnished；**不复用/不改 NOSHADOW_TYPES**（D10）。
- **验收**：**头号项 PASS**（allowed 0 未覆盖渲染盒 + 21px 顶余量 + structure 5 档不误判 + wall_art 不进 furnished + load-bearing 反证）；prompt 6 短语命中；无配饰不加短语。

### F005：方案页配饰呈现 + brief 配饰偏好 · generator · **PASS**
- **文件**：`apps/web/src/app/studio/projects/[id]/scheme/page.tsx`、`apps/web/src/lib/floorplan/decorAttach.ts`、`SchemeBriefEditor.tsx`、`apps/api/schemes.py`、`brief_prompt.py`
- **改动**：方案卡「配饰 N 项」badge（独立件+附着件计数、>0 才显示、复用公共 Badge）；brief `decor_preferences` LIST_FIELD 编译进 prompt。修复持久化死字段（`_BRIEF_LIST_KEYS` 缺 decor_preferences）。
- **验收**：web tsc exit 0（独立复跑）；后端持久化往返 9 passed；三处白名单逐字一致；深色主题成对 dark:。

### F006：回归评测集扩展 · generator · **PASS**
- **文件**：`apps/api/aigc/eval_scenarios.py`、`lint.py`、`test_layout.py`/`test_furnish.py`/`test_perspective.py`/`test_acceptance.py`
- **改动**：3 配饰场景（decor_wall_art_above_sofa / decor_curtain_on_window / decor_plant_in_corner）forbid_lint 断言；lint.OVERLAY_TYPES 增 wall_art/curtain。
- **验收**：真实 D 全场景 all_pass=True，配饰场景 false_positive=[]；两套 pytest 全绿。

### F007：AI 配饰 + 第7步实拍对抗验收 · **evaluator** · **PASS**
- **产出**：`docs/test-reports/decor-b2-verifying-render-2026-07-13.md`（+ assets 2 PNG）
- **改动**：无产品代码（executor:evaluator，只写报告 + 临时脚本）。
- **验收**：头号项（真实 mask 对位）+ annotate 墙面带 + byte-safe + NOSHADOW 红线 + prompt 锚定 + furnish e2e + 落位合理性 + 确定性 全 PASS；[L2] 真实出图降级记账（spec 授权）。

---

## 未变更范围

| 事项 | 说明 |
|---|---|
| `catalog.NOSHADOW_TYPES` 定义 | D10 红线：承 axon 阴影排除 + scene clearance 豁免，定义逐字节未改 |
| axon.py / scene.py 阴影+clearance 逻辑 | git diff 无改动，b1 decor 14 测试绿 |
| 既有普通件第7步投影 | `_box_polys` z0 默认 0，byte-identical（sofa sha 稳定 + golden 快照绿） |
| 无 decor 的 furnish / 无独立件的第7步链路 | 行为字节不变 |
| data/projects/D | 未碰（golden 字节零回归） |

---

## 预期影响

| 项目 | 改动前（b1） | 改动后（b2） |
|---|---|---|
| furnish AI 配饰 | 不产出，全手动摆 | 自动出 decor 清单 + Python 确定性落位 |
| 配饰进第7步实拍 | 隔离兜底（不进） | 挂画/窗帘进彩盒+prompt+allowed，完整接入 |
| 引擎测试 | (b1 基线) | 152 passed 0 skip |
| API 测试 | (b1 基线) | 320 passed 0 skip |

---

## 类型检查 / CI

```
引擎 pytest：152 passed, 0 skip
API pytest：320 passed, 0 skip
golden 字节快照：byte-for-byte 绿, 0 skip（rsvg-convert 可用）
ruff check（6 改动文件）：All checks passed
web tsc --noEmit（Node 22）：exit 0（无输出）
web lint：0 error（7 条 useViewport.ts 历史 exhaustive-deps warning，非本批文件，按约定不计）
web build：Done（/studio/projects/[id]/scheme 12.4 kB）
```

> CI 不跑 pytest（只跑 Playwright smoke）——Python 套件本地实跑背书。分支 feat/decor-b2（stacked off feat/decor-b1）；push main = 部署生产，合并/PR/部署时机待用户定。

---

## L2 实测记录

| 项 | 证据 |
|---|---|
| 第7步真实出图（配饰进实拍可见） | **[L2] 未执行** — 本机 `OPENAI_API_KEY`/`OPENAI_BASE_URL`(relay) 未设，`ai_enabled=False`（AI 端点 503）。spec F007 明文允许降级 SVG/mask 几何目检。 |
| 降级替代（已执行） | annotate 彩盒墙面带投影目检 + allowed mask 对位/structure 边界对抗 + prompt 锚定核查 + axon SVG/PNG 视觉旁证 decor 进渲染（见 render 报告 §1/§2/§5/§6/§7） |
| staging 部署 | 本批未部署 staging；push main=部署生产由用户手动，非本轮验收范围 |

> 挂画/窗帘的**彩盒 → prompt → allowed 验收**三段几何链路均本地 L1 可判且已判（含头号项真实 mask 对位）。真实模型出图待用户授权 relay 后 staging 抽验（backlog）。

---

## Ops 副作用记录

本批次无数据库 ops（文件存储无 DB；未碰 data/projects）。

---

## Harness 说明

本批改动经 Harness 状态机完整流程（planning → building → verifying → done，首轮 PASS fix_rounds=0）交付。快车道同会话 + 三域 fan-out 隔离 evaluator（python / web / render 域各独立 fresh-context subagent，结论互不软化）。`progress.json` 已设 `status:"done"`，signoff 路径已填 `docs.signoff`。

---

## Soft-watch（不阻塞 done，需后续跟进）

| ID | 描述 | 风险等级 | 建议处置 |
|---|---|---|---|
| S1 | [L2] 第7步真实出图未执行（AI keys 未设，spec 授权降级） | low | 用户授权 relay 后 staging 抽验 `_render_real_geometry_lock`；记 backlog BL-decor-b2-L2-realphoto |
| S2 | 落位美学为启发式（挂画居中/窗帘对齐/绿植靠角） | low | spec §7 明文 + F006 回归场景门 + F007 目检已守；不追求完美追求合理不误判 |
| S3 | 挂画 orient=facing vs backing：真实 D L-sofa `orient='E'` 而实贴 S 墙，挂画落朝向墙（仍 wall-flush/in-bounds/确定性） | low | polish：`host.orient` 与 `_nearest_wall` 冲突时优先取背靠墙；记 backlog |
| S4 | 测试 fixture 增强：O-1 非-full wtype 窗帘断言 / O-2 perspective byte-for-byte 单测 / O-3 head-line 非退化相机 fixture | low | 本报告已独立补齐三项实测；建议下批次固化为 pytest 断言 |
| S5 | `apply_decor` standalone 仅同候选内去重，不与该房既有 standalone 家具去重 | low | D 现无 decor + validation cap ≤1；若未来户型预置挂画/绿植需补去重；记 backlog |

---

## Framework Learnings

本批次沉淀 1 条候选提案（追加 `framework/proposed-learnings.md`，Planner done 阶段处理）：

### 新坑
- **对抗验收 fixture 退化陷阱**：几何/渲染类对抗验证若沿用现网单测 fixture 的坐标，可能命中退化位置（本批 wall_art@(300,300) 映射到合成相机眼位 → allowed=全帧 → structure 边界 trivially pass，掩盖真实对位风险）。Evaluator 做几何对抗时应先核 fixture 是否在相机正视野内（`box_usability` usable + in_frame_frac≈1），退化位置的"绿"不等于边界被压到。
  - 来源：decor-b2 F007 头号项验证
  - 建议写入：`framework/patterns/testing-env-patterns.md`（几何/渲染对抗验证 fixture 校验）
